"""Bootstrap confidence bands for per-country recipe similarity scores.

Per risk-metric design v1 (3-Reviewer ratified 2026-05-22):
  docs/specs/internal/ops/ml-track/risk-metric-design-v1.md

Adds uncertainty quantification to the point-estimate risk scores produced by
``compute_recipe_country_similarity.py``.  The canonical profile is the MEAN
z-scored trajectory across all historical positive instances.  Its uncertainty
comes from the finite spread of those positives.  We quantify it by:

  1. Bootstrap-resampling the positive-instance indices with replacement (B
     iterations, configurable).
  2. Rebuilding the per-indicator canonical as the mean of the resampled
     trajectories each time.
  3. Recomputing every scored country's risk_score via the **unchanged**
     ``compute_country_recipe_similarity`` function from the production script.
  4. Reporting p2.5/p10/p90/p97.5 percentile bands per country.

The point estimate (full-sample canonical mean) reproduces the production
script's scores exactly — verified by checking that Iran ≈ 98.1 for
foreign_intervention.

Usage:
    python scripts/compute_similarity_bands.py \\
        --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --shap-importances qgi-data/reference/shap-importances-foreign_intervention.json \\
        --scores-file qgi-data/reference/recipe-similarity-scores-foreign_intervention-2021.json \\
        --panel-dir data/parquet_panels \\
        --output-dir qgi-data/reference/ \\
        --n-bootstrap 1000 \\
        --seed 12345

Output:
    similarity-bands-{recipe-id}-{eval_year}.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402
from compute_recipe_country_similarity import (  # noqa: E402
    compute_country_recipe_similarity,
    extract_country_trajectory,
    prebake_zscore_distribution,
)

REPO_ROOT = SCRIPTS_DIR.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core helpers (pure functions — unit-testable without IO)
# ---------------------------------------------------------------------------


def collect_positive_trajectories(
    walk: dict,
    panels: dict[str, pd.DataFrame],
    chosen_window: int,
    selected: list[str],
    max_year: int | None = None,
) -> dict[str, list[np.ndarray]]:
    """Return the per-positive z-scored trajectory list for each indicator.

    Mirrors the inner loop of ``build_canonical_profile_from_walk`` in
    ``compute_recipe_country_similarity.py`` exactly — same baseline-filter,
    z-score logic, and ``normalize_country_id`` calls.  The difference is that
    it returns the **list** of per-positive vectors rather than their mean, so
    the bootstrap loop can resample them freely.

    Parameters
    ----------
    walk:
        Walk-summary JSON (loaded dict).
    panels:
        ``{indicator_id: panel_dataframe}`` — same format as the production
        script; already loaded by the caller.
    chosen_window:
        Number of years in each trajectory window (from walk summary).
    selected:
        Ordered list of selected indicator IDs (from walk summary).
    max_year:
        Optional upper-bound on event_year (mirrors the OOT-holdout parameter
        in the production canonical builder).

    Returns
    -------
    dict[str, list[np.ndarray]]
        ``{indicator_id: [z_vector_per_positive, ...]}``
        Indicators for which no positive has sufficient data return an empty
        list (the caller must handle this gracefully).
    """
    recipe_id = walk["recipe_id"]
    pos = pd.read_csv(REPO_ROOT / "data" / "shape_inputs_v2" / recipe_id / "positives.csv")
    pos["country"] = pos["country_id"].apply(drv.normalize_country_id)
    pos = pos.rename(columns={"event_year": "year"})
    if max_year is not None:
        pos = pos[pos["year"] <= max_year]

    per_positive: dict[str, list[np.ndarray]] = {ind: [] for ind in selected}

    for ind in selected:
        panel = panels[ind]
        for _, row in pos.iterrows():
            country = str(row["country"])
            event_year = int(row["year"])
            cdf = panel[panel["country"] == country]
            if len(cdf) == 0:
                continue
            series = cdf.set_index("year")["value"]
            window_data = series.loc[event_year - chosen_window : event_year - 1]
            full_index = pd.RangeIndex(event_year - chosen_window, event_year)
            window_full = window_data.reindex(full_index)
            if window_full.dropna().shape[0] < max(3, chosen_window // 3):
                continue
            # Panel-wide z-score at event_year - 1  (mirrors production logic exactly)
            panel_at_year = panel[panel["year"] == event_year - 1]["value"].dropna()
            if len(panel_at_year) < 10:
                baseline = series.loc[
                    max(event_year - 25, series.index.min()) : event_year - 1
                ].dropna()
                # Bare mean (matches build_canonical_profile_from_walk exactly):
                # on an empty baseline this NaN-propagates and is absorbed by the
                # np.where(isfinite) mask below — identical to production. A guarded
                # `else 0.0` would diverge (it keeps a real z-vector), so do NOT add one.
                mu = float(baseline.mean())
                sd = float(baseline.std() or 1.0)
            else:
                mu = float(panel_at_year.mean())
                sd = float(panel_at_year.std() or 1.0)
            z = (window_full.values - mu) / sd
            z = np.where(np.isfinite(z), z, 0.0)
            per_positive[ind].append(z)

    return per_positive


def build_canonical_from_sample(
    trajectories_per_ind: dict[str, list[np.ndarray]],
    chosen_window: int,
    rng: np.random.Generator | None = None,
) -> dict[str, np.ndarray]:
    """Build a canonical profile by averaging the per-positive trajectories.

    Parameters
    ----------
    trajectories_per_ind:
        ``{indicator_id: [z_vector, ...]}`` from ``collect_positive_trajectories``.
    chosen_window:
        Window length — used as the fallback zero vector when a list is empty.
    rng:
        If ``None`` (point-estimate path), the canonical for each indicator is the
        full-sample mean of its trajectories. If an RNG is supplied (bootstrap
        path), each indicator is resampled INDEPENDENTLY — its own list of length
        ``n_i`` is resampled with replacement to ``n_i`` draws, then averaged.

        Independent per-indicator resampling is the statistically correct
        nonparametric bootstrap here: the per-indicator canonicals are built from
        largely different positive-instance subsets (foreign_intervention coverage:
        v2elintmon 24, RQ.EST 46, v2pepwrgen 110, v2stfisccap 109), so each
        canonical's sampling uncertainty must be drawn from its OWN pool. This
        correctly propagates the larger uncertainty of thin-coverage indicators
        (e.g. RQ.EST at n=46 carrying 51% of the SHAP weight) into the score band.

    Returns
    -------
    dict[str, np.ndarray]
        ``{indicator_id: mean_z_vector_of_shape_(chosen_window,)}``
    """
    canonical: dict[str, np.ndarray] = {}
    for ind, traj_list in trajectories_per_ind.items():
        n = len(traj_list)
        if n == 0:
            canonical[ind] = np.zeros(chosen_window)
            continue
        arr = np.array(traj_list)
        if rng is None:
            # Full-sample mean — point estimate path
            canonical[ind] = np.mean(arr, axis=0)
        else:
            # Independent per-indicator bootstrap: resample this indicator's own
            # n_i trajectories with replacement, n_i draws.
            idx = rng.integers(0, n, size=n)
            canonical[ind] = np.mean(arr[idx], axis=0)
    return canonical


def bootstrap_bands(
    per_positive: dict[str, list[np.ndarray]],
    country_trajectories: dict[str, dict[str, np.ndarray]],
    shap_weights: dict[str, float],
    chosen_window: int,
    n_bootstrap: int = 1000,
    seed: int = 12345,
) -> dict[str, dict[str, Any]]:
    """Bootstrap-resample positive instances and build percentile bands.

    Parameters
    ----------
    per_positive:
        Output of ``collect_positive_trajectories``.
    country_trajectories:
        ``{country: {indicator_id: z_vector}}`` — pre-extracted at evaluation
        year.  Only countries present here are scored.
    shap_weights:
        Normalised SHAP importance weights (sum to 1 across selected indicators).
    chosen_window:
        Window length (used as fallback in ``build_canonical_from_sample``).
    n_bootstrap:
        Number of bootstrap replicates (default 1 000).
    seed:
        NumPy random seed for reproducibility (default 12345).

    Returns
    -------
    dict[str, dict[str, Any]]
        ``{country: {risk_score, ci80_lo, ci80_hi, ci95_lo, ci95_hi,
                      band_width_80, bootstrap_mean, bootstrap_std}}``
    """
    rng = np.random.default_rng(seed)

    countries = list(country_trajectories.keys())
    n_countries = len(countries)

    # --- Point estimate (full-sample canonical) ---
    canonical_full = build_canonical_from_sample(per_positive, chosen_window, rng=None)
    point_scores = np.empty(n_countries)
    for ci, country in enumerate(countries):
        result = compute_country_recipe_similarity(
            country_trajectories[country], canonical_full, shap_weights
        )
        point_scores[ci] = result["risk_score"]

    # --- Bootstrap distribution ---
    # Shape: (n_bootstrap, n_countries)
    boot_scores = np.empty((n_bootstrap, n_countries))

    for b in range(n_bootstrap):
        canonical_b = build_canonical_from_sample(per_positive, chosen_window, rng=rng)
        for ci, country in enumerate(countries):
            result = compute_country_recipe_similarity(
                country_trajectories[country], canonical_b, shap_weights
            )
            boot_scores[b, ci] = result["risk_score"]

    # --- Percentile bands ---
    p2_5 = np.percentile(boot_scores, 2.5, axis=0)
    p10 = np.percentile(boot_scores, 10.0, axis=0)
    p90 = np.percentile(boot_scores, 90.0, axis=0)
    p97_5 = np.percentile(boot_scores, 97.5, axis=0)
    boot_mean = np.mean(boot_scores, axis=0)
    boot_std = np.std(boot_scores, axis=0, ddof=1)

    bands: dict[str, dict[str, Any]] = {}
    for ci, country in enumerate(countries):
        bands[country] = {
            "risk_score": float(point_scores[ci]),
            "ci80_lo": float(p10[ci]),
            "ci80_hi": float(p90[ci]),
            "ci95_lo": float(p2_5[ci]),
            "ci95_hi": float(p97_5[ci]),
            "band_width_80": float(p90[ci] - p10[ci]),
            "bootstrap_mean": float(boot_mean[ci]),
            "bootstrap_std": float(boot_std[ci]),
        }

    return bands


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--recipe-id", required=True,
                        help="Recipe identifier, e.g. foreign_intervention")
    parser.add_argument("--walk-summary", type=Path, required=True,
                        help="Path to f-ml-1-poc-summary.json from run_f_ml_1_poc.py")
    parser.add_argument("--shap-importances", type=Path, required=True,
                        help="Path to shap-importances-{recipe-id}.json")
    parser.add_argument("--scores-file", type=Path, required=True,
                        help="Path to recipe-similarity-scores-{recipe-id}-{year}.json "
                             "produced by compute_recipe_country_similarity.py.  Used "
                             "to read the country list, eval_year, chosen_window, and "
                             "selected indicators (avoids re-deriving them).")
    parser.add_argument("--panel-dir", type=Path,
                        default=REPO_ROOT / "data" / "parquet_panels",
                        help="Directory containing per-indicator parquet panels")
    parser.add_argument("--n-bootstrap", type=int, default=1000,
                        help="Number of bootstrap replicates (default 1000)")
    parser.add_argument("--seed", type=int, default=12345,
                        help="NumPy random seed for reproducibility (default 12345)")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Directory to write similarity-bands-{recipe-id}-{year}.json")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load walk summary + SHAP importances
    # ------------------------------------------------------------------
    log.info("Loading walk summary: %s", args.walk_summary)
    with open(args.walk_summary, encoding="utf-8") as f:
        walk = json.load(f)
    assert walk["recipe_id"] == args.recipe_id, (
        f"walk recipe_id '{walk['recipe_id']}' != --recipe-id '{args.recipe_id}'"
    )

    selected: list[str] = walk["greedy_outer_loop"]["selected_indicators"]
    chosen_window: int = walk["greedy_outer_loop"]["chosen_window"]
    log.info("Recipe: %s | indicators: %s | window: %dy", args.recipe_id, selected, chosen_window)

    log.info("Loading SHAP importances: %s", args.shap_importances)
    with open(args.shap_importances, encoding="utf-8") as f:
        shap_data = json.load(f)
    shap_weights: dict[str, float] = shap_data["shap_importance_normalized"]
    assert set(shap_weights.keys()) == set(selected), (
        f"SHAP indicators {sorted(shap_weights)} != walk selected {sorted(selected)}"
    )

    # ------------------------------------------------------------------
    # 2. Load existing scores file to get country list + eval_year
    # ------------------------------------------------------------------
    log.info("Loading existing scores file: %s", args.scores_file)
    with open(args.scores_file, encoding="utf-8") as f:
        scores_data = json.load(f)
    evaluation_year: int = scores_data["evaluation_year"]
    countries_in_scores: list[str] = list(scores_data["scores"].keys())
    log.info("Eval year: %d | Countries in scores: %d", evaluation_year, len(countries_in_scores))

    # Cross-check that the scores file's indicators / window match the walk
    assert scores_data.get("selected_indicators") == selected, (
        f"Scores file selected_indicators {scores_data.get('selected_indicators')} "
        f"!= walk selected {selected}"
    )
    assert scores_data.get("chosen_window") == chosen_window, (
        f"Scores file chosen_window {scores_data.get('chosen_window')} "
        f"!= walk chosen_window {chosen_window}"
    )

    # ------------------------------------------------------------------
    # 3. Load panels + pre-bake z-distribution
    # ------------------------------------------------------------------
    log.info("Loading indicator panels from %s ...", args.panel_dir)
    panels: dict[str, pd.DataFrame] = {
        ind: drv.load_panel(ind, args.panel_dir) for ind in selected
    }

    log.info("Pre-baking panel-wide z-score distribution for eval_year=%d ...", evaluation_year)
    z_dist = prebake_zscore_distribution(args.panel_dir, selected, evaluation_year)

    # ------------------------------------------------------------------
    # 4. Extract country trajectories (mirrors production script exactly)
    # ------------------------------------------------------------------
    log.info("Extracting country trajectories at eval_year=%d ...", evaluation_year)
    country_trajectories: dict[str, dict[str, np.ndarray]] = {}
    for country in countries_in_scores:
        traj: dict[str, np.ndarray] = {}
        for ind in selected:
            t = extract_country_trajectory(
                panels[ind], country, evaluation_year, chosen_window,
                ind_dist=z_dist[ind],
            )
            if t is not None:
                traj[ind] = t
        if len(traj) == len(selected):
            country_trajectories[country] = traj
        else:
            log.warning("Skipping %s — missing %d/%d indicator trajectories",
                        country, len(selected) - len(traj), len(selected))
    log.info("%d countries with full trajectory data", len(country_trajectories))

    # ------------------------------------------------------------------
    # 5. Collect per-positive trajectory lists from walk positives
    # ------------------------------------------------------------------
    log.info("Collecting per-positive trajectories for bootstrap ...")
    per_positive = collect_positive_trajectories(walk, panels, chosen_window, selected)
    n_pos_per_ind = {ind: len(v) for ind, v in per_positive.items()}
    log.info("Positive trajectory counts per indicator: %s", n_pos_per_ind)

    # ------------------------------------------------------------------
    # 6. Self-check: point estimate must match production scores within 0.1
    # ------------------------------------------------------------------
    log.info("Self-check: verifying point estimate matches production scores ...")
    canonical_full = build_canonical_from_sample(per_positive, chosen_window, rng=None)
    n_mismatches = 0
    for country, prod_data in scores_data["scores"].items():
        if country not in country_trajectories:
            continue
        our_result = compute_country_recipe_similarity(
            country_trajectories[country], canonical_full, shap_weights
        )
        prod_score = prod_data["risk_score"]
        delta = abs(our_result["risk_score"] - prod_score)
        if delta > 0.1:
            log.warning("SELF-CHECK MISMATCH: %s  ours=%.2f  prod=%.2f  delta=%.3f",
                        country, our_result["risk_score"], prod_score, delta)
            n_mismatches += 1
    if n_mismatches == 0:
        log.info("Self-check PASSED — all point estimates within 0.1 of production.")
    else:
        log.error("Self-check FAILED: %d countries deviate > 0.1 from production scores.", n_mismatches)

    # ------------------------------------------------------------------
    # 7. Bootstrap
    # ------------------------------------------------------------------
    log.info("Running bootstrap (B=%d, seed=%d) for %d countries ...",
             args.n_bootstrap, args.seed, len(country_trajectories))
    bands = bootstrap_bands(
        per_positive=per_positive,
        country_trajectories=country_trajectories,
        shap_weights=shap_weights,
        chosen_window=chosen_window,
        n_bootstrap=args.n_bootstrap,
        seed=args.seed,
    )
    log.info("Bootstrap complete.")

    # ------------------------------------------------------------------
    # 8. Emit output JSON
    # ------------------------------------------------------------------
    output = {
        "schema_version": 1,
        "recipe_id": args.recipe_id,
        "eval_year": evaluation_year,
        "n_bootstrap": args.n_bootstrap,
        "seed": args.seed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "bootstrap_resample_positive_instances",
        "band_description": {
            "ci80_lo": "10th percentile of bootstrap distribution",
            "ci80_hi": "90th percentile of bootstrap distribution",
            "ci95_lo": "2.5th percentile of bootstrap distribution",
            "ci95_hi": "97.5th percentile of bootstrap distribution",
            "band_width_80": "ci80_hi - ci80_lo",
        },
        "selected_indicators": selected,
        "chosen_window": chosen_window,
        "n_positive_instances": n_pos_per_ind,
        "n_countries_scored": len(bands),
        "bands": bands,
    }

    out_path = args.output_dir / f"similarity-bands-{args.recipe_id}-{evaluation_year}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s", out_path)

    # Print summary (top-10 by risk_score)
    sorted_countries = sorted(bands, key=lambda c: -bands[c]["risk_score"])
    print()
    print(f"=== Top-10 bands for {args.recipe_id} (eval_year={evaluation_year}) ===")
    print(f"  {'Country':30s}  {'score':>6}  {'ci95':>14}  {'ci80':>14}  {'bw80':>6}")
    for country in sorted_countries[:10]:
        b = bands[country]
        print(
            f"  {country:30s}  {b['risk_score']:6.1f}"
            f"  [{b['ci95_lo']:5.1f}, {b['ci95_hi']:5.1f}]"
            f"  [{b['ci80_lo']:5.1f}, {b['ci80_hi']:5.1f}]"
            f"  {b['band_width_80']:6.1f}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(_main())
