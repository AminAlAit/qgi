"""Chunk C.1 — Data preparation for Stage 6 shape-feature fitter.

Produces event-aligned, per-country z-score-normalized indicator panels for
the Phase 1 recipe trio, ready for consumption by
``scripts/fit_shape_prototype.py`` (Chunk B).

**Authority lineage:**
  Stage 6 pre-reg §3.2 (end-alignment + indicator-level normalization)
  + §3.2.2 (BASELINE_TOO_SHORT rule) + Tariq's substrate audit
  (``docs/specs/internal/ops/ml-track/results/substrate-audit-phase-1.json``).

**CLI:**

Single-recipe mode::

    python scripts/prepare_shape_input_panels.py \\
        --recipe civil_war_and_insurgency \\
        --output-dir data/shape_inputs \\
        [--canonical-length 5] \\
        [--key-indicators path/to/substrate-audit-phase-1.json]

Batch mode (all Phase 1 recipes)::

    python scripts/prepare_shape_input_panels.py --batch phase-1

**Output per recipe** in ``<output-dir>/<recipe_id>/``:
  * ``positives_aligned.parquet``  — long-format (country_id, instance_idx,
    indicator_id, t_offset, y_normalized), sorted deterministically.
  * ``prep_manifest.json``         — counts, dropout reasons, coverage stats,
    source SHAs, prep commit SHA.
  * ``prep_log.md``                — human-readable summary.

**Fitter input contract** (``fit_shape_prototype.py``)::

    --indicator-panel  <path>   long-format parquet: country_id, year,
                                indicator_id, value
    --positive-instances <path> CSV: country_id, event_year

This script also emits ``indicator_panel.parquet`` and
``positives.csv`` in the per-recipe output directory so the caller can
pass them directly to the fitter.

R4 binding: no AWS calls. All data loaded from local parquet/JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("prepare_shape_input_panels")

# ---------------------------------------------------------------------------
# Repo layout constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
QGDATA_ROOT = REPO_ROOT.parent / "qgi-data"

# Local indicator panel paths (Tariq's audit scope: union of both parquets).
PANEL_PATHS = [
    REPO_ROOT / "data" / "all_104_panels.parquet",
    REPO_ROOT / "data" / "i1_panels.parquet",
]

EVENTS_DIR = QGDATA_ROOT / "events" / "curated"
SUBSTRATE_AUDIT_PATH = (
    QGDATA_ROOT.parent
    / "docs-specs"
    / "internal"
    / "ops"
    / "ml-track"
    / "results"
    / "substrate-audit-phase-1.json"
)

# Training window: all (country, event_year) with event_year <= TRAIN_MAX.
TRAIN_MAX_YEAR = 2021
TRAIN_MIN_YEAR = 1789  # per Tariq's audit scope

# Normalization: 20-year pre-window baseline per §3.2.2.
BASELINE_YEARS = 20

# sigma_min multiplier (§3.2.2): 1e-3 * median(sigma_c')
SIGMA_MIN_MULTIPLIER = 1e-3

# Phase 1 recipe trio (founder-picked 2026-05-17).
PHASE_1_RECIPES = [
    "civil_war_and_insurgency",
    "economic_recession",
    "foreign_intervention",
]

# ---------------------------------------------------------------------------
# Country name normalization  (panel uses title-case; events use slug)
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert a panel country name to the canonical slug used in event files.

    Matches the slug function in ``_audit_script.py`` (Tariq, 2026-05-17).
    """
    return (
        name.lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("'", "")
        .replace("&", "and")
        .replace(".", "")
        .replace(",", "")
    )


# Panel-name slug → event-file slug overrides (handling WB naming conventions).
_PANEL_SLUG_OVERRIDES: dict[str, str] = {
    "turkey": "turkiye",
    "cape_verde": "cabo_verde",
    "congo_rep": "republic_of_congo",
    "the_democratic_republic_of_the_congo": "democratic_republic_of_congo",
    "republic_of_the_congo": "republic_of_congo",
    "democratic_republic_of_the_congo": "democratic_republic_of_congo",
    "egypt_arab_rep": "egypt",
    "iran_islamic_rep": "iran",
    "syrian_arab_republic": "syria",
    "venezuela_rb": "venezuela",
    "korea_rep": "south_korea",
    "korea_dem_peoples_rep": "north_korea",
    "yemen_rep": "yemen",
    "cote_divoire": "ivory_coast",
    "kyrgyz_republic": "kyrgyzstan",
    "lao_pdr": "laos",
    "slovak_republic": "slovakia",
    "russian_federation": "russia",
    "czech_republic": "czechia",
    "gambia_the": "gambia",
    "bahamas_the": "bahamas",
    "micronesia_fed_sts": "micronesia",
    "macedonia_fyr": "north_macedonia",
    "st_lucia": "saint_lucia",
    "st_kitts_and_nevis": "saint_kitts_and_nevis",
    "st_vincent_and_the_grenadines": "saint_vincent_and_the_grenadines",
}

# Reverse map: event-file slug → canonical panel country_id (for the fitter).
# The canonical country_id is the slug itself; this map is applied after
# slugification so events and panel rows share the same country_id space.
_EVENT_SLUG_TO_PANEL_SLUG: dict[str, str] = {}
# Invert _PANEL_SLUG_OVERRIDES
for _panel_slug, _event_slug in _PANEL_SLUG_OVERRIDES.items():
    _EVENT_SLUG_TO_PANEL_SLUG[_event_slug] = _panel_slug


def _panel_country_to_id(panel_name: str) -> str:
    """Convert a panel ``country`` value to a canonical country_id slug."""
    raw = _slugify(panel_name)
    return _PANEL_SLUG_OVERRIDES.get(raw, raw)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_commit_sha(repo_path: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown-sha"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_df(df: pd.DataFrame) -> str:
    """Stable SHA-256 over a DataFrame using Parquet binary serialization."""
    buf = io.BytesIO()
    try:
        df.to_parquet(buf, index=False)
        return hashlib.sha256(buf.getvalue()).hexdigest()
    except Exception:  # noqa: BLE001
        return hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Panel loading
# ---------------------------------------------------------------------------


def load_combined_panel() -> pd.DataFrame:
    """Load the union of local indicator parquet snapshots.

    Returns a long-format DataFrame with columns:
    ``country_id`` (slug), ``year`` (int), ``indicator_id``, ``value``.

    The ``country`` column from the parquet files is translated to
    ``country_id`` via ``_panel_country_to_id``.
    """
    frames: list[pd.DataFrame] = []
    for p in PANEL_PATHS:
        if not p.exists():
            logger.warning("Panel file not found (skip): %s", p)
            continue
        df = pd.read_parquet(p)
        logger.info("Loaded %s: %d rows, %d unique indicators", p.name, len(df), df["indicator_id"].nunique())
        frames.append(df)

    if not frames:
        raise FileNotFoundError(
            f"No panel files found. Searched: {[str(p) for p in PANEL_PATHS]}"
        )

    combined = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["country", "year", "indicator_id"]
    )

    # Translate panel country name → country_id slug.
    combined["country_id"] = combined["country"].apply(_panel_country_to_id)

    combined = combined[["country_id", "year", "indicator_id", "value"]].copy()
    combined["year"] = combined["year"].astype(int)
    combined["value"] = pd.to_numeric(combined["value"], errors="coerce")

    logger.info(
        "Combined panel: %d rows, %d unique indicators, %d unique countries",
        len(combined),
        combined["indicator_id"].nunique(),
        combined["country_id"].nunique(),
    )
    return combined


# ---------------------------------------------------------------------------
# Curated-event loading
# ---------------------------------------------------------------------------


def load_positive_instances(recipe_id: str) -> list[tuple[str, int]]:
    """Load all (country_id, event_year) pairs for ``recipe_id`` from curated events.

    Returns pairs with event_year in [TRAIN_MIN_YEAR, TRAIN_MAX_YEAR],
    deduplicated. Country_id is the event-file slug, which is the canonical
    country_id used throughout this script.
    """
    if not EVENTS_DIR.exists():
        raise FileNotFoundError(f"Events directory not found: {EVENTS_DIR}")

    pairs: list[tuple[str, int]] = []
    for event_file in sorted(EVENTS_DIR.iterdir()):
        if not event_file.suffix == ".json":
            continue
        if event_file.stem.startswith("_"):
            continue
        if "curation_report" in event_file.name:
            continue

        country_slug = event_file.stem
        try:
            events = json.loads(event_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping %s (parse error: %s)", event_file.name, exc)
            continue

        if not isinstance(events, list):
            continue

        for ev in events:
            if ev.get("category") != recipe_id:
                continue
            year = ev.get("year")
            if year is None:
                continue
            year = int(year)
            if TRAIN_MIN_YEAR <= year <= TRAIN_MAX_YEAR:
                pairs.append((country_slug, year))

    # Deduplicate preserving one entry per (country, year) — multiple events
    # in the same year collapse to one shape-feature instance (§3.2.1).
    seen: set[tuple[str, int]] = set()
    deduped: list[tuple[str, int]] = []
    for pair in pairs:
        if pair not in seen:
            seen.add(pair)
            deduped.append(pair)

    logger.info(
        "Loaded %d raw events for recipe=%s, deduplicated to %d (country, year) pairs",
        len(pairs),
        recipe_id,
        len(deduped),
    )
    return sorted(deduped)


# ---------------------------------------------------------------------------
# Key-indicator loading from substrate audit
# ---------------------------------------------------------------------------


def load_key_indicators(recipe_id: str, audit_path: Path | None = None) -> list[str]:
    """Load the key indicator IDs for ``recipe_id`` from the substrate audit JSON.

    Per Tariq's audit (``substrate-audit-phase-1.json``), the ``key_indicators``
    field lists indicator codes WITHOUT the ``__diff`` suffix used in the SHAP
    fingerprint. This function returns the codes as-is from the audit JSON.
    """
    path = audit_path or SUBSTRATE_AUDIT_PATH
    if not path.exists():
        raise FileNotFoundError(f"Substrate audit JSON not found: {path}")

    audit = json.loads(path.read_text(encoding="utf-8"))
    recipe_block = audit.get("recipes", {}).get(recipe_id)
    if recipe_block is None:
        raise KeyError(
            f"Recipe '{recipe_id}' not found in substrate audit. "
            f"Available: {list(audit['recipes'].keys())}"
        )
    indicators = recipe_block.get("key_indicators", [])
    if not indicators:
        raise ValueError(f"No key_indicators in substrate audit for recipe={recipe_id}")
    logger.info("Key indicators for %s (%d): %s", recipe_id, len(indicators), indicators)
    return list(indicators)


# ---------------------------------------------------------------------------
# BASELINE_TOO_SHORT filter (§3.2.2)
# ---------------------------------------------------------------------------

_DropoutRecord = dict[str, Any]


def _check_baseline_too_short(
    panel_indexed: pd.DataFrame,
    country_id: str,
    event_year: int,
    canonical_length_T: int,
    indicator_ids: list[str],
) -> str | None:
    """Return the dropout reason string, or None if the instance is OK.

    §3.2.2: drop if ANY key indicator has < 20 pre-window observation years.
    The pre-window baseline spans [event_year - T_r - 20, event_year - T_r - 1].
    All 20 years must be present for the instance to survive.
    """
    baseline_start = event_year - canonical_length_T - BASELINE_YEARS
    baseline_end = event_year - canonical_length_T - 1

    for iid in indicator_ids:
        try:
            sub = panel_indexed.loc[(country_id, slice(baseline_start, baseline_end), iid), :]
        except KeyError:
            return f"BASELINE_TOO_SHORT:{iid} (country not in panel)"

        # Count non-NaN observations in the baseline window.
        n_obs = sub["value"].notna().sum()
        if n_obs < BASELINE_YEARS:
            return (
                f"BASELINE_TOO_SHORT:{iid} "
                f"(n_obs={n_obs}<{BASELINE_YEARS}, "
                f"baseline=[{baseline_start},{baseline_end}])"
            )
    return None


# ---------------------------------------------------------------------------
# Per-country z-score normalization (§3.2.2)
# ---------------------------------------------------------------------------


def _compute_sigma_min(
    sigma_values: list[float],
) -> float:
    """Compute sigma_min = 1e-3 * median(sigma_c') across countries.

    Used as the denominator floor in §3.2.2.

    Edge cases:
    - Empty list (no countries with baseline data): return 1e-3 (1e-3 * 1.0
      surrogate, matches shape_prototype_fit_utils fallback of 1e-6 direction).
    - All-zero sigmas (near-constant baseline across all countries): median = 0
      → sigma_min = 0 would fail as a floor. Floor at 1e-6 in that case,
      matching the ``sigma_floor = 1e-6`` fallback in per_country_z_score
      (shape_prototype_fit_utils.py line 338).
    """
    if not sigma_values:
        return SIGMA_MIN_MULTIPLIER  # fallback: 1e-3 * 1.0
    median_val = float(np.median(sigma_values))
    computed = SIGMA_MIN_MULTIPLIER * median_val
    # Ensure the floor is always strictly positive so division never produces inf.
    return max(computed, 1e-6)


def _normalize_trajectory(
    raw_trajectory: np.ndarray,
    mu_c: float,
    sigma_c: float,
    sigma_min: float,
) -> np.ndarray:
    """Apply per-country z-score normalization per §3.2.2.

    y = (x - mu_c) / max(sigma_c, sigma_min)
    """
    denom = max(sigma_c, sigma_min)
    return (raw_trajectory - mu_c) / denom


# ---------------------------------------------------------------------------
# Main per-recipe preparation
# ---------------------------------------------------------------------------


def prepare_recipe(
    recipe_id: str,
    *,
    output_dir: Path,
    canonical_length_T: int | None = None,
    key_indicators_path: Path | None = None,
    panel: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Prepare the aligned + normalized input panels for one recipe.

    Steps:
      a. Load key indicator set from substrate audit.
      b. Load positive instances from curated events.
      c. Load indicator panel from local parquet.
      d. Apply BASELINE_TOO_SHORT dropouts (§3.2.2).
      e. End-align trajectories (§3.2.1): extract t in {-T_r, ..., -1}.
      f. Per-country pre-event 20-year z-score normalize (§3.2.2).
      g. Emit positives_aligned.parquet + indicator_panel.parquet +
         positives.csv + prep_manifest.json + prep_log.md.

    Returns a dict of summary statistics for reporting.
    """
    # ---- (a) Key indicators -----------------------------------------------
    key_indicators = load_key_indicators(recipe_id, audit_path=key_indicators_path)

    # ---- T_r ------------------------------------------------------------------
    # Default from substrate audit; caller may override.
    if canonical_length_T is None:
        audit_path = key_indicators_path or SUBSTRATE_AUDIT_PATH
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        T_r = int(audit["recipes"][recipe_id].get("canonical_length_T", 5))
    else:
        T_r = canonical_length_T
    logger.info("Recipe=%s T_r=%d", recipe_id, T_r)

    # ---- (b) Positive instances -------------------------------------------
    positives_raw = load_positive_instances(recipe_id)
    n_pos_input = len(positives_raw)
    logger.info("n_pos_input=%d", n_pos_input)

    # ---- (c) Indicator panel -----------------------------------------------
    if panel is None:
        panel = load_combined_panel()

    # Check indicator coverage.
    available_in_panel = sorted(
        set(key_indicators) & set(panel["indicator_id"].unique())
    )
    missing_from_panel = sorted(
        set(key_indicators) - set(panel["indicator_id"].unique())
    )
    logger.info(
        "Indicator coverage: %d/%d available locally; missing: %s",
        len(available_in_panel),
        len(key_indicators),
        missing_from_panel,
    )
    if not available_in_panel:
        raise RuntimeError(
            f"Zero key indicators for recipe={recipe_id} found in local panel. "
            f"Missing: {missing_from_panel}. "
            f"Cannot proceed — check data layout (BLOCKER)."
        )

    # Filter panel to key indicators only (speeds up subsequent lookups).
    panel_filtered = panel[panel["indicator_id"].isin(available_in_panel)].copy()

    # Build a multi-index for fast baseline/window lookups.
    panel_filtered = panel_filtered.sort_values(["country_id", "year", "indicator_id"])
    panel_indexed = panel_filtered.set_index(["country_id", "year", "indicator_id"])

    # ---- Resolve event-slug → panel country_id ----------------------------
    # Event files use lowercase slug; panel uses its own country_id.
    # Some event slugs map directly; others need the reverse override table.
    panel_countries = set(panel_filtered["country_id"].unique())

    def _resolve_country(event_slug: str) -> str | None:
        """Map an event-file slug to the panel's country_id.

        The panel's country_id space is already slugified (via
        _panel_country_to_id). Some event slugs are identical to panel
        country_ids; others need the _PANEL_SLUG_OVERRIDES reverse map.
        """
        # Direct match (most countries).
        if event_slug in panel_countries:
            return event_slug
        # Try the reverse override map (e.g. democratic_republic_of_congo
        # → the_democratic_republic_of_the_congo_slug → panel entry).
        panel_slug = _EVENT_SLUG_TO_PANEL_SLUG.get(event_slug)
        if panel_slug and panel_slug in panel_countries:
            return panel_slug
        # Not resolvable.
        return None

    # ---- (d) BASELINE_TOO_SHORT filter ------------------------------------
    dropouts: list[_DropoutRecord] = []
    surviving_pairs: list[tuple[str, int, str]] = []  # (panel_country_id, event_year, event_slug)

    # We filter using AVAILABLE indicators only (not missing ones).
    # A country is only dropped if a locally-AVAILABLE indicator fails the
    # baseline check.  Missing indicators are documented in coverage stats.
    for event_slug, event_year in positives_raw:
        panel_cid = _resolve_country(event_slug)
        if panel_cid is None:
            dropouts.append({
                "country_id": event_slug,
                "event_year": event_year,
                "reason": "COUNTRY_NOT_IN_PANEL",
            })
            continue

        reason = _check_baseline_too_short(
            panel_indexed, panel_cid, event_year, T_r, available_in_panel
        )
        if reason:
            dropouts.append({
                "country_id": panel_cid,
                "event_year": event_year,
                "reason": reason,
            })
        else:
            surviving_pairs.append((panel_cid, event_year, event_slug))

    n_country_not_in_panel = sum(1 for d in dropouts if d["reason"] == "COUNTRY_NOT_IN_PANEL")
    n_baseline_too_short = sum(1 for d in dropouts if d["reason"].startswith("BASELINE_TOO_SHORT"))
    n_pos_after_dropouts = len(surviving_pairs)

    logger.info(
        "After BASELINE_TOO_SHORT filter: %d kept, %d dropped "
        "(%d COUNTRY_NOT_IN_PANEL, %d BASELINE_TOO_SHORT)",
        n_pos_after_dropouts,
        len(dropouts),
        n_country_not_in_panel,
        n_baseline_too_short,
    )

    # ---- (e, f) End-align + z-score normalize --------------------------------
    # First pass: collect all per-country sigma values per indicator
    # so we can compute sigma_min across countries (§3.2.2).
    sigma_values_per_indicator: dict[str, list[float]] = {iid: [] for iid in available_in_panel}

    for panel_cid, event_year, _ in surviving_pairs:
        for iid in available_in_panel:
            baseline_start = event_year - T_r - BASELINE_YEARS
            baseline_end = event_year - T_r - 1
            try:
                sub = panel_indexed.loc[
                    (panel_cid, slice(baseline_start, baseline_end), iid), "value"
                ].dropna()
            except KeyError:
                continue
            if len(sub) >= 2:
                sigma_values_per_indicator[iid].append(float(np.std(sub.values, ddof=1)))

    sigma_min_per_indicator = {
        iid: _compute_sigma_min(sigma_values_per_indicator[iid])
        for iid in available_in_panel
    }

    # Second pass: extract aligned trajectories + normalize.
    rows: list[dict[str, Any]] = []
    alignment_dropouts: list[_DropoutRecord] = []

    for instance_idx, (panel_cid, event_year, event_slug) in enumerate(surviving_pairs):
        instance_ok = True
        instance_rows: list[dict[str, Any]] = []

        for iid in available_in_panel:
            # Baseline.
            baseline_start = event_year - T_r - BASELINE_YEARS
            baseline_end = event_year - T_r - 1
            try:
                sub_base = panel_indexed.loc[
                    (panel_cid, slice(baseline_start, baseline_end), iid), "value"
                ].dropna()
            except KeyError:
                alignment_dropouts.append({
                    "country_id": panel_cid,
                    "event_year": event_year,
                    "reason": f"BASELINE_LOOKUP_FAILED:{iid}",
                })
                instance_ok = False
                break

            if len(sub_base) < BASELINE_YEARS:
                # Double-check caught by pass-1 above; belt-and-suspenders.
                alignment_dropouts.append({
                    "country_id": panel_cid,
                    "event_year": event_year,
                    "reason": f"BASELINE_TOO_SHORT_ALIGN:{iid} n={len(sub_base)}",
                })
                instance_ok = False
                break

            mu_c = float(sub_base.mean())
            sigma_c = float(sub_base.std(ddof=1))

            # Alignment window: t in {event_year - T_r, ..., event_year - 1}.
            # Event year EXCLUDED (§3.2.1).
            for t_abs in range(event_year - T_r, event_year):
                t_offset = t_abs - event_year  # negative: t in {-T_r, ..., -1}
                try:
                    val = panel_indexed.loc[(panel_cid, t_abs, iid), "value"]
                    raw_val = float(val) if pd.notna(val) else np.nan
                except KeyError:
                    raw_val = np.nan

                if np.isnan(raw_val):
                    y_norm = np.nan
                else:
                    y_norm = _normalize_trajectory(
                        np.array([raw_val]),
                        mu_c,
                        sigma_c,
                        sigma_min_per_indicator[iid],
                    )[0]

                instance_rows.append({
                    "country_id": panel_cid,
                    "event_slug": event_slug,
                    "instance_idx": instance_idx,
                    "indicator_id": iid,
                    "t_offset": t_offset,
                    "y_normalized": y_norm,
                })

        if instance_ok:
            rows.extend(instance_rows)
        else:
            logger.debug(
                "Alignment dropout: country=%s event_year=%d", panel_cid, event_year
            )

    n_alignment_dropouts = len(alignment_dropouts)
    n_final_instances = len(surviving_pairs) - n_alignment_dropouts
    logger.info(
        "Final instances: %d (alignment dropouts: %d)",
        n_final_instances,
        n_alignment_dropouts,
    )

    # ---- Build output DataFrames ------------------------------------------
    aligned_df = pd.DataFrame(rows)
    if aligned_df.empty:
        aligned_df = pd.DataFrame(
            columns=[
                "country_id", "event_slug", "instance_idx",
                "indicator_id", "t_offset", "y_normalized",
            ]
        )
    else:
        # Deterministic sort (§ idempotency requirement).
        aligned_df = aligned_df.sort_values(
            ["country_id", "instance_idx", "indicator_id", "t_offset"]
        ).reset_index(drop=True)

    # Positives CSV (fitter contract: country_id, event_year).
    # One row per surviving instance that completed alignment.
    # Derive from the instance_idx set present in aligned_df.
    if not aligned_df.empty:
        valid_idxs = set(aligned_df["instance_idx"].unique())
        positives_df = pd.DataFrame(
            [
                {"country_id": panel_cid, "event_year": event_year}
                for idx, (panel_cid, event_year, _) in enumerate(surviving_pairs)
                if idx in valid_idxs
            ]
        )
    else:
        positives_df = pd.DataFrame(columns=["country_id", "event_year"])

    # Indicator panel (fitter contract: country_id, year, indicator_id, value).
    # Restricted to the countries + years that appear in this recipe's positives.
    if not positives_df.empty:
        needed_countries = set(positives_df["country_id"].unique())
        needed_years_per_country: dict[str, set[int]] = {}
        for _, row in positives_df.iterrows():
            cid = row["country_id"]
            ey = int(row["event_year"])
            needed_years_per_country.setdefault(cid, set())
            needed_years_per_country[cid].update(
                range(ey - T_r - BASELINE_YEARS, ey)
            )

        # Build the panel subset efficiently.
        panel_subset_rows: list[pd.DataFrame] = []
        for cid, yrs in needed_years_per_country.items():
            sub = panel_filtered[
                (panel_filtered["country_id"] == cid)
                & (panel_filtered["year"].isin(yrs))
            ]
            panel_subset_rows.append(sub)

        if panel_subset_rows:
            panel_subset_df = pd.concat(panel_subset_rows, ignore_index=True)
        else:
            panel_subset_df = pd.DataFrame(
                columns=["country_id", "year", "indicator_id", "value"]
            )
    else:
        panel_subset_df = pd.DataFrame(
            columns=["country_id", "year", "indicator_id", "value"]
        )

    # ---- Emit outputs -------------------------------------------------------
    recipe_out = output_dir / recipe_id
    recipe_out.mkdir(parents=True, exist_ok=True)

    aligned_parquet_path = recipe_out / "positives_aligned.parquet"
    positives_csv_path = recipe_out / "positives.csv"
    panel_parquet_path = recipe_out / "indicator_panel.parquet"
    manifest_path = recipe_out / "prep_manifest.json"
    log_path = recipe_out / "prep_log.md"

    aligned_df.to_parquet(aligned_parquet_path, index=False)
    positives_df.to_csv(positives_csv_path, index=False)
    panel_subset_df.to_parquet(panel_parquet_path, index=False)

    # ---- Manifest -----------------------------------------------------------
    prep_commit_sha = _git_commit_sha(REPO_ROOT)
    qgdata_commit_sha = _git_commit_sha(QGDATA_ROOT)

    example_dropouts = [
        d for d in dropouts
        if d["reason"] != "COUNTRY_NOT_IN_PANEL"
    ][:5]

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "recipe_id": recipe_id,
        "canonical_length_T": T_r,
        "key_indicators_requested": key_indicators,
        "key_indicators_available_locally": available_in_panel,
        "key_indicators_missing_from_local_panel": missing_from_panel,
        "indicator_coverage_fraction": (
            len(available_in_panel) / len(key_indicators)
            if key_indicators else 0.0
        ),
        "counts": {
            "n_pos_input": n_pos_input,
            "n_country_not_in_panel": n_country_not_in_panel,
            "n_baseline_too_short": n_baseline_too_short,
            "n_pos_after_baseline_filter": n_pos_after_dropouts,
            "n_alignment_dropouts": n_alignment_dropouts,
            "n_pos_final": n_final_instances,
            "n_instances_in_parquet": int(aligned_df["instance_idx"].nunique()) if not aligned_df.empty else 0,
        },
        "dropout_sample": (
            dropouts[:5]
            if dropouts else []
        ),
        "baseline_too_short_examples": example_dropouts,
        "source_shas": {
            "qgi_ml_commit": prep_commit_sha,
            "qgi_data_commit": qgdata_commit_sha,
            "aligned_parquet_sha256": _sha256_file(aligned_parquet_path),
            "positives_csv_sha256": _sha256_file(positives_csv_path),
            "indicator_panel_sha256": _sha256_file(panel_parquet_path),
        },
        "fitter_input_contract": {
            "indicator_panel": str(panel_parquet_path),
            "positive_instances": str(positives_csv_path),
            "indicator_ids": ",".join(available_in_panel),
            "T_r": T_r,
        },
        "honesty_disclosure": (
            f"Local panel snapshot contains only {len(available_in_panel)}/{len(key_indicators)} "
            f"key indicators for {recipe_id}. "
            f"Missing: {missing_from_panel}. "
            f"G3/G4 substrate verdicts are BLOCKED-on-substrate-availability per Tariq's audit. "
            f"Re-run on full 104-indicator production panel required (see substrate-audit-phase-1.json P0 actions)."
        ),
    }

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # ---- Human-readable log ------------------------------------------------
    coverage_pct = 100.0 * len(available_in_panel) / len(key_indicators) if key_indicators else 0.0
    _write_log(
        log_path=log_path,
        recipe_id=recipe_id,
        T_r=T_r,
        n_pos_input=n_pos_input,
        n_country_not_in_panel=n_country_not_in_panel,
        n_baseline_too_short=n_baseline_too_short,
        n_pos_after_dropouts=n_pos_after_dropouts,
        n_alignment_dropouts=n_alignment_dropouts,
        n_final=n_final_instances,
        available_in_panel=available_in_panel,
        missing_from_panel=missing_from_panel,
        coverage_pct=coverage_pct,
        dropout_sample=dropouts[:10],
        prep_commit_sha=prep_commit_sha,
        aligned_parquet_path=aligned_parquet_path,
        positives_csv_path=positives_csv_path,
        panel_parquet_path=panel_parquet_path,
    )

    logger.info(
        "Recipe %s done. Output: %s", recipe_id, recipe_out
    )

    return {
        "recipe_id": recipe_id,
        "n_pos_input": n_pos_input,
        "n_pos_kept": n_final_instances,
        "n_baseline_too_short": n_baseline_too_short,
        "n_country_not_in_panel": n_country_not_in_panel,
        "available_indicators": available_in_panel,
        "missing_indicators": missing_from_panel,
        "indicator_coverage_fraction": len(available_in_panel) / len(key_indicators) if key_indicators else 0.0,
        "output_dir": str(recipe_out),
    }


def _write_log(
    *,
    log_path: Path,
    recipe_id: str,
    T_r: int,
    n_pos_input: int,
    n_country_not_in_panel: int,
    n_baseline_too_short: int,
    n_pos_after_dropouts: int,
    n_alignment_dropouts: int,
    n_final: int,
    available_in_panel: list[str],
    missing_from_panel: list[str],
    coverage_pct: float,
    dropout_sample: list[dict[str, Any]],
    prep_commit_sha: str,
    aligned_parquet_path: Path,
    positives_csv_path: Path,
    panel_parquet_path: Path,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Shape Input Panel — Prep Log",
        "",
        f"**Recipe:** `{recipe_id}`  ",
        f"**Canonical length T_r:** {T_r}  ",
        f"**Prepared:** {now}  ",
        f"**Commit:** `{prep_commit_sha}`  ",
        "",
        "## Instance counts",
        "",
        "| Stage | Count |",
        "|-------|-------|",
        f"| n_pos_input (curated events, training window 1789-2021) | {n_pos_input} |",
        f"| Country not in local panel | -{n_country_not_in_panel} |",
        f"| BASELINE_TOO_SHORT (§3.2.2) | -{n_baseline_too_short} |",
        f"| After baseline filter | {n_pos_after_dropouts} |",
        f"| Alignment dropouts | -{n_alignment_dropouts} |",
        f"| **Final instances in parquet** | **{n_final}** |",
        "",
        "## Indicator coverage",
        "",
        f"**{len(available_in_panel)}/{len(available_in_panel) + len(missing_from_panel)}** "
        f"({coverage_pct:.0f}%) key indicators available in local panel snapshot.",
        "",
        f"**Available:** {available_in_panel}",
        "",
        "**Missing (BLOCKED — not in local 37-indicator snapshot):**",
        f"{missing_from_panel}",
        "",
        "> **Honesty disclosure:** G3/G4 substrate verdicts are "
        "BLOCKED-on-substrate-availability. Re-run on full 104-indicator "
        "production panel required (substrate-audit-phase-1.json P0 actions).",
        "",
        "## Dropout sample (first 10)",
        "",
    ]

    if dropout_sample:
        lines.append("| country_id | event_year | reason |")
        lines.append("|------------|-----------|--------|")
        for d in dropout_sample:
            lines.append(
                f"| {d['country_id']} | {d['event_year']} | {d['reason']} |"
            )
    else:
        lines.append("_No dropouts._")

    lines += [
        "",
        "## Output files",
        "",
        "| File | Description |",
        "|------|-------------|",
        f"| `{aligned_parquet_path.name}` | Long-format aligned+normalized trajectories |",
        f"| `{positives_csv_path.name}` | Positives CSV for fitter `--positive-instances` |",
        f"| `{panel_parquet_path.name}` | Indicator panel for fitter `--indicator-panel` |",
        "| `prep_manifest.json` | Full provenance manifest |",
        "",
        "## Fitter invocation (Chunk C.2)",
        "",
        "```bash",
        "python scripts/fit_shape_prototype.py \\",
        f"    --recipe {recipe_id} \\",
        f"    --indicator-panel {panel_parquet_path} \\",
        f"    --positive-instances {positives_csv_path} \\",
        f"    --indicator-ids {','.join(available_in_panel)} \\",
        f"    --T-r {T_r}",
        "```",
    ]

    log_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Chunk C.1 — prepare shape input panels for Stage 6 fitter."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--recipe", help="Single recipe_id to process.")
    mode.add_argument(
        "--batch",
        choices=["phase-1"],
        help="Batch mode: process all Phase 1 recipes.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data" / "shape_inputs",
        help="Root output directory. Per-recipe subdirectory is created here.",
    )
    parser.add_argument(
        "--canonical-length",
        type=int,
        default=None,
        dest="canonical_length",
        help="Override T_r (default: read from substrate audit JSON).",
    )
    parser.add_argument(
        "--key-indicators",
        type=Path,
        default=None,
        dest="key_indicators",
        help="Override path to substrate-audit-phase-1.json.",
    )
    args = parser.parse_args(argv)

    recipes = PHASE_1_RECIPES if args.batch == "phase-1" else [args.recipe]

    # Pre-load the combined panel once (shared across recipes in batch mode).
    try:
        combined_panel = load_combined_panel()
    except FileNotFoundError as exc:
        logger.error("BLOCKER: %s", exc)
        return 1

    results: list[dict[str, Any]] = []
    for recipe_id in recipes:
        logger.info("=== Processing recipe: %s ===", recipe_id)
        try:
            result = prepare_recipe(
                recipe_id,
                output_dir=args.output_dir,
                canonical_length_T=args.canonical_length,
                key_indicators_path=args.key_indicators,
                panel=combined_panel,
            )
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to prepare recipe=%s: %s", recipe_id, exc, exc_info=True)
            results.append({"recipe_id": recipe_id, "error": str(exc)})

    # Summary.
    logger.info("=== Summary ===")
    for r in results:
        if "error" in r:
            logger.error("  %s: FAILED — %s", r["recipe_id"], r["error"])
        else:
            logger.info(
                "  %s: n_pos_input=%d n_pos_kept=%d coverage=%d/%d",
                r["recipe_id"],
                r["n_pos_input"],
                r["n_pos_kept"],
                len(r["available_indicators"]),
                len(r["available_indicators"]) + len(r["missing_indicators"]),
            )

    return 0 if all("error" not in r for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
