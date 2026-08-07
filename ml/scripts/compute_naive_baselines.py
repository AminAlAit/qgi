"""compute_naive_baselines.py — greenfield (path-c) floor provenance (#113 / T20-R2).

For each recipe with NO prior score, compute the naive-baseline LOCO-AUC =
``max(NB1 persistence, NB2 single-best-indicator)`` under the SAME LOCO harness +
candidate set as the F-ML-1 walk (Ji-Hoon parity: this reuses ``build_samples`` +
``build_X_y`` + ``fit_predict_loco`` + ``univariate_loco_screen`` from
run_f_ml_1_poc — no re-implementation). Observed-only (JH-R1 firewall — events +
panels, no LOCF fill anywhere). The floor is then:

    relative = (naive_basis) + DELTA_LIFT          # naive_basis = point est, OR
                                                    # upper-CI for thin recipes (N_pos<150)
    LOCK_FLOOR = max(relative, ABS_FLOOR 0.70)      # Miriam absolute backstop

Emits a version-pinned per-recipe artifact (Tariq T20-R2-G): naive value + its
percentile-bootstrap CI + n_pos + panel_fingerprint + git commit + script version,
so the floor is reproducible + auditably pre-walk.

Deterministic, seed-pinned. Zero AWS (runs on a local --panel-dir; sync the S3
production panels down first if you want production-vintage provenance). Test-first.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent

# Floor-policy constants (per fleet-floor-annex.md, ratified 2026-05-25)
DELTA_LIFT = 0.03
ABS_FLOOR = 0.70
FLOOR_CAP = 0.90             # hard ceiling: max(naive+δ, 0.70) can never exceed this
                             # (truncation-leak bugfix facet 2, Majles 2026-05-25). When
                             # naive≈0.98 the relative floor would be 1.01 (impossible) →
                             # an unreachable floor that can never graduate. Cap at 0.90.
THIN_NPOS_CUT = 150          # below this → anchor the floor to the naive upper-CI (Kwame K11-R1)
SCREEN_WINDOW = 10           # univariate screen default window (§5.1)
N_BOOTSTRAP = 2000


def compute_floor(naive_auc: float, ci_hi: float, n_pos: int) -> tuple[float, float, str]:
    """Pure floor policy (testable). Returns (naive_basis, lock_floor, floor_basis).

    - Thin recipes (N_pos < THIN_NPOS_CUT) anchor to the naive upper-CI (Kwame K11-R1);
      others to the point estimate.
    - lock_floor = max(naive_basis + DELTA_LIFT, ABS_FLOOR), then HARD-CAPPED at
      FLOOR_CAP (bugfix facet 2): an uncapped floor >1.0 (when naive≈0.98) is
      unreachable and would silently doom an otherwise-strong recipe."""
    naive_basis = ci_hi if n_pos < THIN_NPOS_CUT else naive_auc
    relative_floor = naive_basis + DELTA_LIFT
    lock_floor = max(relative_floor, ABS_FLOOR)
    floor_basis = "relative" if relative_floor >= ABS_FLOOR else "absolute_0.70"
    if lock_floor > FLOOR_CAP:
        lock_floor = FLOOR_CAP
        floor_basis = "capped_0.90"
    return naive_basis, lock_floor, floor_basis


def persistence_feature(samples: pd.DataFrame, pos: pd.DataFrame) -> np.ndarray:
    """NB1 feature: per (country, year) sample, recency of the most recent PRIOR
    positive for that country. score = 1/(1 + years_since_last_prior_positive),
    or 0 if none. Causal (uses only events strictly before the sample year), so no
    label leakage — the classic 'past crises predict future crises' baseline.
    Panel-independent (events only)."""
    pos_years: dict[str, list[int]] = defaultdict(list)
    for _, r in pos.iterrows():
        pos_years[str(r["country"])].append(int(r["year"]))
    scores = []
    for _, r in samples.iterrows():
        c, y = str(r["country"]), int(r["year"])
        priors = [py for py in pos_years.get(c, []) if py < y]
        scores.append(1.0 / (1.0 + (y - max(priors))) if priors else 0.0)
    return np.asarray(scores, dtype=float).reshape(-1, 1)


def _bootstrap_auc_ci(probs: np.ndarray, labels: np.ndarray, n_boot: int = N_BOOTSTRAP,
                      seed: int = 0) -> tuple[float, float, float]:
    """Percentile bootstrap CI on AUC from pooled LOCO predictions. Returns
    (point, ci95_lo, ci95_hi). (Percentile, not BCa — a conservative-enough
    provenance band for a floor anchor; reuses drv.compute_auc.)"""
    probs = np.asarray(probs, float)
    labels = np.asarray(labels, int)
    point = drv.compute_auc(probs, labels)
    rng = np.random.default_rng(seed)
    n = len(labels)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        if len(np.unique(labels[idx])) < 2:
            continue
        boots.append(drv.compute_auc(probs[idx], labels[idx]))
    if not boots:
        return point, point, point
    return point, float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def compute_naive_baseline(recipe_id: str, positives_csv: Path, panel_dir: Path,
                           candidates: list[str], panels: dict[str, pd.DataFrame],
                           negatives_per_positive: int = 3, seed: int = 0,
                           screen_window: int = SCREEN_WINDOW,
                           n_bootstrap: int = N_BOOTSTRAP) -> dict[str, Any]:
    """Compute NB1 (persistence) + NB2 (single-best-indicator) LOCO-AUC for one
    recipe, then the naive baseline + floor. Parity: same build_samples + folds."""
    pos = pd.read_csv(positives_csv)
    pos["country"] = pos["country_id"].apply(drv.normalize_country_id)
    pos = pos.rename(columns={"event_year": "year"})
    pos["label"] = 1
    n_pos = int(len(pos))
    samples = drv.build_samples(pos, negatives_per_positive=negatives_per_positive, seed=seed)

    # NB1 — persistence (panel-free; all sample rows valid)
    Xp = persistence_feature(samples, pos)
    yp = samples["label"].to_numpy()
    cp = samples["country"].to_numpy()
    yrp = samples["year"].to_numpy()
    nb1 = drv.fit_predict_loco(Xp, yp, cp, yrp, architecture="LR", seed=seed)
    nb1_auc = float(nb1["global_auc"])

    # NB2 — single best indicator (max over the univariate LOCO screen)
    _, screen = drv.univariate_loco_screen(samples, candidates, panels,
                                            default_window=screen_window, top_n=len(candidates))
    nb2_vals = [v["univariate_loco_auc"] for v in screen.values()
                if not np.isnan(v["univariate_loco_auc"])]
    nb2_auc = float(max(nb2_vals)) if nb2_vals else float("nan")
    nb2_best_indicator = (max(screen, key=lambda k: (screen[k]["univariate_loco_auc"]
                          if not np.isnan(screen[k]["univariate_loco_auc"]) else -1.0))
                          if nb2_vals else None)

    # naive = max(NB1, NB2); CI from the winning baseline's pooled predictions
    if not np.isnan(nb2_auc) and nb2_auc >= nb1_auc:
        winner, pooled = "NB2_single_indicator", None
        naive_auc = nb2_auc
        # NB2 pooled predictions: re-run the winning indicator's LOCO to get pooled preds
        Xb, yb, cb, yrb = drv.build_X_y(samples, [nb2_best_indicator], screen_window, panels)
        res = drv.fit_predict_loco(Xb, yb, cb, yrb, architecture="LR", seed=seed)
        pooled = (np.asarray(res["probs"]), np.asarray(res["labels"]))
    else:
        winner, naive_auc = "NB1_persistence", nb1_auc
        pooled = (np.asarray(nb1["probs"]), np.asarray(nb1["labels"]))

    _, ci_lo, ci_hi = _bootstrap_auc_ci(pooled[0], pooled[1], n_boot=n_bootstrap, seed=seed)

    # Floor: thin recipes anchor to the upper-CI (Kwame K11-R1); cap at 0.90 (facet 2)
    naive_basis, lock_floor, floor_basis = compute_floor(naive_auc, ci_hi, n_pos)
    relative_floor = naive_basis + DELTA_LIFT

    return {
        "recipe_id": recipe_id,
        "n_pos": n_pos,
        "nb1_persistence_loco": round(nb1_auc, 4),
        "nb2_single_indicator_loco": (round(nb2_auc, 4) if not np.isnan(nb2_auc) else None),
        "nb2_best_indicator": nb2_best_indicator,
        "naive_winner": winner,
        "naive_loco": round(naive_auc, 4),
        "naive_ci95": [round(ci_lo, 4), round(ci_hi, 4)],
        "naive_basis_for_floor": round(naive_basis, 4),
        "delta_lift": DELTA_LIFT,
        "relative_floor": round(relative_floor, 4),
        "lock_floor": round(lock_floor, 4),
        "floor_cap": FLOOR_CAP,
        "floor_basis": floor_basis,
        "thin": n_pos < THIN_NPOS_CUT,
        "panel_fingerprint": drv.panel_data_fingerprint(panel_dir, positives_csv),
        "screen_window": screen_window,
        "negatives_per_positive": negatives_per_positive,
        "seed": seed,
    }


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=str(REPO_ROOT), text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recipes", nargs="+", help="recipe_ids to compute (default: all greenfield in --greenfield-file)")
    p.add_argument("--greenfield-file", type=Path, default=None,
                   help="JSON list of greenfield recipe_ids (no prior score)")
    p.add_argument("--shape-inputs-dir", type=Path, default=REPO_ROOT / "data" / "shape_inputs_v2")
    p.add_argument("--panel-dir", type=Path, default=REPO_ROOT / "data" / "parquet_panels")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "naive-baselines.json")
    p.add_argument("--negatives-per-positive", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    args = p.parse_args(argv)

    recipes = args.recipes or (json.loads(args.greenfield_file.read_text()) if args.greenfield_file else [])
    if not recipes:
        print("No recipes given (use --recipes or --greenfield-file).", file=sys.stderr)
        return 2

    candidates = drv.list_candidate_indicators(args.panel_dir)
    panels = {ind: drv.load_panel(ind, args.panel_dir) for ind in candidates}
    print(f"Loaded {len(candidates)} candidate panels from {args.panel_dir}")

    results = {}
    for rid in recipes:
        pcsv = args.shape_inputs_dir / rid / "positives.csv"
        if not pcsv.exists():
            print(f"  SKIP {rid}: no positives.csv", file=sys.stderr)
            continue
        print(f"Computing naive baseline for {rid} ...")
        try:
            r = compute_naive_baseline(rid, pcsv, args.panel_dir, candidates, panels,
                                       negatives_per_positive=args.negatives_per_positive,
                                       seed=args.seed, n_bootstrap=args.n_bootstrap)
        except Exception as exc:  # noqa: BLE001 — one bad recipe must not kill a multi-hour batch
            print(f"  ERROR {rid}: {exc}", file=sys.stderr)
            results[rid] = {"recipe_id": rid, "error": str(exc)}
            continue
        results[rid] = r
        print(f"  {rid}: naive={r['naive_loco']} ({r['naive_winner']}) "
              f"floor={r['lock_floor']} ({r['floor_basis']})")
        # Incremental write so a mid-batch interruption preserves completed recipes.
        args.out.write_text(json.dumps({
            "schema_version": 1, "policy": "fleet-floor-annex.md (2026-05-25)",
            "delta_lift": DELTA_LIFT, "abs_floor": ABS_FLOOR, "floor_cap": FLOOR_CAP,
            "thin_npos_cut": THIN_NPOS_CUT,
            "git_commit_sha": _git_sha(), "seed": args.seed, "partial": True, "baselines": results,
        }, indent=2), encoding="utf-8")

    payload = {
        "schema_version": 1,
        "policy": "fleet-floor-annex.md (5-Opus-Majles + founder, 2026-05-25)",
        "delta_lift": DELTA_LIFT, "abs_floor": ABS_FLOOR, "thin_npos_cut": THIN_NPOS_CUT,
        "git_commit_sha": _git_sha(), "seed": args.seed,
        "baselines": results,
    }
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(results)} recipes)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
