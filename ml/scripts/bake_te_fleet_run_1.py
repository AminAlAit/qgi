"""Bake fleet-run-1 walk artifacts into the frontend's TE data-contract shape.

Reads per-recipe walk outputs from S3 under --ml-results-prefix (run-1 =
`ml-results/`, run-2 = `ml-results-run2/`) — produces a corpus at
`qgi-frontend/data/te-fleet-run-{N}/` in cards-v3 + scores + country-index +
analogs + activity-feed shape. Applies the Bucket A enrichments committed in
`docs/specs/internal/ops/te-sample-10-backend-reply-round-3-2026-05-29.md` so the
frontend reads server-resolved iso2/region/indicator names rather than
backfilling client-side.

INPUTS (resolved from CLI):
  --bucket qgi-data-lake-771606957899
  --output-dir qgi-frontend/data/te-fleet-run-1
  --countries qgi-frontend/data/countries.json
  --recipe-tracker qgi-frontend/data/recipe-tracker.json
  --indicator-catalog docs/specs/methodology/indicator-catalog-detailed.md
  --vintage fleet-run-1-2026-05-30

OUTPUTS (under --output-dir):
  MANIFEST.json
  cards-v3/{recipe_id}.card.json   (per-recipe, all 44)
  scores/{recipe_id}.scores.json   (per-recipe, enriched)
  countries/country-index.json
  analogs/current-state-analogs.json
  activity/program-feed.json

Per the backend reply Bucket A:
  - iso2/iso3/flag_emoji baked on scores + analogs entries
  - region on country-index (+ coverage_density_pct per region)
  - indicator `name` on every shap_attribution + indicator_sensitivity entry
  - description_compelling from recipe-tracker.json
  - family_label from recipe-tracker.json (drops the letter glyph)
  - recipe_status_audience derived from pipeline verdict
  - histogram[].countries[] on score_distribution
  - score_pp + n_countries_scored on scores file
  - compound_score_v2 per country (bounded formula)
  - engine: 'trajectory-engine-v1' on every card

Hard constraints preserved:
  - Bit-identity: loco_auc rendered at JSON precision (no Math.round)
  - foreign_intervention sourced ONLY from the 2026-05-29 re-walk (post-fix)
  - No probability claims; calibration block as-is from the walk summary
  - Byline = Amin Al-Ait (not relevant here; bake is data only)

Usage:
  python qgi-ml/scripts/bake_te_fleet_run_1.py \\
    --bucket qgi-data-lake-771606957899 \\
    --output-dir ../qgi-frontend/data/te-fleet-run-1 \\
    --countries ../qgi-frontend/data/countries.json \\
    --recipe-tracker ../qgi-frontend/data/recipe-tracker.json \\
    --indicator-catalog ../docs/specs/methodology/indicator-catalog-detailed.md \\
    --vintage fleet-run-1-2026-05-30
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import math
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("bake-te-fleet-run-1")

# ─── verdict → recipe_status_audience mapping (§9.3) ─────────────────────────
# Pipeline owns the canonical mapping; frontend safe-falls unknown to "coming_soon".
#
# M8-R7 (BINDING, 2026-05-30 cumulative DECISION §10): "prior_version" only
# applies to a HARD_FAIL or CHANCE_FAIL whose recipe HAS appeared as validated
# or graduated on the public site (i.e. the recipe has a prior public footprint).
# For greenfield (no prior public footprint), use a neutral never-graduated
# label. The gate fires for any verdict whose base mapping = "prior_version"
# (currently HARD_FAIL + CHANCE_FAIL).
#
# The base map below is the "with prior" view; the runtime gate in
# _resolve_audience_status() applies M8-R7 using the recipe's tracker status.
VERDICT_TO_AUDIENCE_STATUS = {
    "LOCK": "validated",
    "HARD_FAIL": "prior_version",
    "COVERAGE_FAIL": "coming_soon",
    "CHANCE_FAIL": "prior_version",
    "MARGINAL": "in_play",
    "MARGINAL_PENDING_BETA_CALIBRATION": "in_play",
    "MARGINAL_PENDING_BETA_CAL": "in_play",
}

# Tracker statuses that count as "validated or graduated" public footprint per
# M8-R7. `walked_no_graduation` is NOT public footprint of a GRADUATION; the
# recipe was walked but never shipped as validated. Greenfield (`queued` or
# anything else) likewise has no public footprint.
PRIOR_PUBLIC_FOOTPRINT_STATUSES = frozenset({"live_legacy", "graduated"})


def _resolve_audience_status(verdict: str, tracker_row: dict | None) -> str:
    """M8-R7 gate: a HARD_FAIL maps to 'prior_version' only when the recipe has
    prior public footprint (was validated/graduated). Greenfield HARD_FAILs
    (the common case in fleet-run-1) get 'coming_soon' instead — honest about
    "we tried this and the protective-belt did not clear" without falsely
    implying a roll-back from a prior public version.

    Args:
        verdict: the walk's verdict string (e.g. "LOCK", "HARD_FAIL").
        tracker_row: the recipe's row from recipe-tracker.json, or None if
            the recipe is not yet in the tracker (greenfield).

    Returns the audience-status string. Caller emits it to the scores file +
    card. Unknown verdicts fall to "coming_soon" (same as the dict default).
    """
    base = VERDICT_TO_AUDIENCE_STATUS.get(verdict, "coming_soon")
    if base != "prior_version":
        return base
    tracker_status = (tracker_row or {}).get("status")
    if tracker_status in PRIOR_PUBLIC_FOOTPRINT_STATUSES:
        return "prior_version"
    return "coming_soon"

# ─── verdict → tier (the legacy classification used on cards) ────────────────
VERDICT_TO_TIER = {
    "LOCK": "validated",
    "HARD_FAIL": "experimental",
    "COVERAGE_FAIL": "experimental",
    "CHANCE_FAIL": "experimental",
    "MARGINAL": "directional",
    "MARGINAL_PENDING_BETA_CALIBRATION": "directional",
    "MARGINAL_PENDING_BETA_CAL": "directional",
}

CONTRACT_VERSION = "v3-2026-05-30"


# ─── Output writer (local FS vs AWS S3) ──────────────────────────────────────
#
# `BAKE_MODE` env-var selects the destination of every artifact write:
#   - unset / "local"  → writes under args.output_dir on the local filesystem
#   - "aws"            → writes under s3://{args.bucket}/{OUTPUT_S3_PREFIX}/
#
# AWS mode also enforces the run-separation rule (
# `feedback_run_separation_versioning.md`): the target S3 prefix must not
# already contain a MANIFEST.json. Refuse-to-overwrite is fail-loud, never
# silent — a duplicate execution name (manual restart) must be caught here
# before any new file lands on top of a published vintage.
class _BakeOutput:
    """Routes mkdir + write_text to local FS or to S3 based on `mode`.

    Paths in calls are RELATIVE to the bake output root (e.g.
    "scores/foreign_intervention.scores.json"). Callers should not pass
    absolute paths or paths beginning with "/".
    """

    def __init__(
        self,
        *,
        mode: str,
        output_dir: Path,
        s3_client: Any,
        bucket: str,
        prefix: str,
    ) -> None:
        if mode not in ("local", "aws"):
            raise ValueError(f"Invalid BAKE_MODE: {mode!r} (expected local|aws)")
        self.mode = mode
        self.output_dir = output_dir
        self.s3 = s3_client
        self.bucket = bucket
        # Normalize trailing slash on prefix so concat always yields valid key
        self.prefix = (prefix.rstrip("/") + "/") if prefix else ""

    def mkdir(self, rel: str = "") -> None:
        if self.mode == "aws":
            return  # S3 has no directories; put_object lazily creates the path
        target = self.output_dir / rel if rel else self.output_dir
        target.mkdir(parents=True, exist_ok=True)

    def write_text(self, rel_path: str, content: str) -> None:
        if rel_path.startswith("/"):
            raise ValueError(f"rel_path must be relative, got {rel_path!r}")
        if self.mode == "aws":
            key = f"{self.prefix}{rel_path}"
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType="application/json",
            )
        else:
            target = self.output_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            # encoding="utf-8" matches the S3 path (which always writes UTF-8
            # via .encode("utf-8")). Without it, Windows-default cp1252 would
            # silently mangle flag emoji / non-ASCII indicator names. QA
            # review F1 on qgi-ml#132.
            target.write_text(content, encoding="utf-8")

    def describe_root(self) -> str:
        if self.mode == "aws":
            return f"s3://{self.bucket}/{self.prefix}"
        return str(self.output_dir)


def _resolve_reference_input(arg_value: str | Path, s3_client: Any) -> Path:
    """Resolve a CLI --countries / --recipe-tracker / --indicator-catalog
    argument that may be a local path OR an s3:// URI.

    AWS-mode prereq (per the bake Batch JobDef): the founder syncs the 3
    reference files to s3://qgi-data-lake-771606957899/reference/. The
    JobDef then passes s3:// URIs for these flags so we don't have to
    bake them into the container image.

    Local mode: argv passes a local path; this function is a no-op (returns
    Path verbatim).
    """
    s = str(arg_value)
    if not s.startswith("s3://"):
        return Path(s)
    # s3://bucket/key/with/slashes.json
    after_scheme = s[len("s3://"):]
    if "/" not in after_scheme:
        raise ValueError(f"Malformed S3 URI: {s!r} (expected s3://bucket/key)")
    bucket, _, key = after_scheme.partition("/")
    # QA #133 BLOCK fix: `s3://bucket/` passes the slash check but yields
    # an empty key, which boto3 would dispatch as an opaque mid-bake S3 error
    # instead of failing pre-flight here.
    if not key:
        raise ValueError(f"Malformed S3 URI: {s!r} (key is empty after bucket name)")
    suffix = Path(key).suffix or ".tmp"
    # Use a NamedTemporaryFile with delete=False so it survives until process exit.
    import tempfile
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="bake-ref-")
    os.close(fd)
    LOG.info("Downloading s3://%s/%s to %s", bucket, key, tmp_path)
    s3_client.download_file(bucket, key, tmp_path)
    return Path(tmp_path)


def _sync_panel_root(arg_value: str | Path, s3_client: Any) -> Path:
    """Resolve --panel-root, which may be a local path OR an ``s3://`` prefix.

    The qgi-recipe-fleet image has **no s3fs**, so the bake cannot
    ``pd.read_parquet('s3://...')`` directly, and the bake job does NOT run the walk
    entrypoint that syncs panels. In AWS mode the JobDef therefore passes the
    ``pipeline-A-indicator-extractor/output/parquet-completed/`` prefix as an ``s3://``
    URI; this syncs every ``{code}/`` panel under it to a local temp dir (boto3,
    in-region ⇒ ~free) and returns that dir, so the downstream ``_load_panel(panel_root,
    code)`` reads work unchanged. WITHOUT this, population (§C.1), trajectory_window
    (§A.2), raw indicator values (§1.4) and analog trajectories (§D) silently null out
    in the cloud bake. Local mode: returns the path verbatim (no-op)."""
    s = str(arg_value)
    if not s.startswith("s3://"):
        return Path(s)
    after_scheme = s[len("s3://"):]
    if "/" not in after_scheme:
        raise ValueError(f"Malformed S3 panel URI: {s!r} (expected s3://bucket/prefix/)")
    bucket, _, prefix = after_scheme.partition("/")
    if not prefix:
        raise ValueError(f"Malformed S3 panel URI: {s!r} (prefix is empty after bucket)")
    import tempfile
    dest = Path(tempfile.mkdtemp(prefix="bake-panels-"))
    paginator = s3_client.get_paginator("list_objects_v2")
    n = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(prefix):].lstrip("/")
            if not rel:  # the prefix's own placeholder object, if any
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            s3_client.download_file(bucket, key, str(target))
            n += 1
    LOG.info("Synced %d panel objects from %s -> %s", n, s, dest)
    return dest


def _refuse_overwrite_if_baked(s3_client: Any, bucket: str, prefix: str) -> None:
    """Per `feedback_run_separation_versioning.md` — refuse-to-overwrite if a
    MANIFEST.json already exists at the target prefix. Raises RuntimeError so
    main() can fail loud with a non-zero exit code; SFN sees a failed Batch
    job rather than a silent overwrite of a published vintage."""
    if not prefix:
        return
    key = f"{prefix.rstrip('/')}/MANIFEST.json"
    resp = s3_client.list_objects_v2(Bucket=bucket, Prefix=key, MaxKeys=1)
    if resp.get("KeyCount"):
        raise RuntimeError(
            f"Refusing to overwrite published vintage: s3://{bucket}/{key} "
            "already exists. Every fleet run must have a unique OUTPUT_S3_PREFIX "
            "(see feedback_run_separation_versioning.md). If this is a "
            "deliberate restart, delete the existing prefix manually first."
        )


def _provider_for(code: str | None) -> str | None:
    """Indicator-provider hint via code-prefix heuristic. Mirrors frontend's
    inferProvider(). Pipeline ought to emit this explicitly per frontend §1.4 —
    until then this is a server-side approximation."""
    if not code:
        return None
    if code.startswith("v2") or code.startswith("v3"):
        return "V-Dem"
    if code.endswith(".EST"):
        return "World Bank WGI"
    return "World Bank"


# ────────────────────────────────────────────────────────────────────────────
# Resource loaders
# ────────────────────────────────────────────────────────────────────────────

def load_countries(path: Path) -> dict[str, dict[str, str]]:
    """Returns: name → {iso2, iso3, name} dict. Source: qgi-frontend/data/countries.json
    which has [{id, name, alpha_2}, ...]. We synthesize iso3 from alpha_2 via a small
    fallback table for the most common cases — the catalog is iso-2 only.
    """
    countries = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for c in countries:
        name = c.get("name") or ""
        iso2 = c.get("alpha_2")
        if not name or not iso2:
            continue
        out[name] = {"iso2": iso2.lower(), "iso3": None, "name": name}
    return out


# Flag emoji from iso2 codepoints: A=0x1F1E6, etc.
def flag_emoji_from_iso2(iso2: str | None) -> str | None:
    if not iso2 or len(iso2) != 2:
        return None
    base = 0x1F1E6
    cp = [base + ord(c.upper()) - ord("A") for c in iso2]
    return "".join(chr(p) for p in cp)


# UN-region static seed (kept minimal; covers the ~150 countries we score).
_REGION_SEED = {
    "us": "Americas", "ca": "Americas", "mx": "Americas", "br": "Americas",
    "ar": "Americas", "cl": "Americas", "co": "Americas", "pe": "Americas",
    "ve": "Americas", "uy": "Americas", "ec": "Americas", "bo": "Americas",
    "cu": "Americas", "do": "Americas", "ht": "Americas", "gt": "Americas",
    "hn": "Americas", "ni": "Americas", "pa": "Americas", "cr": "Americas",
    "sv": "Americas", "jm": "Americas", "tt": "Americas", "py": "Americas",
    "gb": "Europe", "fr": "Europe", "de": "Europe", "it": "Europe",
    "es": "Europe", "pt": "Europe", "nl": "Europe", "be": "Europe",
    "ch": "Europe", "at": "Europe", "se": "Europe", "no": "Europe",
    "dk": "Europe", "fi": "Europe", "ie": "Europe", "pl": "Europe",
    "cz": "Europe", "sk": "Europe", "hu": "Europe", "ro": "Europe",
    "bg": "Europe", "gr": "Europe", "hr": "Europe", "rs": "Europe",
    "ba": "Europe", "al": "Europe", "mk": "Europe", "si": "Europe",
    "lt": "Europe", "lv": "Europe", "ee": "Europe", "is": "Europe",
    "mt": "Europe", "lu": "Europe", "cy": "Europe", "by": "Europe",
    "ua": "Europe", "md": "Europe", "ru": "Europe", "me": "Europe",
    "cn": "Asia", "jp": "Asia", "kr": "Asia", "kp": "Asia",
    "tw": "Asia", "hk": "Asia", "mn": "Asia", "in": "Asia",
    "pk": "Asia", "bd": "Asia", "lk": "Asia", "np": "Asia",
    "bt": "Asia", "mm": "Asia", "th": "Asia", "vn": "Asia",
    "kh": "Asia", "la": "Asia", "my": "Asia", "sg": "Asia",
    "id": "Asia", "ph": "Asia", "bn": "Asia", "tl": "Asia",
    "af": "Asia", "ir": "Asia", "iq": "Asia", "sy": "Asia",
    "lb": "Asia", "jo": "Asia", "il": "Asia", "ps": "Asia",
    "sa": "Asia", "ae": "Asia", "om": "Asia", "ye": "Asia",
    "kw": "Asia", "qa": "Asia", "bh": "Asia", "tr": "Asia",
    "ge": "Asia", "am": "Asia", "az": "Asia", "kz": "Asia",
    "uz": "Asia", "tm": "Asia", "kg": "Asia", "tj": "Asia",
    "eg": "Africa", "ly": "Africa", "tn": "Africa", "dz": "Africa",
    "ma": "Africa", "sd": "Africa", "ss": "Africa", "et": "Africa",
    "er": "Africa", "dj": "Africa", "so": "Africa", "ke": "Africa",
    "ug": "Africa", "tz": "Africa", "rw": "Africa", "bi": "Africa",
    "cd": "Africa", "cg": "Africa", "cf": "Africa", "td": "Africa",
    "cm": "Africa", "ne": "Africa", "ng": "Africa", "bj": "Africa",
    "tg": "Africa", "gh": "Africa", "ci": "Africa", "lr": "Africa",
    "sl": "Africa", "gn": "Africa", "gw": "Africa", "sn": "Africa",
    "gm": "Africa", "ml": "Africa", "bf": "Africa", "mr": "Africa",
    "cv": "Africa", "ao": "Africa", "zm": "Africa", "mw": "Africa",
    "mz": "Africa", "zw": "Africa", "bw": "Africa", "na": "Africa",
    "za": "Africa", "sz": "Africa", "ls": "Africa", "mg": "Africa",
    "mu": "Africa", "sc": "Africa", "km": "Africa", "ga": "Africa",
    "gq": "Africa", "st": "Africa", "au": "Oceania", "nz": "Oceania",
    "pg": "Oceania", "fj": "Oceania", "sb": "Oceania", "vu": "Oceania",
    "ws": "Oceania", "ki": "Oceania", "to": "Oceania", "fm": "Oceania",
    "mh": "Oceania", "pw": "Oceania", "nr": "Oceania", "tv": "Oceania",
}


def region_for(iso2: str | None) -> str | None:
    if not iso2:
        return None
    return _REGION_SEED.get(iso2.lower())


def load_recipe_tracker(path: Path) -> dict[str, dict[str, Any]]:
    """Returns: recipe_id → tracker row with description_compelling + l1_id + label.
    Source: qgi-frontend/data/recipe-tracker.json (the canonical hand-curated set).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    # The tracker is a flat list of recipe entries
    recipes = data if isinstance(data, list) else data.get("recipes", [])
    for r in recipes:
        rid = r.get("recipe_id") or r.get("id")
        if not rid:
            continue
        out[rid] = r
    return out


# Family taxonomy A-H per recipe-tracker.json convention
FAMILY_LABELS = {
    "A": "Governance Stress",
    "B": "Economic Stress",
    "C": "Civil Conflict",
    "D": "International Tension",
    "E": "Foreign Policy",
    "F": "Social Movements",
    "G": "External Shock",
    "H": "Institutional Reform",
}


def load_indicator_catalog(path: Path) -> dict[str, str]:
    """Returns: indicator_code → friendly name.
    Parses the markdown table from docs/specs/methodology/indicator-catalog-detailed.md.

    Catalog rows have shape:
      `| WB-01 | VC.BTL.DETH | Battle-related deaths per 100K | <prose> | ... |`
       ID-col   code-col      name-col                          QGI-value
    OR (for V-Dem section without ID col):
      `| v2x_polyarchy | Electoral Democracy Index (0-1) | ... |`

    Strategy: scan all `|`-delimited cells; find the FIRST cell that looks like
    an indicator code (no spaces, contains '.' or '_', 4-30 chars); use the
    NEXT non-empty cell as the friendly name.
    """
    if not path.exists():
        LOG.warning("indicator catalog not found at %s — names will be null", path)
        return {}
    out: dict[str, str] = {}
    code_re = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.]{3,29}$")

    def looks_like_code(s: str) -> bool:
        s = s.strip()
        if not code_re.match(s):
            return False
        # Reject if it's an ID-marker (WB-NN, VD-NN, FA-NN, IL-NN, NN-NN)
        if re.match(r"^[A-Z]{2,3}-\d{1,3}$", s):
            return False
        # Must contain at least one '.' or '_' or be all-lowercase v-prefixed
        return ("." in s) or ("_" in s) or s.startswith("v2")

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        # Skip separator rows
        if all(set(c) <= {"-", " ", ":"} for c in cells):
            continue
        # Skip header rows
        if any(c.lower() in ("code", "indicator", "name", "indicator name") for c in cells[:3]):
            continue
        # Find the first code-shaped cell + use the next non-empty cell as name
        for i, c in enumerate(cells):
            if looks_like_code(c):
                name = next((cells[j] for j in range(i + 1, len(cells)) if cells[j]), None)
                if name and name != c and len(name) > 3:
                    out[c] = name
                break
    return out


# ────────────────────────────────────────────────────────────────────────────
# S3 helpers
# ────────────────────────────────────────────────────────────────────────────

def list_recipe_dirs(s3: Any, bucket: str, prefix: str = "ml-results/") -> list[str]:
    out: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for p in page.get("CommonPrefixes", []) or []:
            sub = p["Prefix"][len(prefix):].rstrip("/")
            if not sub or sub.startswith("_"):
                continue
            out.append(sub)
    return sorted(out)


def s3_get_json(s3: Any, bucket: str, key: str) -> dict | None:
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        return json.loads(body)
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────────────
# Panel-parquet helpers (raw values + units + provider)
# ────────────────────────────────────────────────────────────────────────────

_PANEL_CACHE: dict[str, Any] = {}


def _load_panel(panel_root: Path, code: str):
    """Load + cache a single indicator panel. Returns DataFrame or None."""
    if code in _PANEL_CACHE:
        return _PANEL_CACHE[code]
    import pandas as pd
    p = panel_root / code
    if not p.exists():
        _PANEL_CACHE[code] = None
        return None
    try:
        df = pd.read_parquet(p)
        _PANEL_CACHE[code] = df
        return df
    except Exception:
        _PANEL_CACHE[code] = None
        return None


def panel_lookup(panel_root: Path, code: str, country: str, year: int) -> tuple[Any, Any, str | None]:
    """Returns (value_at_year, value_prev_year, provider) for (country, year)."""
    df = _load_panel(panel_root, code)
    if df is None:
        return None, None, None
    rows = df[(df["country"] == country) & (df["year"] <= year)].sort_values("year")
    if rows.empty:
        return None, None, None
    latest = rows.iloc[-1]
    prev = rows.iloc[-2] if len(rows) >= 2 else None
    provider = latest.get("provider") if "provider" in df.columns else None
    return (
        float(latest["value"]) if pd.notna(latest["value"]) else None,
        float(prev["value"]) if (prev is not None and pd.notna(prev["value"])) else None,
        str(provider) if provider else None,
    )


def _load_population(panel_root: Path | None) -> dict[str, int]:
    """Latest SP.POP.TOTL value per country, read from the indicator panels (frontend
    §C.1). Population is already an ingested WB indicator — no external fetch needed.
    Empty dict when the panel is absent (population stays null; the FE keeps its seeds)."""
    if not panel_root:
        return {}
    df = _load_panel(Path(panel_root), "SP.POP.TOTL")
    if df is None or "country" not in getattr(df, "columns", []):
        return {}
    out: dict[str, int] = {}
    valid = df[df["value"].notna()]
    for country, g in valid.groupby("country"):
        latest = g.sort_values("year").iloc[-1]
        try:
            out[str(country)] = int(round(float(latest["value"])))
        except (TypeError, ValueError):
            continue
    return out


def analog_pre_event_trajectory(
    panel_root: Path,
    selected: list[str],
    analog_country: str,
    analog_year: int,
    panel_wide_z: dict | None,
) -> list[float]:
    """Compute the 12-year pre-event composite z-score trajectory for an analog
    (country, year) tuple. Mean over selected indicators, z-scored using the
    panel-wide-z-distribution stats (mean/std per indicator). LOCF fill on
    missing years. Returns [] if no indicator data is available.
    (Frontend §1.1 indicator_trajectory_12q per AnalogEntry — gap #3 close.)
    """
    if not analog_country or not analog_year:
        return []
    years = list(range(int(analog_year) - 11, int(analog_year) + 1))  # 12 inclusive
    composite = [0.0] * 12
    n_contrib = [0] * 12
    z_stats = (panel_wide_z or {}).get("indicators") or {}

    import math
    for code in selected:
        df = _load_panel(panel_root, code)
        if df is None:
            continue
        stats = z_stats.get(code) or {}
        mu = stats.get("mean")
        sigma = stats.get("std")
        # Defensive fallbacks — nan/None/zero all need to be handled.
        if mu is None or (isinstance(mu, float) and math.isnan(mu)):
            mu = float(df["value"].mean())
        if mu is None or (isinstance(mu, float) and math.isnan(mu)):
            mu = 0.0
        if sigma is None or (isinstance(sigma, float) and math.isnan(sigma)) or sigma <= 0:
            sigma = float(df["value"].std())
        if sigma is None or (isinstance(sigma, float) and math.isnan(sigma)) or sigma <= 0:
            sigma = 1.0
        cdf = df[(df["country"] == analog_country) & (df["year"] <= max(years))].sort_values("year")
        if cdf.empty:
            continue
        # Build year → value index for LOCF
        year_to_val: dict[int, float] = {}
        last_val = None
        for _, row in cdf.iterrows():
            y = int(row["year"])
            v = row["value"]
            if pd.notna(v):
                last_val = float(v)
            year_to_val[y] = last_val
        # Find value at each target year using LOCF
        sorted_years = sorted(year_to_val.keys())
        for i, target in enumerate(years):
            val = None
            for y in reversed(sorted_years):
                if y <= target:
                    val = year_to_val[y]
                    break
            if val is None:
                continue
            if isinstance(val, float) and math.isnan(val):
                continue
            z = (val - mu) / sigma
            if math.isnan(z) or math.isinf(z):
                continue
            composite[i] += z
            n_contrib[i] += 1
    # Average across contributing indicators per time point
    if not any(n_contrib):
        return []
    return [composite[i] / n_contrib[i] if n_contrib[i] > 0 else 0.0 for i in range(12)]


# Lightweight unit hints from common indicator-code prefixes.
def unit_hint_for(code: str | None) -> str | None:
    if not code:
        return None
    if code.endswith(".ZS") or code.endswith(".GD.ZS"):
        return "% of GDP" if ".GD" in code else "%"
    if code.endswith(".KD") or code.endswith(".CD"):
        return "USD"
    if code.endswith(".P5") or "PSRC.P5" in code:
        return "per 100K population"
    if code.startswith("v2") or code.startswith("v3"):
        return "z-score (V-Dem)"
    if code.endswith(".EST"):
        return "WGI score"
    return None


def import_pandas():
    """Lazy import so the bake doesn't require pandas if panels disabled."""
    global pd
    import pandas as _pd
    pd = _pd
    return _pd


# ────────────────────────────────────────────────────────────────────────────
# Card-v3 builder
# ────────────────────────────────────────────────────────────────────────────

def normalize_iso(name: str, countries: dict[str, dict[str, str]]) -> tuple[str | None, str | None, str | None]:
    """Returns (iso2, iso3, flag_emoji) for a country name; (None, None, None) if not found."""
    if not name:
        return None, None, None
    # Direct hit
    entry = countries.get(name)
    if entry:
        iso2 = entry.get("iso2")
        return iso2, entry.get("iso3"), flag_emoji_from_iso2(iso2)
    # Title-case retry
    entry = countries.get(name.title())
    if entry:
        iso2 = entry.get("iso2")
        return iso2, entry.get("iso3"), flag_emoji_from_iso2(iso2)
    return None, None, None


def _percentile(values: list[float], q: float) -> float:
    """Linear-interpolation percentile (q in [0,100]) over a non-empty list.
    Matches numpy's default 'linear' method so a shape line renders identically
    whether aggregated here or upstream. Pure stdlib (the bake has no numpy)."""
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    rank = (q / 100.0) * (len(s) - 1)
    lo = int(rank)
    frac = rank - lo
    if lo + 1 < len(s):
        return float(s[lo] + frac * (s[lo + 1] - s[lo]))
    return float(s[lo])


def _fill_gaps(arr: list) -> list:
    """Fill None gaps so a shape array is a full number[] (the frontend card-v3
    contract declares mean/p25/p75 as non-nullable). A gap means NO positive case
    covered that lead-year (rare — sparse early indicator coverage). Interior gaps
    are linearly interpolated between the nearest known lead-years; leading/trailing
    gaps carry the nearest known value. Interpolating a smooth z-trajectory is a
    standard, defensible estimate and is disclosed in the alignment `method` string."""
    known = [i for i, v in enumerate(arr) if v is not None]
    if not known:
        return arr  # all-None — caller skips empty indicators, so this is defensive
    out = list(arr)
    for i in range(0, known[0]):              # leading
        out[i] = arr[known[0]]
    for i in range(known[-1] + 1, len(arr)):  # trailing
        out[i] = arr[known[-1]]
    for a, b in zip(known, known[1:]):        # interior
        if b - a > 1:
            for i in range(a + 1, b):
                frac = (i - a) / (b - a)
                out[i] = round(arr[a] + frac * (arr[b] - arr[a]), 4)
    return out


def _build_trajectory_alignment(summary: dict, indicator_names: dict[str, str]) -> dict | None:
    """Canonical per-indicator movement shape (frontend bake-request B.1): z-scored
    mean/p25/p75 of each selected indicator across the recipe's positive cases over
    the window run-up, one point per lead-year.

    Source is already on S3 in the walk summary
    (`descriptive_emit.ranked_trajectory_signature.per_indicator_signatures[].samples[]`,
    each carrying `temporal_profile` + `years_covered`); we aggregate at bake time, NO
    re-walk. Samples are aligned by RELATIVE lead position (year_covered - event_year),
    not by raw index: each sample's profile is dropna'd so lengths differ, and aligning
    by index would smear different lead-times together.

    Coverage: pre-§F walks (fleet-run-1) emit only head(5) positives, so those cards
    carry a 5-sample shape (identified by samples_used == 5; the same basis te-sample-10
    shipped). §F-onward walks emit the full positive corpus. `samples_used` always
    records the actual count for audit."""
    rts = (summary.get("descriptive_emit") or {}).get("ranked_trajectory_signature") or {}
    per_ind = rts.get("per_indicator_signatures") or []
    if not per_ind:
        return None
    window_years = (summary.get("greedy_outer_loop") or {}).get("chosen_window")
    if not isinstance(window_years, int) or window_years < 2:
        return None

    positions = list(range(-int(window_years), 0))  # -W .. -1 (years before the event)
    indicators_out: list[dict] = []
    max_samples = 0
    for block in per_ind:
        code = block.get("indicator_id")
        if not code:  # malformed signature block — can't identify the indicator
            continue
        samples = block.get("samples") or []
        max_samples = max(max_samples, len(samples))
        by_pos: dict[int, list[float]] = {}
        for s in samples:
            profile = s.get("temporal_profile") or []
            years = s.get("years_covered") or []
            ev = s.get("year")
            if ev is None or len(profile) != len(years):
                continue
            for z, yr in zip(profile, years):
                by_pos.setdefault(int(yr) - int(ev), []).append(float(z))
        if not by_pos:
            continue
        mean_arr, p25_arr, p75_arr = [], [], []
        for p in positions:
            vals = by_pos.get(p)
            if vals:
                mean_arr.append(round(sum(vals) / len(vals), 4))
                p25_arr.append(round(_percentile(vals, 25), 4))
                p75_arr.append(round(_percentile(vals, 75), 4))
            else:
                mean_arr.append(None)
                p25_arr.append(None)
                p75_arr.append(None)
        indicators_out.append({
            "code": code,
            "name": indicator_names.get(code),
            "provider": _provider_for(code),
            "n_samples": len(samples),
            "shape": {
                "mean": _fill_gaps(mean_arr),
                "p25": _fill_gaps(p25_arr),
                "p75": _fill_gaps(p75_arr),
            },
        })
    if not indicators_out:
        return None
    return {
        "window_years": int(window_years),
        "indicators": indicators_out,
        "samples_used": max_samples,
        "method": ("z-aggregated across the emitted positive cases (count in "
                   "samples_used), aligned by lead-year, gaps linearly interpolated. "
                   "Pre-§F walks emit head(5) positives; §F-onward emit the full corpus."),
    }


def _cohort_separation_pp(per_cohort: dict | None) -> float | None:
    """reliability_multipass.v1_separation_pp: the spread (in AUC points) between the
    best and worst per-cohort LOCO-AUC. A within-run consistency signal derivable from
    this single walk; v4_oot_recall_pct stays null (it genuinely needs a 2nd pass)."""
    if not per_cohort:
        return None
    aucs = [v.get("loco_auc") for v in per_cohort.values()
            if isinstance(v, dict) and v.get("loco_auc") is not None]
    if len(aucs) < 2:
        return None
    return round(max(aucs) - min(aucs), 4)


def _per_cohort_calibration(per_cohort: dict | None) -> dict | None:
    """Per-cohort calibration (frontend bake-request B.4): {cohort: {ece, bins, n}}.
    The pooled `calibration` block is left intact; this adds the per-cohort breakdown
    the walk already computed (`per_cohort[c].ece` + `.reliability_diagram_bins`)."""
    if not per_cohort:
        return None
    out: dict[str, dict] = {}
    for cohort, v in per_cohort.items():
        if not isinstance(v, dict):
            continue
        out[cohort] = {
            "ece": v.get("ece"),
            "bins": v.get("reliability_diagram_bins"),
            "n": v.get("n"),
            "low_confidence": v.get("low_confidence"),
        }
    return out or None


def _calibration_block(summary: dict) -> dict:
    """Pooled calibration block + a per-cohort breakdown folded in. Returns a FRESH
    dict so we never mutate the summary's own `calibration` object."""
    base = dict(summary.get("calibration") or {
        "computed": False,
        "bins": None,
        "ece": None,
        "notes": "calibration block absent in this vintage",
    })
    pc = _per_cohort_calibration(summary.get("per_cohort"))
    if pc is not None:
        base["per_cohort"] = pc
    return base


def _load_verified_events(path: Path | None) -> dict[str, list[dict]]:
    """Group the curated verified-events corpus by `category` (== recipe_id) for the
    §B.3 precedents. Empty dict when no path is given — precedents then come back empty
    and the recipe-detail Precedents panel keeps its 'no precedents yet' state."""
    if not path:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    by_cat: dict[str, list[dict]] = {}
    for e in raw:
        cat = e.get("category")
        if cat:
            by_cat.setdefault(cat, []).append(e)
    return by_cat


def _norm_country_key(name: str | None) -> str:
    """Fold a verified-events country name to positives.csv's `country_id` form
    (lowercase, underscores). A fold mismatch just leaves in_training_set False — the
    event still appears in the precedents list, it's only not flagged as a training case."""
    return (name or "").strip().lower().replace(" ", "_")


def _load_positives_set(shape_inputs_root: Path | None, rid: str) -> set[tuple[str, int]]:
    """Read {root}/{rid}/positives.csv (header: country_id,event_year) into a
    {(country_id, year)} set for the in_training_set flag. Empty set if the file is
    absent (in_training_set then degrades to all-False; precedents still render)."""
    if not shape_inputs_root:
        return set()
    p = Path(shape_inputs_root) / rid / "positives.csv"
    if not p.exists():
        return set()
    out: set[tuple[str, int]] = set()
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        if i == 0 or not line.strip():  # header / blank
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            out.add((parts[0].strip().lower(), int(float(parts[1].strip()))))
        except ValueError:
            continue
    return out


def _build_precedents_corpus(rid: str, events_by_cat: dict[str, list[dict]],
                             positives: set[tuple[str, int]], countries: dict) -> dict:
    """frontend §B.3: the recipe's precedents corpus = every curated event whose
    `category` is this recipe, each tagged `in_training_set` (was it one of the walk's
    positives). Most-recent first. Always returns a dict (possibly empty events) so the
    panel can show '0 precedents' vs. an un-computed null."""
    out_events: list[dict] = []
    for e in (events_by_cat.get(rid) or []):
        nm = e.get("country")
        iso2, _, _ = normalize_iso(nm, countries) if nm else (None, None, None)
        try:
            yr_int = int(e.get("year"))
        except (TypeError, ValueError):
            yr_int = None
        in_ts = yr_int is not None and (_norm_country_key(nm), yr_int) in positives
        out_events.append({
            "country_iso": iso2,
            "country_name": nm,
            "year": yr_int,
            "label": e.get("title"),
            "in_training_set": in_ts,
        })
    out_events.sort(key=lambda x: -(x["year"] or 0))  # most recent first
    return {"events": out_events, "total_events_in_corpus": len(out_events)}


def build_card_v3(
    summary: dict,
    sensitivity_data: dict | None,
    indicator_names: dict[str, str],
    tracker_row: dict[str, Any] | None,
    s3_bucket: str,
    shap_data: dict | None = None,
    panel_root: Path | None = None,
    precedents_corpus: dict | None = None,
    ml_results_prefix: str = "ml-results/",
) -> dict:
    """Compose a card-v3 JSON from the walk summary + sidecar artifacts."""
    rid = summary.get("recipe_id")
    verdict = summary.get("verdict") or "UNKNOWN"
    tier = VERDICT_TO_TIER.get(verdict, "experimental")
    # M8-R7 (BINDING) gate: tracker_row drives the prior_version vs. coming_soon
    # split. See module-level _resolve_audience_status() docstring + the
    # 2026-05-30 cumulative DECISION §10 annex.
    audience_status = _resolve_audience_status(verdict, tracker_row)
    go = summary.get("greedy_outer_loop") or {}
    selected = go.get("selected_indicators") or []
    chosen_window = go.get("chosen_window")
    gl = summary.get("global_loco") or {}

    # Family from tracker row's l1_id
    l1_id = (tracker_row or {}).get("l1_id") or (tracker_row or {}).get("family_id")
    family_label = FAMILY_LABELS.get(l1_id) if l1_id else None

    # Indicator-sensitivity LOO (#967 emits this in score_countries; pull from sidecar)
    sens_entries: list[dict] = []
    if sensitivity_data:
        for e in sensitivity_data.get("leave_one_out") or []:
            code = e.get("indicator") or e.get("code")
            sens_entries.append({
                "code": code,
                "name": indicator_names.get(code) if code else None,
                "auc_with": e.get("cv_auc_full") or e.get("auc_with"),
                "auc_without": e.get("cv_auc_without") or e.get("auc_without"),
                "auc_drop": e.get("auc_drop"),
            })

    # Greedy walk history (best-effort; #967 walk schema)
    greedy_history = []
    for step in (go.get("history") or []):
        greedy_history.append({
            "step": step.get("step"),
            "candidate": step.get("candidate") or step.get("indicator"),
            "window": step.get("window"),
            "auc": step.get("auc") or step.get("final_global_auc"),
            "lift_over_previous": step.get("lift_over_previous", 0),
            "selected_after": step.get("selected_after") or [],
        })

    # score_distribution: computed downstream from country-scores.json
    # (filled in build_scores_file; emitted here as placeholder)
    score_distribution = {
        "computed": False,
        "histogram": [],
        "median": None,
        "p90": None,
        "p99": None,
        "max": None,
        "n_countries_scored": 0,
        "source": "score_countries.py per-country eval",
    }

    card = {
        "recipe_id": rid,
        "engine": "trajectory-engine-v1",
        "contract_version": CONTRACT_VERSION,
        "tier": tier,
        "tier_provenance": "verdict → tier mapping in bake_te_fleet_run_1.py",
        "recipe_status_audience": audience_status,
        "family_label": family_label,
        "description_compelling": (tracker_row or {}).get("description_compelling"),
        "description": (tracker_row or {}).get("description"),
        "verdict": verdict,
        "stats": {
            "loco_auc": gl.get("auc"),
            "ci95_lo": gl.get("ci95_lo"),
            "ci95_hi": gl.get("ci95_hi"),
            "ci80_lo": gl.get("ci80_lo"),
            "ci80_hi": gl.get("ci80_hi"),
            "n_bootstrap": gl.get("n_bootstrap"),
        },
        "greedy_walk": {
            "selected_indicators": selected,
            "selected_indicators_named": [
                {"code": c, "name": indicator_names.get(c)} for c in selected
            ],
            "chosen_window": chosen_window,
            "final_global_auc": go.get("final_global_auc"),
            "early_abort_floor_unreachable": go.get("early_abort_floor_unreachable", False),
            "history": greedy_history,
        },
        "coverage_audit": summary.get("coverage_audit"),
        "per_cohort": summary.get("per_cohort") or {},
        "architecture": summary.get("architecture"),
        "architecture_provenance": summary.get("architecture_provenance") or {},
        "borderline_lock": summary.get("borderline_lock", False),
        "temporal_confound_auc": summary.get("temporal_confound_auc"),
        "stability_diagnostic": summary.get("stability_diagnostic"),
        "per_recipe_floor_provenance": summary.get("per_recipe_floor_provenance") or {},
        "n_positives": summary.get("n_positives"),
        "n_negatives": summary.get("n_negatives"),
        "walked_at_utc": summary.get("filed"),
        "elapsed_seconds": summary.get("elapsed_seconds"),
        "raw_summary_s3": f"s3://{s3_bucket}/{ml_results_prefix}{rid}/f-ml-1-poc-summary.json",
        "score_distribution": score_distribution,  # filled by scores pass
        "indicator_sensitivity": {
            "computed": bool(sens_entries),
            "leave_one_out": sens_entries,
            "method": "5-fold-CV LOO ablation per #967",
        },
        "reliability_multipass": {
            "walks_completed": 1,
            "v1_separation_pp": _cohort_separation_pp(summary.get("per_cohort")),
            "v4_oot_recall_pct": None,  # needs a 2nd independent walk (fleet-run-2)
            "verdict": verdict,
        },
        "calibration": _calibration_block(summary),
        "per_country_scores_pointer": f"scores/{rid}.scores.json",
    }

    # NEW (frontend round-3 §1.5): shape_points + recipe-level SHAP importances
    if shap_data:
        card["shape_points"] = _compute_shape_points(shap_data, selected)
        card["shap_importance_raw"] = shap_data.get("shap_importance_raw") or {}
        card["shap_importance_normalized"] = shap_data.get("shap_importance_normalized") or {}
        card["shap_direction_signs"] = shap_data.get("shap_direction_signs") or {}
        card["per_feature_breakdown"] = shap_data.get("per_feature_breakdown") or {}
    else:
        card["shape_points"] = None
        card["shap_importance_raw"] = {}
        card["shap_importance_normalized"] = {}
        card["shap_direction_signs"] = {}
        card["per_feature_breakdown"] = {}

    # frontend bake-request B.1: canonical per-indicator movement shape, aggregated
    # from the walk summary's descriptive emit (5-sample interim; full-corpus at run-2)
    card["trajectory_alignment"] = _build_trajectory_alignment(summary, indicator_names)
    # frontend bake-request B.3: curated precedents corpus (events of this recipe's
    # category, each tagged whether it was a training positive). Empty {events:[],
    # total_events_in_corpus:0} when no verified-events input was supplied.
    card["precedents_corpus"] = precedents_corpus

    return card


def _compute_shape_points(shap_data: dict, selected: list[str]) -> list[float]:
    """Canonical 12-point z-score shape per recipe — composite of per-feature
    last_z + mean_z + std_z + slope across the selected indicators, weighted by
    SHAP normalized importance. Approximates the recipe's archetypal shape.
    (frontend §1.5 ask; real implementation belongs in score_countries upgrade.)
    """
    pfb = shap_data.get("per_feature_breakdown") or {}
    weights = shap_data.get("shap_importance_normalized") or {}
    if not pfb or not selected:
        return []
    # Build 12-point trajectory by interpolating from per-feature (last_z, mean_z, std_z, slope)
    # Each feature contributes: y(t) = mean_z + slope * (t - 5.5)  for t in 0..11
    pts = [0.0] * 12
    total_w = sum((weights.get(c) or 0) for c in selected) or 1.0
    for c in selected:
        b = pfb.get(c) or {}
        w = (weights.get(c) or 0) / total_w
        mean = b.get("mean_z") or 0
        slope = (b.get("slope") or 0) / 12.0  # spread slope across 12 points
        for t in range(12):
            pts[t] += w * (mean + slope * (t - 5.5))
    return pts


# ────────────────────────────────────────────────────────────────────────────
# Scores file builder
# ────────────────────────────────────────────────────────────────────────────

def build_scores_file(
    rid: str,
    vintage: str,
    country_scores: dict | None,
    countries: dict[str, dict[str, str]],
    indicator_names: dict[str, str],
    recipe_similarity: dict | None = None,
    sensitivity_data: dict | None = None,
    momentum_data: dict | None = None,
    nearest_analog_data: dict | None = None,
    panel_wide_z: dict | None = None,
    selected_indicators: list[str] | None = None,
    panel_root: Path | None = None,
    platform_roster: set[str] | None = None,
) -> dict | None:
    """Compose the scores file from country-scores.json (#967 output) with iso2 +
    indicator name + score_pp backfill + frontend round-3 enrichments:
    cosine_similarity_S + zone + sensitivity_per_indicator + momentum_scores_by_year +
    indicator_trajectory_composite_12q + countries_not_scored_iso."""
    if not country_scores:
        return None
    raw = country_scores.get("scores") or []
    if not raw:
        return None
    # Sort by score desc for rank assignment
    raw_sorted = sorted(raw, key=lambda e: -(e.get("score") or 0))
    n = len(raw_sorted)
    entries: list[dict] = []
    for rank, e in enumerate(raw_sorted, 1):
        name = e.get("country") or e.get("name") or ""
        iso2, iso3, flag = normalize_iso(name, countries)
        # SHAP attribution with friendly names (field names per frontend contract §4)
        shap_attr = []
        for s in (e.get("shap_attribution") or []):
            code = s.get("indicator") or s.get("code")
            shap_attr.append({
                "indicator_code": code,
                "indicator_name": indicator_names.get(code) if code else None,
                "signal_share_pct": s.get("signal_share_pct") or s.get("share_pct") or s.get("share"),
                # Raw shap_value pending score_countries.py upgrade (frontend §4 ask)
                "shap_value": s.get("shap_value"),
                # Provider hint via code-prefix heuristic (mirrors frontend's inferProvider)
                "provider": _provider_for(code),
            })
        # Indicator movement with friendly names + raw values from panel parquets
        movement = []
        eval_year = e.get("eval_year")
        for m in (e.get("indicator_movement") or []):
            code = m.get("indicator") or m.get("code")
            latest, prior, panel_provider = (None, None, None)
            if panel_root and code and eval_year and name:
                latest, prior, panel_provider = panel_lookup(panel_root, code, name, int(eval_year))
            movement.append({
                "indicator_code": code,
                "indicator_name": indicator_names.get(code) if code else None,
                "trajectory_12q": m.get("trajectory_12q") or [],
                "z_score_change": m.get("z_score_change"),
                # §A.2: carry the score-time trajectory_window (25y-baseline z, annual) +
                # its years through from the walk's country-scores. The bake REBUILDS this
                # entry, so without explicitly forwarding these they silently drop to []
                # even though score_countries emitted them (2026-06-01 finding).
                "trajectory_window": m.get("trajectory_window") or [],
                "trajectory_window_years": m.get("trajectory_window_years") or [],
                # Provider: prefer panel-resolved (explicit) over heuristic
                "provider": panel_provider or _provider_for(code),
                # Raw values from panel parquet (frontend §1.4)
                "latest_raw_value": latest,
                "prior_raw_value": prior,
                "unit": unit_hint_for(code),
            })

        # Indicator trajectory composite (frontend §1.1) — mean across selected
        # indicators' trajectory_12q.
        trajectories = [mv["trajectory_12q"] for mv in movement if mv["trajectory_12q"]]
        if trajectories:
            n_pts = min(len(t) for t in trajectories)
            indicator_trajectory_composite = [
                sum(t[i] for t in trajectories) / len(trajectories)
                for i in range(n_pts)
            ]
        else:
            indicator_trajectory_composite = []

        # Nearest analogs — enrichment via secondary_recipe_ids (cross-recipe)
        analogs = []
        for a in (e.get("nearest_analogs") or []):
            an_name = a.get("country") or a.get("name") or ""
            an_iso2, _, _ = normalize_iso(an_name, countries)
            an_year = a.get("year")
            # Pre-event indicator_trajectory_12q (frontend §1.1; closes gap #3)
            pre_event_traj = []
            if panel_root and selected_indicators and an_year:
                pre_event_traj = analog_pre_event_trajectory(
                    panel_root, selected_indicators, an_name, int(an_year), panel_wide_z,
                )
            analogs.append({
                "country": an_name,
                "country_iso2": an_iso2,
                "year": an_year,
                "match_score": a.get("match_score") or a.get("similarity"),
                "weak_analog": bool(a.get("weak_analog", False)),
                "what_happened_next": None,  # research workstream (ticket #974)
                "indicator_trajectory_12q": pre_event_traj,
                "secondary_recipe_ids": [],  # filled later via cross-recipe enrichment pass
            })

        score = e.get("score")
        score_pp = round(100.0 * (n - rank) / max(n - 1, 1), 2) if n > 1 else 50.0

        # Cosine similarity + zone from recipe-similarity-scores
        rs_entry = ((recipe_similarity or {}).get("scores") or {}).get(name) or {}
        cosine_S = rs_entry.get("cosine_similarity_S")
        zone = rs_entry.get("zone")
        zone_label = rs_entry.get("zone_label")

        # Sensitivity per indicator (frontend §1.4 marginal_points_per_unit)
        sens_pi = (((sensitivity_data or {}).get("sensitivity") or {}).get(name) or [])

        # Momentum scores_by_year (frontend §1.4 — vintage-1 multi-year history!)
        mom_entry = ((momentum_data or {}).get("results") or {}).get(name) or {}
        scores_by_year = mom_entry.get("scores_by_year") or {}
        momentum_label = mom_entry.get("label") or mom_entry.get("trend")

        entries.append({
            "iso": iso3,
            "iso2": iso2,
            "flag_emoji": flag,
            "name": name,
            "score": score,
            "rank": rank,
            "score_pp": score_pp,
            "eval_year": eval_year,
            "in_evidence_base": bool(e.get("in_evidence_base", False)),
            "delta_vs_prior_vintage": None,  # first vintage
            "shap_attribution": shap_attr,
            "indicator_movement": movement,
            "indicator_trajectory_composite_12q": indicator_trajectory_composite,
            "nearest_analogs": analogs,
            # NEW (frontend round-3 enrichments):
            "cosine_similarity_S": cosine_S,
            "zone": zone,
            "zone_label": zone_label,
            "sensitivity_per_indicator": sens_pi,
            "momentum_scores_by_year": scores_by_year,
            "momentum_label": momentum_label,
        })

    # countries_not_scored_iso (frontend §1.2) — roster diff
    scored_names = {e["name"] for e in entries}
    not_scored: list[dict] = []
    if platform_roster:
        for full_name in (platform_roster - scored_names):
            ns_iso2, _, _ = normalize_iso(full_name, countries)
            not_scored.append({"name": full_name, "iso2": ns_iso2})

    return {
        "recipe_id": rid,
        "vintage": vintage,
        "scored_at_utc": country_scores.get("scored_at_utc")
                          or country_scores.get("walked_at_utc")
                          or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "n_countries_scored": n,
        "n_countries_not_scored": len(not_scored),
        "countries_not_scored": not_scored,  # frontend §1.2
        "countries_not_scored_iso": [c["iso2"] for c in not_scored if c["iso2"]],
        "train_auc": country_scores.get("train_auc"),
        "cv_auc_full": country_scores.get("cv_auc_full"),
        "scoring_method": "XGBoost refit + SHAP TreeExplainer (per #967)",
        "scores": entries,
    }


def compute_score_distribution(scores_file: dict) -> dict:
    """20 bins of 5pp width with hover country list per bin (§9.14)."""
    entries = scores_file.get("scores") or []
    if not entries:
        return {"computed": False, "histogram": [], "median": None, "p90": None, "p99": None, "max": None, "n_countries_scored": 0}
    bins: list[dict] = []
    for i in range(20):
        lo, hi = i * 5, (i + 1) * 5
        in_bin = [e for e in entries if (lo <= (e.get("score") or 0) < hi) or (i == 19 and (e.get("score") or 0) == 100)]
        bins.append({
            "bin_lo": lo,
            "bin_hi": hi,
            "count": len(in_bin),
            "countries": [e.get("name") for e in in_bin],
            "country_isos": [e.get("iso2") for e in in_bin],
        })
    sorted_scores = sorted([(e.get("score") or 0) for e in entries])
    n = len(sorted_scores)

    def pct(p):
        if n == 0:
            return None
        idx = max(0, min(n - 1, int(p * n / 100)))
        return sorted_scores[idx]

    return {
        "computed": True,
        "histogram": bins,
        "median": pct(50),
        "p90": pct(90),
        "p99": pct(99),
        "max": sorted_scores[-1] if sorted_scores else None,
        "n_countries_scored": n,
        "source": "score_countries.py per-country eval",
    }


# ────────────────────────────────────────────────────────────────────────────
# Country-index builder (the big cross-recipe join)
# ────────────────────────────────────────────────────────────────────────────

def compound_score_v2(scores_per_country: list[float]) -> float:
    """V4.1 §8 + Sard consult formula:
      sqrt(N / (N + 2)) * sqrt(mean(score_i² for score_i ≥ 50))
    Bounded [0, 100]. Shrinks for thin coverage."""
    lit = [s for s in scores_per_country if s >= 50.0]
    if not lit:
        return 0.0
    N = len(lit)
    inner = sum(s * s for s in lit) / N
    return math.sqrt(N / (N + 2.0)) * math.sqrt(inner)


def build_country_index(
    all_scores: dict[str, dict],  # recipe_id → scores file dict
    all_cards: dict[str, dict],
    countries: dict[str, dict[str, str]],
    tracker: dict[str, dict[str, Any]],
    vintage: str,
    population_by_country: dict[str, int] | None = None,
) -> dict:
    """Aggregate every country across every recipe; produce CountryIndexEntry rows."""
    population_by_country = population_by_country or {}
    # country_name → {recipe_id → score_entry}
    by_country: dict[str, dict[str, dict]] = {}
    for rid, sf in all_scores.items():
        for e in (sf.get("scores") or []):
            name = e.get("name")
            if not name:
                continue
            by_country.setdefault(name, {})[rid] = e

    out_entries: list[dict] = []
    for name, recipe_scores in by_country.items():
        iso2, iso3, flag = normalize_iso(name, countries)
        region = region_for(iso2)

        # top_recipes (sorted by score desc)
        top_sorted = sorted(recipe_scores.items(), key=lambda kv: -(kv[1].get("score") or 0))
        top_recipes = []
        for rid, sc in top_sorted[:5]:
            card = all_cards.get(rid, {})
            tracker_row = tracker.get(rid) or {}
            l1_id = tracker_row.get("l1_id") or tracker_row.get("family_id") or ""
            top_recipes.append({
                "recipe_id": rid,
                "label": tracker_row.get("label") or rid.replace("_", " ").title(),
                "l1_id": l1_id,
                "l1_label": FAMILY_LABELS.get(l1_id, ""),
                "l1_color": tracker_row.get("l1_color") or "#888",
                "score": sc.get("score"),
                "status": card.get("recipe_status_audience") or "coming_soon",
            })

        # recipes_lit_count = recipes with score >= 50
        lit_scores = [sc.get("score") or 0 for sc in recipe_scores.values() if (sc.get("score") or 0) >= 50]
        lit_families = sorted({
            (tracker.get(rid) or {}).get("l1_id") or ""
            for rid, sc in recipe_scores.items()
            if (sc.get("score") or 0) >= 50
        } - {""})

        cs_v2 = compound_score_v2([sc.get("score") or 0 for sc in recipe_scores.values()])
        # Legacy compound_score: simple sum capped
        compound_legacy = sum(lit_scores)

        out_entries.append({
            "iso": iso3,
            "iso2": iso2,
            "flag_emoji": flag,
            "name": name,
            "region": region,
            "population": population_by_country.get(name),  # §C.1 from SP.POP.TOTL panel
            "vintage": vintage,
            "recipes_lit_count": len(lit_scores),
            "lit_families": list(lit_families),
            "compound_score": compound_legacy,
            "compound_score_v2": round(cs_v2, 2),
            "top_recipes": top_recipes,
            "drivers_attribution": None,
            "drivers_movement": None,
            "rank_history": [{"quarter": vintage, "rank_on_top_recipe": (top_sorted[0][1].get("rank") if top_sorted else None)}],
            "rank_history_notes": "First vintage; rank history accumulates from next quarterly run.",
            "analogs_pointer": "analogs/current-state-analogs.json",
            "compound_score_rank": 0,  # filled after sort
        })

    # Rank by compound_score_v2 desc
    out_entries.sort(key=lambda e: -e["compound_score_v2"])
    for i, e in enumerate(out_entries, 1):
        e["compound_score_rank"] = i

    # Region density rollup
    region_counts: dict[str, int] = {}
    for e in out_entries:
        r = e.get("region") or "Unknown"
        region_counts[r] = region_counts.get(r, 0) + 1

    return {
        "vintage": vintage,
        "platform_roster_size": 248,  # canonical UN-member-ish count for the roster
        "n_countries_scored": len(out_entries),
        "compound_score_formula": "sqrt(N/(N+2)) * sqrt(mean(score² for score ≥ 50))  (V4.1 §8 / Sard consult)",
        "coverage_density_per_region": region_counts,
        "countries": out_entries,
    }


# ────────────────────────────────────────────────────────────────────────────
# Analogs file builder (per-country top analogs across all recipes)
# ────────────────────────────────────────────────────────────────────────────

def build_analogs_file(
    all_scores: dict[str, dict],
    tracker: dict[str, dict[str, Any]],
    countries: dict[str, dict[str, str]],
    vintage: str,
) -> dict:
    """For each country, aggregate top analog matches across recipes."""
    # §D.1/§D.2 pre-pass: per-(recipe, country) current composite 12q z-trajectory,
    # copied straight from the scores files so analog sparklines embed it rather than
    # the frontend best-effort-joining it. `top_recipe` = each country's highest-scoring
    # recipe, used as its representative "current country" sparkline (§D.1).
    composite_by_rc: dict[tuple[str, str], Any] = {}
    top_recipe: dict[str, tuple[float, str]] = {}
    for rid, sf in all_scores.items():
        for e in (sf.get("scores") or []):
            nm = e.get("name")
            if not nm:
                continue
            composite_by_rc[(rid, nm)] = e.get("indicator_trajectory_composite_12q")
            sc_ = e.get("score") or 0
            if nm not in top_recipe or sc_ > top_recipe[nm][0]:
                top_recipe[nm] = (sc_, rid)

    by_country: dict[str, list[dict]] = {}
    contributions: dict[str, dict[str, dict]] = {}
    for rid, sf in all_scores.items():
        for e in (sf.get("scores") or []):
            name = e.get("name")
            if not name:
                continue
            for an in (e.get("nearest_analogs") or []):
                by_country.setdefault(name, []).append({
                    "country": an.get("country"),
                    "country_iso2": an.get("country_iso2"),
                    "year": an.get("year"),
                    "match_score": an.get("match_score"),
                    "primary_recipe_id": rid,
                    "what_happened_next": None,
                    "weak_analog": an.get("weak_analog", False),
                    # §D.2: embed the analog country's current composite (same recipe)
                    "indicator_trajectory_12q": composite_by_rc.get((rid, an.get("country"))),
                })
            # Track per-recipe contribution
            s = e.get("score") or 0
            if s >= 50:
                contributions.setdefault(name, {})[rid] = {
                    "recipe_id": rid,
                    "score": s,
                    "tracker_row": tracker.get(rid) or {},
                }

    entries: list[dict] = []
    for name, analogs in by_country.items():
        iso2, _, _ = normalize_iso(name, countries)
        region = region_for(iso2)
        # Sort + cap to top 5 analogs
        analogs_sorted = sorted(analogs, key=lambda a: -(a.get("match_score") or 0))[:5]
        # Contributions
        contr_list: list[dict] = []
        c_dict = contributions.get(name, {})
        total = sum(c.get("score") for c in c_dict.values()) or 1.0
        for rid, c in c_dict.items():
            tr = c["tracker_row"]
            l1_id = tr.get("l1_id") or ""
            contr_list.append({
                "recipe_id": rid,
                "recipe_label": tr.get("label") or rid.replace("_", " ").title(),
                "l1_color": tr.get("l1_color") or "#888",
                "contribution_pct": round(100.0 * (c.get("score") or 0) / total, 2),
                "status": "in_play",
            })
        contr_list.sort(key=lambda c: -c["contribution_pct"])
        # §D.1: the subject's "current country" sparkline = its composite from its
        # highest-scoring recipe (the country's most-lit pattern).
        tr_recipe = top_recipe.get(name, (0.0, None))[1]
        entries.append({
            "iso": None,
            "iso2": iso2,
            "name": name,
            "region": region,
            "indicator_trajectory": composite_by_rc.get((tr_recipe, name)) if tr_recipe else None,
            "analogs": analogs_sorted,
            "contributions": contr_list[:5],
        })

    return {"vintage": vintage, "entries": entries}


# ────────────────────────────────────────────────────────────────────────────
# Activity feed (walk_fired events from all 44 recipes)
# ────────────────────────────────────────────────────────────────────────────

def build_activity_feed(
    all_cards: dict[str, dict],
    tracker: dict[str, dict[str, Any]],
    vintage: str,
) -> dict:
    events: list[dict] = []
    # walk_fired events per card
    for rid, card in all_cards.items():
        tr = tracker.get(rid) or {}
        events.append({
            "kind": "walk_fired",
            "fired_at": card.get("walked_at_utc"),
            "recipe_id": rid,
            "recipe_label": tr.get("label") or rid.replace("_", " ").title(),
            "tier": card.get("tier"),
            "verdict": card.get("verdict"),
            "loco_auc": card.get("stats", {}).get("loco_auc"),
            "in_review_after": True,
            "note": f"Wave {('1+2' if rid in {'banking_and_financial_crisis','bilateral_treaty','diplomatic_rupture','economic_liberalization','economic_nationalization','ethnic_and_communal_conflict','fiscal_policy_change','government_formation','migration_and_refugees','terrorist_attack'} else '3' if rid != 'foreign_intervention' else 'foreign_intervention re-walk')} → first vintage of this recipe under the trajectory engine.",
        })
    # Hard-coded methodology event for the truncation-leak vacation
    events.append({
        "kind": "vacate",
        "fired_at": "2026-05-25T19:00:00+00:00",
        "recipe_id": "foreign_intervention",
        "recipe_label": "Foreign Intervention",
        "prior_status": "graduated",
        "vacated_at": "2026-05-25T19:00:00+00:00",
        "cause": "Sample-truncation leak: graduation LOCO 0.9147 was on 110/174 positives (~63% partial). Corrected full-corpus walk lands at 0.7227 (still above the 0.700 lock floor; not auto-graduating, not falsified).",
        "note": "Public correction live since 2026-05-25; re-walk under fixed instrument completed 2026-05-29T21:02Z (verdict MARGINAL_PENDING_BETA_CALIBRATION).",
    })
    # Methodology amendment events
    events.append({
        "kind": "methodology_amendment",
        "fired_at": "2026-05-25T13:00:00+00:00",
        "title": "Coverage- and chance-baseline gates added to F-ML-1 §3.4/§3.5",
        "detail": "8/8 Majles RATIFY-WITH-RIDER (MR-14-A1 / MR-14-A2 / T20-R3 NON-AMENDABLE first-re-walk-non-FI firewall). Closes the truncation-leak failure class.",
        "source": "docs/specs/internal/decisions/artifacts/F-ML-1-coverage-chance-gate-amendment-2026-05-25.md",
    })

    # Sort by fired_at desc
    events.sort(key=lambda e: e.get("fired_at") or "", reverse=True)

    return {
        "vintage": vintage,
        "events": events,
        "notes": {
            "first_vintage": "Walk_fired events are first-vintage signals; reliability tiles populate from the next quarterly run.",
        },
    }


# ────────────────────────────────────────────────────────────────────────────
# Main bake pipeline
# ────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--output-dir", type=Path, default=None,
                    help="Local FS output dir. Required when BAKE_MODE!=aws; "
                         "ignored when BAKE_MODE=aws (S3 prefix is used instead).")
    # accept str (not Path) so s3:// URIs aren't munged by pathlib; the
    # resolver function downloads if needed and returns a Path.
    ap.add_argument("--countries", type=str, required=True,
                    help="Local path OR s3:// URI to countries.json")
    ap.add_argument("--recipe-tracker", type=str, required=True,
                    help="Local path OR s3:// URI to recipe-tracker.json")
    ap.add_argument("--indicator-catalog", type=str, required=True,
                    help="Local path OR s3:// URI to indicator-catalog-detailed.md")
    ap.add_argument("--vintage", default="fleet-run-1-2026-05-30")
    ap.add_argument("--ml-results-prefix", default="ml-results/",
                    help="S3 prefix the per-recipe walk outputs are read from. Run-1 = "
                         "'ml-results/'; run-2 (Path A) wrote to 'ml-results-run2/'. MUST match "
                         "the run's ML_RESULTS_PREFIX or the bake reads the wrong vintage's data.")
    # MANIFEST provenance — per-vintage; default to run-1's values so an unflagged
    # invocation is byte-identical to the original run-1 bake (QA #143 FIX 1/2).
    ap.add_argument("--run-index", type=int, default=1,
                    help="Vintage ordinal in MANIFEST (frontend §1.3). run-1=1, run-2=2.")
    ap.add_argument("--image-digest",
                    default="sha256:b95ece033fb5f5ff6b4dcca7011f7a7a52747d864fbcac5cb7900ecd5f91c6f8",
                    help="Image digest stamped into MANIFEST provenance.")
    ap.add_argument("--image-tag", default="43f9d9bd",
                    help="Image tag stamped into MANIFEST provenance.")
    ap.add_argument("--qgi-ml-sha", default="9e764464c9074d0e5c351cd31603456b5b8ff434",
                    help="qgi-ml commit SHA stamped into MANIFEST provenance.")
    ap.add_argument("--panel-root", type=str, default="data/parquet_panels",
                    help="Panel parquet root for raw-value lookups (frontend §1.4). Local path "
                         "OR an s3:// prefix (parquet-completed/); the s3:// form is synced to a "
                         "local temp dir at startup (the image has no s3fs). str, not Path, so the "
                         "s3:// '//' survives argparse.")
    ap.add_argument("--verified-events", type=str, default=None,
                    help="Local path OR s3:// URI to verified-events.json (frontend §B.3 "
                         "precedents corpus, grouped by category==recipe_id). Optional; "
                         "precedents stay empty if omitted.")
    ap.add_argument("--shape-inputs-root", type=Path, default=Path("data/shape_inputs_v2"),
                    help="Root of per-recipe positives.csv ({root}/{recipe}/positives.csv) "
                         "for the precedents in_training_set flag (in the AWS image: "
                         "/app/data/shape_inputs_v2). Optional; flag degrades to False if absent.")
    ap.add_argument("--output-s3-prefix", default=None,
                    help="S3 key prefix under --bucket for AWS-mode writes. "
                         "Overrides OUTPUT_S3_PREFIX env-var if both are set. "
                         "Ignored in local mode.")
    args = ap.parse_args()

    # ── Output mode resolution (BAKE_MODE env-var; CLI flags assist) ──────
    mode = os.environ.get("BAKE_MODE", "local").strip().lower()
    if mode not in ("local", "aws"):
        LOG.error("Invalid BAKE_MODE=%r (expected 'local' or 'aws')", mode)
        return 2

    output_s3_prefix = ""
    if mode == "aws":
        output_s3_prefix = (args.output_s3_prefix
                            or os.environ.get("OUTPUT_S3_PREFIX", "")).strip()
        if not output_s3_prefix:
            LOG.error("BAKE_MODE=aws requires --output-s3-prefix or "
                      "OUTPUT_S3_PREFIX env-var")
            return 2
        if args.output_dir is None:
            args.output_dir = Path("/tmp/_bake_unused")  # stub; never written
    else:
        if args.output_dir is None:
            LOG.error("BAKE_MODE=local requires --output-dir")
            return 2

    # boto3 client is needed both for the reference-file s3:// resolver and
    # for the bake itself. Build it BEFORE loading reference files so the
    # resolver can use it.
    s3 = boto3.client("s3", region_name="eu-central-1")

    LOG.info("Loading resources...")
    # In AWS mode the Batch JobDef passes s3:// URIs for these 3 reference
    # files (countries / recipe-tracker / indicator-catalog) because they
    # aren't vendored in the qgi-recipe-fleet image. _resolve_reference_input
    # downloads to a temp file in that case; in local mode it's a no-op.
    args.countries = _resolve_reference_input(args.countries, s3)
    args.recipe_tracker = _resolve_reference_input(args.recipe_tracker, s3)
    args.indicator_catalog = _resolve_reference_input(args.indicator_catalog, s3)
    # --panel-root may be an s3:// prefix in AWS mode (no panels are baked into the
    # image and the bake job skips the walk entrypoint's panel sync). Sync to a local
    # dir so the panel-dependent fields (§C.1 population / §A.2 trajectory_window /
    # §1.4 raw values / §D analog trajectories) populate instead of silently nulling.
    args.panel_root = _sync_panel_root(args.panel_root, s3)

    countries = load_countries(args.countries)
    LOG.info("  %d countries", len(countries))
    tracker = load_recipe_tracker(args.recipe_tracker)
    LOG.info("  %d tracker rows", len(tracker))
    indicator_names = load_indicator_catalog(args.indicator_catalog)
    LOG.info("  %d indicator catalog entries", len(indicator_names))
    # §B.3 precedents: curated verified-events corpus (optional; s3:// resolved in AWS).
    if args.verified_events:
        args.verified_events = _resolve_reference_input(args.verified_events, s3)
    events_by_cat = _load_verified_events(args.verified_events)
    LOG.info("  %d recipe-categories in verified-events corpus", len(events_by_cat))
    if events_by_cat and not Path(args.shape_inputs_root).exists():
        LOG.warning("  shape-inputs-root %s not found — precedents in_training_set will be "
                    "all-False (pass --shape-inputs-root, e.g. /app/data/shape_inputs_v2)",
                    args.shape_inputs_root)

    recipe_ids = list_recipe_dirs(s3, args.bucket, args.ml_results_prefix)
    LOG.info("Discovered %d recipe dirs in S3 under %s", len(recipe_ids), args.ml_results_prefix)

    # In AWS mode, refuse-to-overwrite if MANIFEST.json already exists at the
    # target prefix (run-separation rule). This MUST happen before any artifact
    # write — fail loud, don't clobber a published vintage.
    if mode == "aws":
        try:
            _refuse_overwrite_if_baked(s3, args.bucket, output_s3_prefix)
        except RuntimeError as exc:
            LOG.error("%s", exc)
            return 3

    writer = _BakeOutput(
        mode=mode,
        output_dir=args.output_dir,
        s3_client=s3,
        bucket=args.bucket,
        prefix=output_s3_prefix,
    )
    LOG.info("BAKE_MODE=%s → writing to %s", mode, writer.describe_root())

    writer.mkdir()
    writer.mkdir("cards-v3")
    writer.mkdir("scores")
    writer.mkdir("countries")
    writer.mkdir("analogs")
    writer.mkdir("activity")

    all_cards: dict[str, dict] = {}
    all_scores: dict[str, dict] = {}

    # Platform roster from countries.json for countries_not_scored_iso derivation
    platform_roster = {entry["name"] for entry in countries.values()}

    # Eagerly import pandas if panel root exists (raw-value lookups need it)
    if args.panel_root.exists():
        import_pandas()

    mlp = args.ml_results_prefix  # read prefix (run-1 = ml-results/, run-2 = ml-results-run2/)

    def process_one(rid: str) -> tuple[str, dict | None, dict | None]:
        summary = s3_get_json(s3, args.bucket, f"{mlp}{rid}/f-ml-1-poc-summary.json")
        if not summary:
            return rid, None, None
        # Pull all sidecar artifacts in parallel (per-recipe inner-parallel via S3 SDK)
        sensitivity = s3_get_json(s3, args.bucket, f"{mlp}{rid}/sensitivity-{rid}-2026.json")
        country_scores = s3_get_json(s3, args.bucket, f"{mlp}{rid}/country-scores.json")
        recipe_similarity = s3_get_json(s3, args.bucket, f"{mlp}{rid}/recipe-similarity-scores-{rid}-2026.json")
        nearest_analog_full = s3_get_json(s3, args.bucket, f"{mlp}{rid}/nearest-analog-{rid}-2026.json")
        momentum = s3_get_json(s3, args.bucket, f"{mlp}{rid}/momentum-{rid}-2026.json")
        shap_imp = s3_get_json(s3, args.bucket, f"{mlp}{rid}/shap-importances-{rid}.json")
        panel_wide_z = s3_get_json(s3, args.bucket, f"{mlp}{rid}/panel-wide-z-distribution-2026.json")
        tracker_row = tracker.get(rid)
        selected_indicators = (summary.get("greedy_outer_loop") or {}).get("selected_indicators") or []
        precedents = _build_precedents_corpus(
            rid, events_by_cat, _load_positives_set(args.shape_inputs_root, rid), countries)
        card = build_card_v3(
            summary, sensitivity, indicator_names, tracker_row, args.bucket,
            shap_data=shap_imp, panel_root=args.panel_root, precedents_corpus=precedents,
            ml_results_prefix=mlp,
        )
        scores_file = build_scores_file(
            rid, args.vintage, country_scores, countries, indicator_names,
            recipe_similarity=recipe_similarity, sensitivity_data=sensitivity,
            momentum_data=momentum, nearest_analog_data=nearest_analog_full,
            panel_wide_z=panel_wide_z, selected_indicators=selected_indicators,
            panel_root=args.panel_root if args.panel_root.exists() else None,
            platform_roster=platform_roster,
        )
        if scores_file:
            card["score_distribution"] = compute_score_distribution(scores_file)
        return rid, card, scores_file

    LOG.info("Building cards + scores per recipe (parallel S3 fetches)...")
    with ThreadPoolExecutor(max_workers=8) as ex:
        for rid, card, scores_file in ex.map(process_one, recipe_ids):
            if card is None:
                LOG.warning("  %s: no summary; skipped", rid)
                continue
            all_cards[rid] = card
            writer.write_text(f"cards-v3/{rid}.card.json", json.dumps(card, indent=2, default=str))
            if scores_file:
                all_scores[rid] = scores_file
                writer.write_text(f"scores/{rid}.scores.json", json.dumps(scores_file, indent=2, default=str))
            else:
                LOG.info("  %s: no country-scores.json (likely pre-image-rebuild walk; scores skipped)", rid)

    # Cross-recipe enrichment: fill secondary_recipe_ids on each analog by
    # looking up which OTHER recipes also have the same (analog_country, year)
    # as a high-score analog.
    LOG.info("Cross-recipe secondary_recipe_ids enrichment...")
    analog_to_recipes: dict[tuple, list[str]] = {}
    for rid, sf in all_scores.items():
        for e in sf.get("scores", []):
            for a in e.get("nearest_analogs", []):
                key = (a.get("country"), a.get("year"))
                if key[0] and key[1]:
                    analog_to_recipes.setdefault(key, []).append(rid)
    for rid, sf in all_scores.items():
        for e in sf.get("scores", []):
            for a in e.get("nearest_analogs", []):
                key = (a.get("country"), a.get("year"))
                # Dedup while preserving order
                seen = set()
                others = []
                for r in analog_to_recipes.get(key, []):
                    if r != rid and r not in seen:
                        others.append(r)
                        seen.add(r)
                a["secondary_recipe_ids"] = others[:5]
        writer.write_text(f"scores/{rid}.scores.json", json.dumps(sf, indent=2, default=str))

    # Emit country-rank-history.json (frontend §1.4 highest priority — vintage 1)
    LOG.info("Emitting country-rank-history.json (vintage-1)...")
    rank_history_rows: list[dict] = []
    for rid, sf in all_scores.items():
        for e in sf.get("scores", []):
            rank_history_rows.append({
                "vintage": args.vintage,
                "recipe_id": rid,
                "country": e["name"],
                "country_iso2": e.get("iso2"),
                "score": e.get("score"),
                "rank": e.get("rank"),
                "n_countries_scored": sf.get("n_countries_scored"),
            })
    rank_history = {
        "vintage": args.vintage,
        "produced_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "schema_note": "Append-only across vintages. Cross-vintage delta panels join by (recipe_id, country) and order by vintage.",
        "n_rows": len(rank_history_rows),
        "rows": rank_history_rows,
    }
    writer.mkdir("countries")
    writer.write_text(
        "countries/country-rank-history.json",
        json.dumps(rank_history, indent=2, default=str),
    )
    LOG.info("  %d rank-history rows emitted", len(rank_history_rows))

    LOG.info("Built %d cards, %d scores files", len(all_cards), len(all_scores))

    LOG.info("Building country-index...")
    population_by_country = _load_population(args.panel_root if args.panel_root.exists() else None)
    LOG.info("  %d countries with population from the SP.POP.TOTL panel", len(population_by_country))
    country_index = build_country_index(all_scores, all_cards, countries, tracker, args.vintage,
                                        population_by_country=population_by_country)
    writer.write_text("countries/country-index.json", json.dumps(country_index, indent=2, default=str))
    LOG.info("  %d countries indexed", country_index["n_countries_scored"])

    LOG.info("Building analogs file...")
    analogs_file = build_analogs_file(all_scores, tracker, countries, args.vintage)
    writer.write_text("analogs/current-state-analogs.json", json.dumps(analogs_file, indent=2, default=str))
    LOG.info("  %d analog entries", len(analogs_file["entries"]))

    LOG.info("Building activity feed...")
    activity = build_activity_feed(all_cards, tracker, args.vintage)
    writer.write_text("activity/program-feed.json", json.dumps(activity, indent=2, default=str))
    LOG.info("  %d events", len(activity["events"]))

    # Indicator corpus breakdown: count of UNIQUE indicators by provider seen
    # across all walks (frontend §1.3 — what they want is the corpus inventory,
    # not the per-walk selection tally).
    seen_per_provider: dict[str, set[str]] = {}
    for card in all_cards.values():
        for ind in (card.get("greedy_walk", {}).get("selected_indicators") or []):
            p = _provider_for(ind) or "Other"
            seen_per_provider.setdefault(p, set()).add(ind)
    provider_tally = {p: len(s) for p, s in seen_per_provider.items()}

    # MANIFEST
    manifest = {
        "vintage": args.vintage,
        "run_index": args.run_index,  # frontend §1.3 — per-vintage; pass --run-index (run-2 = 2)
        "produced_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "engine": "F-ML-1 / Trajectory Engine (ML2)",
        "n_recipes": len(all_cards),
        "n_scores_files": len(all_scores),
        "n_countries_indexed": country_index["n_countries_scored"],
        "indicator_catalog_size": len(indicator_names),  # frontend §1.3
        "indicator_corpus_breakdown": provider_tally,    # frontend §1.3
        "contract_version": CONTRACT_VERSION,
        "image_digest": args.image_digest,  # provenance — pass per-run; defaults to run-1's
        "image_tag": args.image_tag,
        "qgi_ml_sha": args.qgi_ml_sha,
        "bucket_a_enrichments_applied": [
            "iso2/iso3/flag_emoji on scores + analogs",
            "region on country-index",
            "indicator name on every shap_attribution + indicator_sensitivity entry",
            "description_compelling from recipe-tracker.json",
            "family_label from recipe-tracker.json (letter glyph dropped)",
            "recipe_status_audience derived from pipeline verdict",
            "histogram[].countries[] on score_distribution",
            "score_pp + n_countries_scored on scores file",
            "compound_score_v2_per_country on country-index",
            "engine: trajectory-engine-v1 on every card",
            "coverage_density_per_region on country-index",
        ],
        "verdict_counts": {},
        "tier_counts": {},
    }
    for card in all_cards.values():
        v = card.get("verdict") or "UNKNOWN"
        manifest["verdict_counts"][v] = manifest["verdict_counts"].get(v, 0) + 1
        t = card.get("tier") or "UNKNOWN"
        manifest["tier_counts"][t] = manifest["tier_counts"].get(t, 0) + 1
    writer.write_text("MANIFEST.json", json.dumps(manifest, indent=2, default=str))

    LOG.info("=== BAKE COMPLETE ===")
    LOG.info("Output: %s", writer.describe_root())
    LOG.info("Verdict counts: %s", manifest["verdict_counts"])
    LOG.info("Tier counts:    %s", manifest["tier_counts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
