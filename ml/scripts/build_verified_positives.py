"""Build verdict=TRUE positives.csv per recipe for the fleet fan-out (#112).

Joins ``qgi-data/events/curated/`` (carries `category`) to
``qgi-data/events/verification/`` (carries `verdict`) on (country, year, title);
keeps ONLY events with `verdict == "TRUE"`; dedups to one (country, event_year)
per recipe within the F-ML-1 training window; writes
``shape_inputs_v2/{recipe}/positives.csv`` for every category with
n_pos >= THIN_MIN_NPOS.

The fleet walk syncs indicator panels from S3 and self-selects indicators, so
``positives.csv`` (country_id, event_year) is the ONLY per-recipe input this prep
produces — no panel alignment, no indicator hand-picking.

Founder directive 2026-05-25 ("work with verified events strictly"): the prior
prep (`prepare_shape_input_panels.load_positive_instances`) used ALL curated
events regardless of verdict. This builder restricts to the verification verdict.

Fail-loud (M-style honesty): among countries that HAVE a verification file, the
curated->verdict match rate must be >= --min-match-rate (default 0.90). Countries
with NO verification file are excluded from positives (cannot be verified) and are
NOT counted against the match rate — they are reported separately.

country_id in positives.csv is the event-file slug (lowercase, e.g. "afghanistan"),
matching the existing positives.csv contract + run_f_ml_1_poc.normalize_country_id.

Notes (review followups):
  - n_pos is PRE-panel-coverage (an upper bound). The walk drops positives whose
    indicators lack panel coverage, so a recipe tiered near THIN_MIN may see fewer
    effective positives at walk time.
  - This builder OVERWRITES positives.csv in-place under shape_inputs_v2/; it does
    NOT prune a stale positives.csv for a recipe that drops to 0 verified-TRUE
    events (none do at present). Re-run cleanly or remove orphans manually if a
    category is ever retired.

Test-first per #373. Run-time: <30s laptop. Zero AWS.

Usage:
    python scripts/build_verified_positives.py                      # write all recipes
    python scripts/build_verified_positives.py --dry-run            # diagnostics only, no writes
    python scripts/build_verified_positives.py --diagnostics-out /tmp/verified-positives-diag.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
QGDATA_ROOT = REPO_ROOT.parent / "qgi-data"

# F-ML-1 training window (matches prepare_shape_input_panels.py) + tier thresholds
# (matches build_recipe_manifest.py).
TRAIN_MIN_YEAR = 1789
TRAIN_MAX_YEAR = 2021
THIN_MIN_NPOS = 8       # < THIN_MIN_NPOS → recipe is skipped (no positives.csv written)
RUNNABLE_MIN_NPOS = 60  # informational tiering only (manifest applies the gate)

TRUE_VERDICT = "TRUE"


_NONALNUM = re.compile(r"[^a-z0-9]+")


def _norm_title(title: str | None) -> str:
    """Join-key normalization: lowercase, collapse every run of non-alphanumeric
    characters to a single space, strip. This recovers the (year, title) join
    across an encoding drift between the curated and verification files — the
    curated titles carry mojibaked/replacement characters (e.g. U+FFFD) where the
    verification titles carry the proper punctuation (e.g. em-dash U+2014); an
    exact-strip match silently dropped ~40-57% of verified events for ~10 countries
    (france/ukraine/angola/...). Alphanumeric-only normalization makes
    "Suez Crisis <U+FFFD> France" and "Suez Crisis <U+2014> France" the same key.
    (Underlying curated-file corruption is a separate qgi-data hygiene followup.)"""
    return _NONALNUM.sub(" ", (title or "").lower()).strip()


def load_verdict_map(verification_dir: Path) -> dict[str, dict[tuple[int, str], str]]:
    """country_slug -> {(year, norm_title): verdict}. One entry per verification file."""
    vmap: dict[str, dict[tuple[int, str], str]] = {}
    if not verification_dir.exists():
        raise FileNotFoundError(f"Verification dir not found: {verification_dir}")
    for vf in sorted(verification_dir.glob("*.json")):
        if vf.stem.startswith("_"):
            continue
        try:
            events = json.loads(vf.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: skipping verification file {vf.name}: {exc}", file=sys.stderr)
            continue
        if not isinstance(events, list):
            continue
        m: dict[tuple[int, str], str] = {}
        for e in events:
            yr, ti, vd = e.get("year"), e.get("title"), e.get("verdict")
            if yr is None or ti is None:
                continue
            m[(int(yr), _norm_title(ti))] = vd
        vmap[vf.stem] = m
    return vmap


def build_positives(
    curated_dir: Path,
    verdict_map: dict[str, dict[tuple[int, str], str]],
    train_min: int = TRAIN_MIN_YEAR,
    train_max: int = TRAIN_MAX_YEAR,
) -> tuple[dict[str, set[tuple[str, int]]], dict[str, Any]]:
    """Return ({recipe -> set[(country_slug, event_year)] verdict==TRUE in window},
    diagnostics). Only curated events in countries that HAVE a verification file can
    contribute (a TRUE verdict requires a verification record)."""
    if not curated_dir.exists():
        raise FileNotFoundError(f"Curated dir not found: {curated_dir}")

    positives: dict[str, set[tuple[str, int]]] = defaultdict(set)
    n_curated = n_curated_verified_country = n_matched = n_true = 0
    countries_no_verification: set[str] = set()
    per_category_curated: dict[str, int] = defaultdict(int)
    # Per-country match tracking (review followup): the aggregate match rate can
    # mask a single country with systematically mismatched titles (e.g. casing /
    # Unicode drift), so we surface per-country rates + a low-match watchlist.
    per_country_total: dict[str, int] = defaultdict(int)
    per_country_matched: dict[str, int] = defaultdict(int)

    for cf in sorted(curated_dir.glob("*.json")):
        if cf.stem.startswith("_") or "curation_report" in cf.name:
            continue
        country = cf.stem
        try:
            events = json.loads(cf.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: skipping curated file {cf.name}: {exc}", file=sys.stderr)
            continue
        if not isinstance(events, list):
            continue
        country_vmap = verdict_map.get(country)
        has_verification = country_vmap is not None
        if not has_verification:
            countries_no_verification.add(country)

        for e in events:
            cat, yr, ti = e.get("category"), e.get("year"), e.get("title")
            if cat is None or yr is None:
                continue
            yr = int(yr)
            if not (train_min <= yr <= train_max):
                continue
            n_curated += 1
            per_category_curated[cat] += 1
            if not has_verification:
                continue
            n_curated_verified_country += 1
            per_country_total[country] += 1
            verdict = country_vmap.get((yr, _norm_title(ti)))
            if verdict is not None:  # matched a verdict record (TRUE/FALSE/PARTIAL/UNCERTAIN) = join health
                n_matched += 1
                per_country_matched[country] += 1
            if verdict == TRUE_VERDICT:
                n_true += 1
                positives[cat].add((country, yr))

    match_rate = (n_matched / n_curated_verified_country) if n_curated_verified_country else 0.0
    per_country_match_rate = {
        c: round(per_country_matched[c] / per_country_total[c], 3)
        for c in sorted(per_country_total)
    }
    # watchlist: verified countries with >=10 curated events but <70% join — likely
    # title/casing corruption hiding behind the healthy aggregate.
    low_match_countries = sorted(
        c for c, r in per_country_match_rate.items()
        if per_country_total[c] >= 10 and r < 0.70
    )
    diagnostics = {
        "train_window": [train_min, train_max],
        "n_curated_events_in_window": n_curated,
        "n_curated_in_verified_countries": n_curated_verified_country,
        "n_matched_a_verdict": n_matched,
        "n_verdict_true": n_true,
        "match_rate_among_verified_countries": round(match_rate, 4),
        "n_countries_with_verification": len(verdict_map),
        "n_countries_without_verification": len(countries_no_verification),
        "countries_without_verification": sorted(countries_no_verification),
        "low_match_countries": low_match_countries,
        "per_country_match_rate": per_country_match_rate,
        "per_category_curated_in_window": dict(sorted(per_category_curated.items())),
    }
    return positives, diagnostics


def tier(n_pos: int) -> str:
    if n_pos >= RUNNABLE_MIN_NPOS:
        return "runnable"
    if n_pos >= THIN_MIN_NPOS:
        return "thin"
    return "skip"


def write_positives(
    positives: dict[str, set[tuple[str, int]]],
    out_dir: Path,
    dry_run: bool = False,
) -> dict[str, dict[str, Any]]:
    """Write shape_inputs_v2/{recipe}/positives.csv for recipes with n_pos >= THIN_MIN.
    Returns per-recipe {n_pos, tier, written}."""
    summary: dict[str, dict[str, Any]] = {}
    for recipe in sorted(positives):
        rows = sorted(positives[recipe])  # (country_slug, year) sorted deterministically
        n_pos = len(rows)
        t = tier(n_pos)
        written = False
        if t != "skip" and not dry_run:
            recipe_dir = out_dir / recipe
            recipe_dir.mkdir(parents=True, exist_ok=True)
            with (recipe_dir / "positives.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["country_id", "event_year"])
                w.writerows(rows)
            written = True
        summary[recipe] = {"n_pos": n_pos, "tier": t, "written": written}
    return summary


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--curated-dir", type=Path, default=QGDATA_ROOT / "events" / "curated")
    p.add_argument("--verification-dir", type=Path, default=QGDATA_ROOT / "events" / "verification")
    p.add_argument("--out-dir", type=Path, default=REPO_ROOT / "data" / "shape_inputs_v2")
    p.add_argument("--min-match-rate", type=float, default=0.90,
                   help="Fail loudly if curated->verdict match rate among verified countries is below this.")
    p.add_argument("--diagnostics-out", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true", help="Compute + report; write no positives.csv.")
    args = p.parse_args(argv)

    verdict_map = load_verdict_map(args.verification_dir)
    positives, diag = build_positives(args.curated_dir, verdict_map)
    summary = write_positives(positives, args.out_dir, dry_run=args.dry_run)

    tiers = {"runnable": 0, "thin": 0, "skip": 0}
    for s in summary.values():
        tiers[s["tier"]] += 1

    report = {"diagnostics": diag, "tiers": tiers, "recipes": summary}
    if args.diagnostics_out:
        args.diagnostics_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if diag["n_curated_in_verified_countries"] == 0:
        print("WARNING: no curated events in verified countries within the window — "
              "match rate is undefined (reported as 0.0); this is empty data, not a join failure.")
    print(f"match_rate among verified countries: {diag['match_rate_among_verified_countries']:.1%} "
          f"({diag['n_matched_a_verdict']}/{diag['n_curated_in_verified_countries']})")
    print(f"verdict==TRUE positives: {diag['n_verdict_true']} | "
          f"countries w/o verification (excluded): {diag['n_countries_without_verification']}")
    if diag["low_match_countries"]:
        print(f"  WARNING: low-match countries (>=10 events, <70% join; check title/casing drift): "
              f"{diag['low_match_countries']}")
    # NOTE: n_pos below is PRE-panel-coverage (an upper bound). The walk drops
    # positives whose indicators lack panel coverage at feature-extraction, so a
    # recipe tiered near THIN_MIN may see fewer effective positives at walk time.
    print(f"tiers: runnable(>={RUNNABLE_MIN_NPOS})={tiers['runnable']}  "
          f"thin({THIN_MIN_NPOS}-{RUNNABLE_MIN_NPOS - 1})={tiers['thin']}  skip(<{THIN_MIN_NPOS})={tiers['skip']}"
          + ("  [DRY-RUN: no files written]" if args.dry_run else ""))

    if diag["match_rate_among_verified_countries"] < args.min_match_rate:
        print(f"FAIL-LOUD: match rate {diag['match_rate_among_verified_countries']:.1%} "
              f"< --min-match-rate {args.min_match_rate:.0%}. Investigate title/year join "
              f"mismatches before trusting positives.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
