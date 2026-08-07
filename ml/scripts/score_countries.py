"""score_countries.py — F-ML-1 per-country × per-recipe scoring step (#967).

Productionises the local 2026-05-28 bake (`bake-scores-locally.py`) into a runnable
post-walk script. Reads a recipe's `f-ml-1-poc-summary.json`, reconstructs the
training sample with the SAME `build_samples` the walk used, refits XGBoost on the
LOCKED `(selected_indicators, chosen_window)` from the summary, then scores every
country at its most-recent year of feature support. SHAP attribution per country,
indicator movement, top-3 nearest-analogs, score distribution, and 5-fold-CV LOO
indicator sensitivity all land in one output JSON: `country-scores.json`, written
alongside the summary in the recipe's S3 prefix.

This is **post-walk**: bit-identity is preserved because we don't touch the walk
driver or any of its emit — we only consume `final_loco`-equivalent + summary +
positives, all of which are already-frozen artifacts.

Methodology notes:
  - Scoring uses a full-train fit (NOT LOCO). The card's existing `loco_auc`
    is the gold-standard OOS number; the scoring step's `train_auc` is in-sample
    and known to overfit. The scoring step's job is to RANK countries today, not
    to grade the recipe.
  - LOO indicator sensitivity uses 5-fold stratified CV — in-sample LOO drops are
    uniformly 0 on small recipes (XGBoost overfits to AUC≈1.0 on 300 rows), so the
    CV variant is the only honest version.
  - Nearest-analog uses cosine similarity in feature space (per indicator × 8
    feature components = 8*K-dim vectors). NOT a hand-tuned metric — just the
    geometry the model itself sees.

Run (post-walk):
    python score_countries.py \\
        --recipe-id banking_and_financial_crisis \\
        --summary-path /tmp/.../f-ml-1-poc-summary.json \\
        --panel-dir /app/data/parquet_panels \\
        --positives-csv /app/data/shape_inputs_v2/banking_and_financial_crisis/positives.csv \\
        --output-dir /tmp/.../
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Import the same helpers the walk used — re-uses extract_features_for_indicator,
# build_X_y, build_samples so the scoring step's training-set construction is
# BIT-IDENTICAL to the walk's. No drift between fit-target and score-target.
import run_f_ml_1_poc as drv  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("score-countries")

_OUTPUT_FILENAME = "country-scores.json"


# ---------------------------------------------------------------------------
# Pure helpers (testable; no I/O)
# ---------------------------------------------------------------------------


def normalize_country_id(s: str) -> str:
    """Match the walk's country normalization: `_` -> ` ` then `.title()`. The
    positives.csv stores lower-snake (`albania`) but the panel parquet stores
    title-case (`Albania`)."""
    return s.replace("_", " ").title()


def cos_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors (used for nearest-analog matching).
    Returns 0.0 on either-zero-norm rather than NaN — a zero feature vector
    cannot have a meaningful analog."""
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def signal_share_per_indicator(shap_row: np.ndarray, n_features_per_ind: int = 8
                                 ) -> list[float]:
    """Aggregate |shap| over each indicator's 8-feature group, then normalise to
    percentage share. Returns list of percent shares aligned to the indicator
    order in `selected_indicators`. The 8 features per indicator are the
    canonical (last/mean/std/slope/accel/tertile1-3) z-score components from
    `extract_features_for_indicator`."""
    a = np.abs(shap_row).reshape(-1, n_features_per_ind)
    per = a.sum(axis=1)
    total = per.sum()
    if total <= 0:
        return [0.0] * len(per)
    return (per / total * 100.0).tolist()


def signed_shap_per_indicator(shap_row: np.ndarray, n_features_per_ind: int = 8
                               ) -> list[float]:
    """Signed sum of raw SHAP over each indicator's 8-feature group (frontend §A.1 /
    #974). Positive => this indicator's trajectory pushes the country TOWARD the event
    class; negative => away. Same 8-feature grouping as `signal_share_per_indicator`,
    which takes |shap| and discards the sign; this keeps the sign for the country-profile
    'Why these scores -> signed magnitude' panel."""
    s = np.asarray(shap_row).reshape(-1, n_features_per_ind)
    return s.sum(axis=1).tolist()


def histogram_bins(scores: np.ndarray, n_bins: int = 20) -> dict[str, Any]:
    """20 bins of 5pp width on the [0, 100] score axis. Last bin inclusive on
    100 so a score of exactly 100 isn't dropped (mirrors the calibration-bins
    convention from beta_calibration.py)."""
    if scores.size == 0:
        return {"histogram": [], "median": None, "p90": None, "p99": None, "max": None}
    bins = []
    width = 100 / n_bins
    for i in range(n_bins):
        lo, hi = i * width, (i + 1) * width
        if i == n_bins - 1:
            mask = (scores >= lo) & (scores <= hi)
        else:
            mask = (scores >= lo) & (scores < hi)
        bins.append({"bin_lo": float(lo), "bin_hi": float(hi), "count": int(mask.sum())})
    return {
        "histogram": bins,
        "median": float(round(np.median(scores), 1)),
        "p90": float(round(np.percentile(scores, 90), 1)),
        "p99": float(round(np.percentile(scores, 99), 1)),
        "max": float(round(scores.max(), 1)),
    }


def country_movement_12y(country: str, panels: dict[str, pd.DataFrame],
                          selected: list[str], window: int = 12) -> list[dict[str, Any]]:
    """Per indicator, the last 12 annual data points as a z-score trajectory
    (z-scored within the country's own recent history — the relative-change
    signal, not cross-country level). z_score_change = last - first.

    Also emits `trajectory_window` + `trajectory_window_years` (frontend §A.2): the
    last `window` annual points z-scored against the country's 25y baseline ending at
    its latest year. This mirrors the walk's `extract_trajectory_signature_full`
    baseline-z so the line overlays the canonical `trajectory_alignment` shape on the
    SAME scale (see the inline comment); distinct from `trajectory_12q`'s within-window z."""
    out: list[dict[str, Any]] = []
    for ind in selected:
        cdf = panels[ind][panels[ind]["country"] == country].sort_values("year")
        if cdf.empty:
            out.append({"code": ind, "name": None, "trajectory_12q": [], "z_score_change": None,
                        "trajectory_window": [], "trajectory_window_years": []})
            continue
        recent = cdf.tail(12)
        vals = recent["value"].to_numpy(dtype=float)
        mu = float(vals.mean())
        sd = float(vals.std()) if vals.size > 1 else 0.0
        sd = max(sd, 1e-9)
        traj = ((vals - mu) / sd).tolist()
        zchg = float(traj[-1] - traj[0]) if len(traj) >= 2 else None
        # §A.2 full canonical window, z'd against the country's 25y baseline ending at
        # its latest year (mirrors run_f_ml_1_poc.extract_trajectory_signature_full) so
        # the country's current run-up overlays the canonical trajectory_alignment shape
        # on the SAME per-country 25y-baseline z-scale, not the within-window z used by 12q.
        latest = int(cdf["year"].max())
        base = cdf[(cdf["year"] >= latest - 24) & cdf["value"].notna()]
        bvals = base["value"].to_numpy(dtype=float)
        bmu = float(bvals.mean()) if bvals.size else 0.0
        # match the walk's guard exactly (`baseline.std() or 1.0`): a flat baseline
        # -> 1.0 so a constant run-up reads as 0 movement, not a blown-up z.
        bsd = (float(bvals.std()) if bvals.size > 1 else 0.0) or 1.0
        wdf = cdf[(cdf["year"] >= latest - int(window) + 1) & cdf["value"].notna()]
        wtraj = [round(float((v - bmu) / bsd), 4) for v in wdf["value"].to_numpy(dtype=float)]
        wyears = [int(y) for y in wdf["year"].tolist()]
        out.append({"code": ind, "name": None, "trajectory_12q": traj, "z_score_change": zchg,
                    "trajectory_window": wtraj, "trajectory_window_years": wyears})
    return out


# ---------------------------------------------------------------------------
# Heavy lifters (XGBoost + SHAP — imported lazily so the script's module load
# is cheap and so unit tests can skip them if SHAP isn't installed locally)
# ---------------------------------------------------------------------------


def fit_xgb(X: np.ndarray, y: np.ndarray, *, seed: int = 0, n_jobs: int = 4):
    from xgboost import XGBClassifier
    n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())
    spw = (n_neg / max(n_pos, 1)) if n_pos > 0 else 1.0
    clf = XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        reg_alpha=0.1, scale_pos_weight=spw, eval_metric="logloss",
        random_state=seed, verbosity=0, n_jobs=n_jobs,
    )
    X = np.where(np.isfinite(X), X, 0.0)
    clf.fit(X, y)
    return clf


def cv_auc(X: np.ndarray, y: np.ndarray, *, n_splits: int = 5, seed: int = 0
            ) -> float | None:
    """5-fold stratified CV AUC for LOO indicator-sensitivity ablation. Returns
    None when fold-construction fails (insufficient class balance)."""
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import roc_auc_score
    X = np.where(np.isfinite(X), X, 0.0)
    min_class = int(min((y == 1).sum(), (y == 0).sum()))
    if min_class < n_splits:
        return None
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    aucs: list[float] = []
    for tr, te in skf.split(X, y):
        clf = fit_xgb(X[tr], y[tr], seed=seed, n_jobs=4)
        try:
            aucs.append(roc_auc_score(y[te], clf.predict_proba(X[te])[:, 1]))
        except ValueError:
            continue
    return float(np.mean(aucs)) if aucs else None


# ---------------------------------------------------------------------------
# Per-country feature extraction at "today" (most recent supportable year)
# ---------------------------------------------------------------------------


def build_today_X(selected: list[str], panels: dict[str, pd.DataFrame],
                   window: int) -> tuple[np.ndarray, list[str], list[int]]:
    """For each country with feature support across ALL selected indicators,
    extract the feature vector at that country's most-recent year with full
    coverage. Backs off year-by-year up to 5 years if a particular year fails.

    Returns (X, countries_kept, eval_years_kept). X shape: (n_countries, 8*K)."""
    all_countries = sorted(set.intersection(
        *[set(p["country"].unique()) for p in panels.values()]
    ))
    rows: list[np.ndarray] = []
    keep_c: list[str] = []
    keep_y: list[int] = []
    for c in all_countries:
        # Per-indicator most-recent year — take the MIN so all indicators have data
        years = []
        for ind in selected:
            cdf = panels[ind][panels[ind]["country"] == c]
            if cdf.empty:
                years = []
                break
            years.append(int(cdf["year"].max()))
        if not years:
            continue
        target_year = min(years)
        feats: np.ndarray | None = None
        # Try the country's most-recent year first, then back off year-by-year up to
        # 5 years if `extract_features_for_indicator` returns None at the head year
        # (insufficient window history for one of the selected indicators).
        for try_y in range(target_year, target_year - 5, -1):
            parts: list[np.ndarray] = []
            ok = True
            for ind in selected:
                f = drv.extract_features_for_indicator(panels[ind], c, try_y, window)
                if f is None:
                    ok = False
                    break
                parts.append(f)
            if ok:
                feats = np.concatenate(parts)
                target_year = try_y
                break
        if feats is None:
            continue
        rows.append(feats)
        keep_c.append(c)
        keep_y.append(target_year)
    if not rows:
        return np.zeros((0, len(selected) * 8)), [], []
    return np.vstack(rows), keep_c, keep_y


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def score_recipe(*, summary: dict, positives_df: pd.DataFrame,
                  panels: dict[str, pd.DataFrame], seed: int = 0) -> dict[str, Any]:
    """Score a single recipe end-to-end. Returns the country-scores document
    ready for json.dump. Pure: no I/O; caller owns the panels + positives load."""
    import shap

    selected = summary["greedy_outer_loop"]["selected_indicators"]
    window = int(summary["greedy_outer_loop"]["chosen_window"])
    rid = summary.get("recipe_id", "unknown")
    LOG.info("scoring %s | selected=%s window=%d", rid, selected, window)

    # 1. Reconstruct the same training sample the walk used (positives + time-matched negs).
    samples = drv.build_samples(positives_df, negatives_per_positive=3, seed=seed)
    X_tr, y_tr, _, _ = drv.build_X_y(samples, selected, window, panels)
    if len(X_tr) == 0:
        raise RuntimeError(f"{rid}: build_X_y produced 0 training rows; cannot score")
    X_tr = np.where(np.isfinite(X_tr), X_tr, 0.0)

    # 2. Refit XGBoost on the FULL train set (not LOCO) — the scoring model.
    clf = fit_xgb(X_tr, y_tr, seed=seed)
    from sklearn.metrics import roc_auc_score
    train_auc = float(roc_auc_score(y_tr, clf.predict_proba(X_tr)[:, 1]))
    cv_full = cv_auc(X_tr, y_tr, seed=seed)
    LOG.info("  train_rows=%d train_auc=%.4f cv_auc=%s", len(X_tr), train_auc,
              f"{cv_full:.4f}" if cv_full is not None else "n/a")

    # 3. Build feature matrix for every country at "today".
    X_today, countries, eyears = build_today_X(selected, panels, window)
    LOG.info("  scored_countries=%d", len(countries))
    if len(X_today) == 0:
        raise RuntimeError(f"{rid}: no countries had feature support; nothing to score")

    probs = clf.predict_proba(X_today)[:, 1]
    pranks = (pd.Series(probs).rank(pct=True) * 100).round(1).tolist()
    rank_order = pd.Series(probs).rank(method="min", ascending=False).astype(int).tolist()

    # 4. SHAP per country (TreeExplainer is fast on XGBoost: ms per row).
    shap_vals = shap.TreeExplainer(clf).shap_values(X_today)
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[0]
    shap_arr = np.asarray(shap_vals)

    # 5. 5-fold-CV LOO indicator-sensitivity ablation.
    loo: list[dict[str, Any]] = []
    for drop in selected:
        keep = [i for i in selected if i != drop]
        if not keep:
            loo.append({"code": drop, "name": None, "auc_with": cv_full,
                         "auc_without": None, "auc_drop": None,
                         "notes": "single-indicator recipe; cannot ablate"})
            continue
        Xk, yk, _, _ = drv.build_X_y(samples, keep, window, panels)
        if len(Xk) == 0:
            loo.append({"code": drop, "name": None, "auc_with": cv_full,
                         "auc_without": None, "auc_drop": None,
                         "notes": "ablation produced empty sample"})
            continue
        a = cv_auc(Xk, yk, seed=seed)
        if a is None or cv_full is None:
            loo.append({"code": drop, "name": None, "auc_with": cv_full,
                         "auc_without": a, "auc_drop": None,
                         "notes": "CV folds failed"})
            continue
        loo.append({"code": drop, "name": None,
                     "auc_with": round(cv_full, 4),
                     "auc_without": round(a, 4),
                     "auc_drop": round(cv_full - a, 4)})

    # 6. Nearest-analog: cosine similarity to each training positive's feature vector.
    pos_only = samples[samples["label"] == 1]
    Xp, _, cp_arr, yp_arr = drv.build_X_y(pos_only, selected, window, panels)
    Xp = np.where(np.isfinite(Xp), Xp, 0.0)
    pos_pairs = list(zip(cp_arr.tolist() if len(Xp) else [],
                          yp_arr.tolist() if len(Xp) else []))

    # 7. Compose per-country scoreboard rows.
    pos_country_set = set(positives_df["country"].tolist())
    scores_rows: list[dict[str, Any]] = []
    for i, c in enumerate(countries):
        ss = signal_share_per_indicator(shap_arr[i])
        sv = signed_shap_per_indicator(shap_arr[i])  # §A.1/#974 signed magnitude
        shap_attr = [{"code": ind, "name": None, "signal_share_pct": round(ss[j], 1),
                      "shap_value": round(float(sv[j]), 6)}
                     for j, ind in enumerate(selected)]
        analogs: list[dict[str, Any]] = []
        if len(Xp):
            sims = [(cos_sim(X_today[i], Xp[k]), pos_pairs[k][0], pos_pairs[k][1])
                    for k in range(len(Xp))]
            sims.sort(key=lambda t: -t[0])
            seen: set[str] = set()
            for s_val, c_pos, y_pos in sims:
                if c_pos in seen:
                    continue
                analogs.append({"country": c_pos, "year": int(y_pos),
                                 "match_score": round(float(s_val), 4),
                                 "weak_analog": bool(s_val < 0.7)})
                seen.add(c_pos)
                if len(analogs) >= 3:
                    break
        scores_rows.append({
            "iso": None,  # FE resolves via lib/country-aliases.ts
            "name": c,
            "score": float(round(pranks[i], 1)),
            "rank": int(rank_order[i]),
            "eval_year": int(eyears[i]),
            "in_evidence_base": c in pos_country_set,
            "delta_vs_prior_vintage": None,  # first vintage; filled by vintage-rollup if prior exists
            "shap_attribution": shap_attr,
            "indicator_movement": country_movement_12y(c, panels, selected, window),
            "nearest_analogs": analogs,
        })

    scores_rows.sort(key=lambda r: r["rank"])

    return {
        "recipe_id": rid,
        "vintage_walked_at_utc": summary.get("filed"),
        "n_countries_scored": len(countries),
        "train_auc": round(train_auc, 4),
        "cv_auc_full": round(cv_full, 4) if cv_full is not None else None,
        "scoring_method": (
            "Full-train XGBoost refit on the LOCKED (selected_indicators, chosen_window) "
            "from the walk summary; scored at each country's most-recent year of feature "
            "support. SHAP signal_share_pct is |shap| aggregated over the 8 features per "
            "indicator. LOO indicator_sensitivity uses 5-fold stratified CV (not in-sample, "
            "which overfits to AUC=1.0 on small recipes). The walk's `stats.loco_auc` is the "
            "gold-standard OOS discrimination number; train_auc and cv_auc_full are "
            "internal references for the LOO ablation."
        ),
        "scores": scores_rows,
        "score_distribution": histogram_bins(np.array([r["score"] for r in scores_rows])),
        "indicator_sensitivity_loo": loo,
    }


# ---------------------------------------------------------------------------
# Phase B — per-(country, year) leave-country-out trajectory scoring (#per-trend-news)
#
# For the lead-lag test (does structure lead the news?). For each candidate country C
# with event_year Y, refit XGBoost with C HELD OUT of training (leave-country-out =
# no memorization), then score C at each year in [Y - years_back, Y]. Because
# extract_features_for_indicator(panel, C, y, window) reads ONLY data in [y-window, y-1]
# (verified), each per-year score is temporally leakage-free too. Emits a tidy CSV the
# alignment harness joins against hf-trend-pulse.json. Opt-in; does not touch score_recipe.
# ---------------------------------------------------------------------------

# scores.json names vs panel/positives names that differ. Extend as needed at runtime
# (a miss logs a warning and the candidate is skipped, never silently mis-scored).
PHASE_B_ALIASES = {
    "Turkiye": "Turkey", "Turkey": "Turkiye",
    "Czechia": "Czech Republic", "Cote D'Ivoire": "Ivory Coast", "Cote D'ivoire": "Ivory Coast",
}


def _resolve_panel_country(name: str, panel_countries: set[str]) -> str | None:
    """Resolve a candidate country name to the exact string the panels use. Tries
    normalized form, then the alias map, then case-insensitive. Returns None on a miss
    (caller warns + skips — fail loud, never mis-attribute)."""
    n = normalize_country_id(str(name))
    if n in panel_countries:
        return n
    a = PHASE_B_ALIASES.get(n)
    if a and a in panel_countries:
        return a
    low = {c.lower(): c for c in panel_countries}
    return low.get(n.lower())


def _resolve_positives_to_panel(positives_df: pd.DataFrame,
                                 panel_countries: set[str]) -> pd.DataFrame:
    """Map the positives' country names into the PANEL namespace, so leave-country-out
    filtering and the in_evidence_base flag operate in the SAME namespace as the resolved
    candidate `pc`. Without this, positives.csv "Turkey" vs panel "Turkiye" would defeat the
    `country != pc` LOCO filter and silently leave the held-out country in training (leakage
    on exactly the alias-mapped countries). Unresolvable names are left as-is."""
    df = positives_df.copy()
    df["country"] = df["country"].apply(
        lambda c: _resolve_panel_country(c, panel_countries) or normalize_country_id(str(c)))
    return df


def score_phase_b(*, summary: dict, positives_df: pd.DataFrame,
                   panels: dict[str, pd.DataFrame],
                   candidates: list[dict], years_back: int = 4, seed: int = 0
                   ) -> pd.DataFrame:
    """Per-(country, year) leave-country-out trajectory scores for the candidate set.

    candidates: list of {"name": <country>, "event_year": <int>, ...} (multiple event_years
    per country are merged into one LOCO fit, scored across the union of year-windows).
    Returns a DataFrame: country, year, predicted_probability, event_year(s), in_evidence_base,
    n_train_rows, note.  predicted_probability is the raw LOCO-model probability (the WITHIN-country
    trajectory shape/timing is what the lead-lag test reads — not absolute calibration)."""
    selected = summary["greedy_outer_loop"]["selected_indicators"]
    window = int(summary["greedy_outer_loop"]["chosen_window"])
    panel_countries = set.intersection(*[set(p["country"].unique()) for p in panels.values()])
    # Resolve positives into the panel namespace ONCE — so the LOCO filter and the
    # in_evidence_base flag below use the same names as the resolved candidate `pc`.
    pos_df_norm = _resolve_positives_to_panel(positives_df, panel_countries)
    pos_country_set = set(pos_df_norm["country"].tolist())

    # group candidate event-years by resolved panel country (one LOCO fit per country)
    by_country: dict[str, list[int]] = {}
    for cand in candidates:
        pc = _resolve_panel_country(cand.get("name", ""), panel_countries)
        if pc is None:
            LOG.warning("phase-b: candidate %r not found in panels — SKIPPED", cand.get("name"))
            continue
        by_country.setdefault(pc, []).append(int(cand["event_year"]))

    rows: list[dict[str, Any]] = []
    for pc, eyears in sorted(by_country.items()):
        # Leave-country-out: drop ALL of pc's rows (as positive AND as time-matched negative),
        # both now in the panel namespace so an alias-mapped country is genuinely held out.
        pos_loco = pos_df_norm[pos_df_norm["country"] != pc]
        samples = drv.build_samples(pos_loco, negatives_per_positive=3, seed=seed)
        samples = samples[samples["country"].astype(str) != pc]
        X_tr, y_tr, _, _ = drv.build_X_y(samples, selected, window, panels)
        if len(X_tr) == 0:
            LOG.warning("phase-b: %s — LOCO train set empty; SKIPPED", pc)
            continue
        X_tr = np.where(np.isfinite(X_tr), X_tr, 0.0)
        clf = fit_xgb(X_tr, y_tr, seed=seed)
        in_evb = pc in pos_country_set
        model_scope = f"loco_{pc}"  # so the harness never aggregates raw probs across LOCO models
        years = sorted({y for ey in eyears for y in range(ey - years_back, ey + 1)})
        for y in years:
            parts: list[np.ndarray] = []
            ok = True
            for ind in selected:
                f = drv.extract_features_for_indicator(panels[ind], pc, y, window)
                if f is None:
                    ok = False
                    break
                parts.append(f)
            base = {"country": pc, "year": y,
                    "event_years": ",".join(map(str, sorted(set(eyears)))),
                    "in_evidence_base": in_evb, "model_scope": model_scope,
                    "n_train_rows": int(len(X_tr))}
            if not ok:
                rows.append({**base, "predicted_probability": None, "note": "insufficient_history"})
                continue
            vec = np.where(np.isfinite(np.concatenate(parts)), np.concatenate(parts), 0.0)
            prob = float(clf.predict_proba(vec.reshape(1, -1))[0, 1])
            rows.append({**base, "predicted_probability": round(prob, 6), "note": ""})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recipe-id", required=True)
    ap.add_argument("--summary-path", required=True, type=Path,
                     help="Path to the recipe's f-ml-1-poc-summary.json (walk output).")
    ap.add_argument("--panel-dir", required=True, type=Path,
                     help="Directory containing per-indicator parquet panels.")
    ap.add_argument("--positives-csv", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=0)
    # Phase B (opt-in): produce per-(country,year) leave-country-out trajectory CSV instead
    # of the standard country-scores.json.
    ap.add_argument("--phase-b-candidates", type=Path, default=None,
                     help="JSON list of {name, event_year} candidates. Switches to Phase B mode.")
    ap.add_argument("--phase-b-out", type=Path, default=None,
                     help="Output CSV for Phase B per-(country,year) predictions.")
    ap.add_argument("--years-back", type=int, default=4,
                     help="Phase B: years before each event_year to score (default 4).")
    args = ap.parse_args(argv)

    summary = json.loads(args.summary_path.read_text(encoding="utf-8"))
    selected = summary["greedy_outer_loop"]["selected_indicators"]

    # Load only the panels the recipe needs (cheap).
    panels: dict[str, pd.DataFrame] = {}
    for ind in selected:
        p = args.panel_dir / ind / f"{ind}.parquet"
        if not p.exists():
            LOG.error("panel parquet missing: %s", p)
            return 2
        panels[ind] = pd.read_parquet(p)[["country", "year", "value"]]

    raw_pos = pd.read_csv(args.positives_csv)
    pos_df = pd.DataFrame({
        "country": raw_pos["country_id"].map(normalize_country_id),
        "year":    raw_pos["event_year"].astype(int),
        "label":   1,
    })

    if args.phase_b_candidates is not None:
        if args.phase_b_out is None:
            LOG.error("--phase-b-candidates requires --phase-b-out")
            return 2
        cand_doc = json.loads(args.phase_b_candidates.read_text(encoding="utf-8"))
        # accept either a bare list or the phase_b_candidates.json shape (per-trend keys)
        if isinstance(cand_doc, dict):
            key = f"{args.recipe_id}_testable"
            candidates = cand_doc.get(key) or cand_doc.get(args.recipe_id) or []
        else:
            candidates = cand_doc
        if not candidates:
            LOG.error("no candidates for recipe %s in %s", args.recipe_id, args.phase_b_candidates)
            return 2
        df = score_phase_b(summary=summary, positives_df=pos_df, panels=panels,
                            candidates=candidates, years_back=args.years_back, seed=args.seed)
        args.phase_b_out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.phase_b_out, index=False)
        n_ok = int(df["predicted_probability"].notna().sum()) if len(df) else 0
        LOG.info("phase-b: wrote %s (%d rows, %d scored, %d countries)",
                  args.phase_b_out, len(df), n_ok, df["country"].nunique() if len(df) else 0)
        return 0

    out_doc = score_recipe(summary=summary, positives_df=pos_df, panels=panels,
                              seed=args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / _OUTPUT_FILENAME
    out_path.write_text(json.dumps(out_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    LOG.info("wrote %s (n_countries_scored=%d)", out_path, out_doc["n_countries_scored"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
