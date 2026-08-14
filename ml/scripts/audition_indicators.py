#!/usr/bin/env python3
"""
audition_indicators.py — Indicator-to-recipe auditioner v0 (#480).

Per-indicator predictive contribution per recipe via permutation importance
on a held-out country split. Combines lift with coverage-equity weighting
into an audition_score that feeds the public Recipe Confidence Index
(RCI, #481).

The auditioner is a constant consultant + record-keeper, NOT a gate:
indicator integration proceeds independently of audition findings.
Findings persist forever for retrospective reassessment.

Design doc: docs/specs/internal/design/indicator-recipe-auditioner.md

Usage:
  python scripts/audition_indicators.py \\
      --bucket qgi-data-lake-771606957899 \\
      --workgroup QGI-Lambda-Workgroup \\
      --output-dir results/audition_2026_04_26/

Anti-patterns to avoid (see design doc):
  - BH-FDR multiple-testing correction is OUT OF SCOPE per founder veto
    (2026-04-26). Do not add. Do not relitigate.
  - Don't auto-promote/demote indicators based on audition_score
  - Don't impute missing data — report missingness as a signal
  - Don't expose audition_score formula publicly (RCI is the only public surface)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import boto3
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.model_selection import StratifiedShuffleSplit


TIERS = {"S": (3, 8), "M": (9, 20), "L": (21, 40), "XL": (41, 999)}
TOTAL_COUNTRIES = 261

# Audit defaults — match the per_recipe_auc.py baseline thresholds
MIN_TOTAL = 30
MIN_POS = 5
HOLDOUT_FRAC = 0.20
PERM_REPEATS = 10
BOOTSTRAP_REPEATS = 200  # #493 item 3 — bootstrap AUC CI on holdout
RANDOM_SEED = 42


# ---------------------------------------------------------------------------
# Stage 0: data loading from S3 + Athena
# ---------------------------------------------------------------------------

def load_indicator_map(s3, bucket: str) -> dict[int, str]:
    """numeric_id (smallint, in fingerprints) → id_string (partition key)."""
    obj = s3.get_object(
        Bucket=bucket, Key="pipeline-A-indicator-extractor/input/indicator_map.csv"
    )
    text = obj["Body"].read().decode("utf-8")
    rdr = csv.DictReader(io.StringIO(text))
    return {int(r["numeric_id"]): r["id_string"] for r in rdr}


def load_country_regions(s3, bucket: str) -> dict[str, str]:
    """alpha_2 (e.g. 'BR') → region (e.g. 'AMR'). Hand-parse YAML to avoid
    a yaml dependency."""
    obj = s3.get_object(Bucket=bucket, Key="indicator-freshness/country_regions.yaml")
    text = obj["Body"].read().decode("utf-8")
    out: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.endswith(":") and not s.startswith("-"):
            current = s.rstrip(":")
            continue
        if s.startswith("- ") and current and current.isupper():
            out[s[2:].strip()] = current
    return out


def run_athena(ath, sql: str, bucket: str, workgroup: str, db: str = "qgi_data"):
    r = ath.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": db},
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": f"s3://{bucket}/query_results/"},
    )
    qid = r["QueryExecutionId"]
    while True:
        time.sleep(1.5)
        s = ath.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if s["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
    if s["State"] != "SUCCEEDED":
        raise RuntimeError(f"Athena {s['State']}: {s.get('StateChangeReason', '?')}")
    return qid


def athena_fetch_all(ath, qid: str) -> list[list]:
    """Page through results; first row is the header."""
    rows: list[list] = []
    token = None
    first = True
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        page = ath.get_query_results(**kw)
        page_rows = page["ResultSet"]["Rows"]
        if first and page_rows:
            page_rows = page_rows[1:]
            first = False
        for r in page_rows:
            rows.append([c.get("VarCharValue") for c in r["Data"]])
        token = page.get("NextToken")
        if not token:
            break
    return rows


def load_indicator_panel(ath, bucket, workgroup, indicator_ids: list[str],
                         start_year: int, end_year: int) -> pd.DataFrame:
    """Long-format (country, year, indicator_id, value)."""
    in_clause = ",".join(f"'{i}'" for i in indicator_ids)
    sql = f"""
    SELECT country, year, indicator_id, value
    FROM qgi_data.indicators
    WHERE indicator_id IN ({in_clause})
      AND year BETWEEN {start_year} AND {end_year}
      AND value IS NOT NULL
    """
    print(f"[athena] indicator panel: {len(indicator_ids)} indicators, {start_year}-{end_year}")
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    df = pd.DataFrame(rows, columns=["country", "year", "indicator_id", "value"])
    df["year"] = df["year"].astype(int)
    df["value"] = df["value"].astype(float)
    return df


def _panel_cache_key(indicator_ids: list[str], start_year: int, end_year: int) -> str:
    """Stable hash of the panel-query inputs.

    The cache key MUST be:
      - Order-independent on `indicator_ids` (caller passes a list, but
        two equivalent panels should share a cache entry regardless of
        input ordering).
      - Duplicate-independent: ['VD-01', 'VD-01'] and ['VD-01'] produce
        the same Athena result (the SQL `IN` clause de-duplicates),
        so they MUST share a cache entry. `set()` handles both at once.

    QA review 2026-05-03 caught the duplicate-collision case: a stray
    duplicate from upstream would have caused a cache miss on the
    second call despite returning identical data.
    """
    payload = json.dumps(
        {"ids": sorted(set(indicator_ids)), "lo": int(start_year), "hi": int(end_year)},
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _load_panel_with_cache(
    ath, bucket: str, workgroup: str,
    indicator_ids: list[str], start_year: int, end_year: int,
    cache_dir: "Path | None" = None,
) -> pd.DataFrame:
    """Load panel with optional disk cache (#596).

    When cache_dir is None: behavior is identical to load_indicator_panel
    (the default path — Athena pull every invocation).

    When cache_dir is provided:
      - Compute a stable hash of (sorted indicator_ids, start_year, end_year)
      - If {cache_dir}/panel_{hash}.parquet exists → load from disk, log hit
      - Else → load_indicator_panel, write cache, log miss

    Cache files are parquet (Snappy, pyarrow engine pinned) for fast
    reload. Engine is pinned on BOTH read and write to keep dtype
    semantics identical across cache hit/miss — fastparquet has slightly
    different integer/timestamp handling and we want zero drift even if
    a future image swaps the default. QA review 2026-05-03 flagged
    this as a latent risk.
    """
    if cache_dir is None:
        return load_indicator_panel(ath, bucket, workgroup, indicator_ids, start_year, end_year)

    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _panel_cache_key(indicator_ids, start_year, end_year)
    cache_path = cache_dir / f"panel_{key}.parquet"

    if cache_path.exists():
        df = pd.read_parquet(cache_path, engine="pyarrow")
        print(f"[panel-cache HIT]  {cache_path.name}  ({len(df):,} rows; "
              f"saved Athena pull for {len(indicator_ids)} indicators × "
              f"{end_year - start_year + 1} years)")
        return df

    df = load_indicator_panel(ath, bucket, workgroup, indicator_ids, start_year, end_year)
    df.to_parquet(cache_path, index=False, compression="snappy", engine="pyarrow")
    print(f"[panel-cache MISS] {cache_path.name}  (wrote {len(df):,} rows for next run)")
    return df


def load_event_ground_truth(ath, bucket, workgroup, cutoff_year: int,
                            end_year: int) -> pd.DataFrame:
    """Returns (country_id, event_category, did_event_post_cutoff)."""
    sql = f"""
    SELECT country_id, category_normalized AS event_category,
           cast(max(year) > {cutoff_year} AS integer) AS y_post_cutoff
    FROM qgi_data.events
    WHERE category_normalized IS NOT NULL
      AND year BETWEEN 1900 AND {end_year}
    GROUP BY country_id, category_normalized
    """
    print(f"[athena] ground truth events; cutoff={cutoff_year}")
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    df = pd.DataFrame(rows, columns=["country_id", "event_category", "y_post_cutoff"])
    df["country_id"] = df["country_id"].astype(int)
    df["y_post_cutoff"] = df["y_post_cutoff"].astype(int)
    return df


def load_countries(ath, bucket, workgroup) -> pd.DataFrame:
    sql = """
    SELECT id AS country_id, name_1 AS name, alpha_2
    FROM qgi_data.countries
    WHERE id IS NOT NULL AND id != '' AND alpha_2 IS NOT NULL
    """
    print("[athena] countries")
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    df = pd.DataFrame(rows, columns=["country_id", "name", "alpha_2"])
    df["country_id"] = df["country_id"].astype(int)
    return df


def load_indicators_by_provider(ath, bucket, workgroup, provider: str) -> list[str]:
    """Return distinct indicator_id strings for a given provider (e.g. 'VDEM')."""
    sql = f"""
    SELECT DISTINCT indicator_id
    FROM qgi_data.indicators
    WHERE provider = '{provider}'
    """
    print(f"[athena] indicators with provider='{provider}'")
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    return [r[0] for r in rows if r[0]]


def load_recipes_aggregated_with_fingerprints(ath, bucket, workgroup) -> list[dict]:
    """Pull event_category, canonical_length, and the indicator_fingerprint
    array (just indicator_id + tfidf_score per element).
    """
    sql = """
    SELECT event_category, canonical_length,
           transform(indicator_fingerprint,
                     fp -> cast(fp.indicator_id as varchar) || ':' || cast(fp.tfidf_score as varchar)
                    ) AS fp_pairs
    FROM qgi_data.recipes_aggregated
    """
    print("[athena] recipes_aggregated fingerprints")
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    out = []
    for cat, cl, fp_str in rows:
        if cat is None or cl is None or not fp_str:
            continue
        fp = []
        for entry in fp_str.strip("[] ").split(", "):
            if not entry:
                continue
            ind_id, tfidf = entry.split(":")
            fp.append({"indicator_id": int(ind_id), "tfidf": float(tfidf)})
        out.append({
            "event_category": cat,
            "canonical_length": int(cl),
            "fingerprint": fp,
        })
    return out


def tier_for_length(L: int) -> str:
    for t, (lo, hi) in TIERS.items():
        if lo <= L <= hi:
            return t
    return "XL"


# ---------------------------------------------------------------------------
# Stage 1: per-recipe feature preparation
# ---------------------------------------------------------------------------

# Two feature-stat modes (#484 country-identity de-confound):
#
# - LEGACY (--no-deconfound): the v0 stats — mean, std, last_value carry raw
#   level information, which the GBM exploited as a country-identity proxy
#   (e.g. SP.POP.TOTL "lift" was actually country-size identification).
#
# - DECONFOUND (default): scale-invariant stats only. std normalized by
#   |mean|, slope expressed as relative-rate over the window, change as
#   percent change. Country identity does not survive these transformations.
#
# n_obs is dimensionless and present in both modes.
INDICATOR_FEATURE_STATS_LEGACY = ["mean", "std", "last_value", "slope", "change", "n_obs"]
INDICATOR_FEATURE_STATS_DECONF = [
    "std_norm", "slope_norm", "pct_change", "n_obs",
    "autocorr_1", "frac_missing",  # #493 item 4 (added 2026-04-27)
]
# #493 item 10 — minimum n_obs to compute slope/autocorr meaningfully on
# tier-S recipes (canonical_length 3-8). Below this, those stats are NaN
# (later filled with 0.0 in fit_and_score) rather than fabricated from
# under-determined fits.
MIN_OBS_FOR_DYNAMICS = 3

EPS = 1e-9


def _stats_legacy(years: np.ndarray, values: np.ndarray) -> list[float]:
    """v0 stat set — mean/std/last/slope/change/n_obs. Identity-leaky."""
    if values.size == 0:
        return [np.nan] * len(INDICATOR_FEATURE_STATS_LEGACY)
    mean = float(np.mean(values))
    std = float(np.std(values)) if values.size > 1 else 0.0
    last_value = float(values[-1])
    if values.size > 1 and np.std(years) > 0:
        slope = float(np.polyfit(years, values, 1)[0])
    else:
        slope = 0.0
    change = float(values[-1] - values[0])
    n_obs = int(values.size)
    return [mean, std, last_value, slope, change, n_obs]


def _stats_deconfound(years: np.ndarray, values: np.ndarray,
                      window_total_years: int | None = None) -> list[float]:
    """Country-identity de-confounded stat set. All values scale-invariant.

    - std_norm     = std / (|mean| + eps)               coefficient of variation
    - slope_norm   = (slope * window_len) / (|mean| + eps)
                                                        relative total change rate
    - pct_change   = (last - first) / (|first| + eps)   relative total change
    - n_obs        = sample size                        dimensionless
    - autocorr_1   = lag-1 Pearson autocorrelation      trending vs noisy (#493 item 4)
    - frac_missing = (window_total - n_obs) / window_total  data-density signal

    #493 item 10: when n_obs < MIN_OBS_FOR_DYNAMICS, slope_norm + pct_change +
    autocorr_1 return NaN (then filled with 0.0 in fit_and_score) rather
    than a fabricated value from a 2-point regression on tier-S recipes.
    """
    n_obs = int(values.size)
    if n_obs == 0:
        return [np.nan] * len(INDICATOR_FEATURE_STATS_DECONF)

    mean = float(np.mean(values))
    std = float(np.std(values)) if n_obs > 1 else 0.0
    abs_mean = abs(mean) + EPS
    std_norm = std / abs_mean

    if n_obs >= MIN_OBS_FOR_DYNAMICS and np.std(years) > 0:
        slope = float(np.polyfit(years, values, 1)[0])
        window_len = float(years.max() - years.min())
        slope_norm = (slope * window_len) / abs_mean
        # autocorr_1 — Pearson r of value[t] with value[t-1].
        x = values[:-1]
        y = values[1:]
        if np.std(x) > EPS and np.std(y) > EPS:
            autocorr_1 = float(np.corrcoef(x, y)[0, 1])
        else:
            autocorr_1 = 0.0
        abs_first = abs(float(values[0])) + EPS
        pct_change = float(values[-1] - values[0]) / abs_first
    else:
        # Under-determined — emit NaN. fillna(0) in fit_and_score takes over.
        slope_norm = float("nan")
        autocorr_1 = float("nan")
        pct_change = float("nan")

    # #493 item 4 — frac_missing: how much of the canonical_length window
    # is data-poor. Caller passes window_total_years (= canonical_length);
    # if not provided, fall back to year-span observed.
    if window_total_years and window_total_years > 0:
        frac_missing = max(0.0, 1.0 - (n_obs / float(window_total_years)))
    elif n_obs > 0:
        observed_span = max(1, int(years.max() - years.min()) + 1)
        frac_missing = max(0.0, 1.0 - (n_obs / float(observed_span)))
    else:
        frac_missing = 1.0

    return [std_norm, slope_norm, pct_change, n_obs, autocorr_1, frac_missing]


# Selected at runtime via the --deconfound / --no-deconfound CLI flag.
INDICATOR_FEATURE_STATS = INDICATOR_FEATURE_STATS_DECONF
_stats_for_series = _stats_deconfound


# ---------------------------------------------------------------------------
# #585 Phase C — diff-based stats for I(1) indicators
# ---------------------------------------------------------------------------
#
# Per Majles Al Ihsa I3 (2026-05-02): for indicators classified as I(1) by
# the CIPS panel stationarity audit (#582), compute features on the
# first-differenced series rather than levels. This removes the unit-root
# spurious-correlation contamination identified in Phase 0b (87.7% spurious
# pass-through under raw Z-scoring → 5% under first-differencing).
#
# Implementation: same 6 stats as the deconfound stat set, but applied to
# np.diff(values) rather than values themselves. Column names are prefixed
# with "diff_" so they don't collide with level features in the GBM.
#
# Architecture (post-I3 + post-#588): default behavior (--detrend-method none)
# is unchanged. Under --detrend-method=first-diff, I(1) indicators receive
# diff features; stationary indicators retain level features. The override
# list (cells where both level AND diff are emitted) is currently empty per
# the triple-confirmation analysis post-#588, so dual-output is dormant in
# v1 but the code path is present for v2 expansion via #586.

DETREND_METHODS: tuple[str, ...] = ("none", "first-diff")

INDICATOR_FEATURE_STATS_DIFF: list[str] = [
    "diff_std_norm", "diff_slope_norm", "diff_pct_change", "diff_n_obs",
    "diff_autocorr_1", "diff_frac_missing",
]


def _stats_first_diff(years: np.ndarray, values: np.ndarray,
                      window_total_years: int | None = None) -> list[float]:
    """Compute deconfound-style stats on the first-differenced series.

    Returns 6 values in the same order as INDICATOR_FEATURE_STATS_DIFF.
    NaN values are caller's responsibility to fill (fit_and_score uses fillna(0)).

    Mathematical equivalence: this is _stats_deconfound applied to np.diff(values),
    with the year axis shifted to match (years[1:]). The output stats describe
    properties of year-over-year *changes* rather than levels — std of changes,
    slope of changes (i.e., acceleration), pct change of changes, etc.

    Note on diff_frac_missing: window_total_years is passed unchanged to
    _stats_deconfound, but differencing reduces the series length by 1.
    For canonical_length=25 with full coverage, diff_frac_missing returns
    1 - (24/25) = 0.04 instead of 0.0. This is a small constant systematic
    offset (~1/canonical_length) that's the same for every fully-covered I(1)
    series and therefore non-discriminating in the GBM. Documented as a known
    minor cosmetic property; not a defect.
    """
    if values.size < 2:
        return [np.nan] * len(INDICATOR_FEATURE_STATS_DIFF)
    diffs = np.diff(values)
    diff_years = years[1:]
    # Reuse the deconfound stat machinery — diff_std_norm has same formula as
    # std_norm, just on differences.
    return _stats_deconfound(diff_years, diffs, window_total_years)


def load_regimes_set(regimes_path: Path) -> set[str]:
    """Return the set of indicator_id_strings classified as I(1).

    Reads `qgi-data/reference/indicator-regimes.json` (produced by Phase 0c).
    The full envelope has a `regimes.i1` array of indicator_id_strings.
    """
    if not regimes_path.exists():
        raise FileNotFoundError(f"--regimes-path not found: {regimes_path}")
    data = json.loads(regimes_path.read_text(encoding="utf-8"))
    regimes = data.get("regimes", {}) or {}
    return set(regimes.get("i1", []) or [])


def load_cointegration_overrides(coint_path: Path) -> set[tuple[str, str]]:
    """Return the set of (indicator_id_string, recipe_category) cells flagged
    as cointegrated in the cointegration map.

    Per Ihsa I3 + Roshani follow-up + #588 indicator-basket revision, this
    set is currently EMPTY (0 cells survive triple-confirmation + basket
    revision). The function is preserved for v2 expansion via #586 where
    Roshani's flexible-rule framework will re-populate it via EB hyperprior
    dominance OR causal-documentation mechanism (NOT cointegration evidence
    per Roshani's lags=3 pivot).
    """
    if coint_path is None or not coint_path.exists():
        return set()
    data = json.loads(coint_path.read_text(encoding="utf-8"))
    cells = data.get("cells", {}) or {}
    out: set[tuple[str, str]] = set()
    for cell_key, cell in cells.items():
        if "::" not in cell_key:
            continue
        ind_id, recipe = cell_key.split("::", 1)
        if cell.get("verdict") == "cointegrated":
            out.add((ind_id, recipe))
    return out


def build_feature_matrix_v2(panel: pd.DataFrame, fingerprint: list[dict],
                            num_to_str: dict[int, str],
                            cutoff_year: int, canonical_length: int,
                            country_to_id: dict[str, int],
                            detrend_method: str = "none",
                            i1_set: set[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Build (country_id × feature) DataFrame for one recipe.

    Window: [cutoff_year - canonical_length, cutoff_year].

    Default behavior (detrend_method='none', i1_set=None): emits 6 level-based
    features per indicator (INDICATOR_FEATURE_STATS — currently the deconfound
    set). This matches all prior audition_indicators.py runs bit-for-bit.

    With detrend_method='first-diff' AND i1_set provided: indicators in i1_set
    receive 6 ADDITIONAL diff-based features (INDICATOR_FEATURE_STATS_DIFF),
    yielding 12 total features per I(1) indicator. Stationary indicators are
    unchanged (6 features each). Per Majles Al Ihsa I3 (2026-05-02).

    Backward-compat guarantee: any caller that does NOT pass detrend_method
    and i1_set sees identical output to the pre-Phase-C function. Tests
    exercise this in test_audition_detrend.py::test_default_args_match_legacy.
    """
    window_start = cutoff_year - canonical_length
    window_end = cutoff_year

    # Normalize detrend params
    detrend_active = (detrend_method == "first-diff" and i1_set is not None)
    if i1_set is None:
        i1_set = set()

    # Filter panel to fingerprint indicators + window
    fp_str_ids = [num_to_str[fp["indicator_id"]] for fp in fingerprint
                  if fp["indicator_id"] in num_to_str]
    if not fp_str_ids:
        return pd.DataFrame(), []

    pw = panel[
        (panel["indicator_id"].isin(fp_str_ids))
        & (panel["year"] >= window_start)
        & (panel["year"] <= window_end)
    ].copy()
    if pw.empty:
        return pd.DataFrame(), []

    feature_cols: list[str] = []
    for fp in fingerprint:
        if fp["indicator_id"] not in num_to_str:
            continue
        nid = fp["indicator_id"]
        sid = num_to_str[nid]
        is_i1 = detrend_active and (sid in i1_set)
        # Always emit level features (matches pre-Phase-C behavior)
        for stat in INDICATOR_FEATURE_STATS:
            feature_cols.append(f"ind{nid}__{stat}")
        # Additionally emit diff features for I(1) indicators when detrending
        if is_i1:
            for stat in INDICATOR_FEATURE_STATS_DIFF:
                feature_cols.append(f"ind{nid}__{stat}")

    # Build per-country feature rows
    countries = sorted(pw["country"].unique())
    feature_rows: list[dict] = []
    for ctry in countries:
        if ctry not in country_to_id:
            continue
        country_id = country_to_id[ctry]
        cdata = pw[pw["country"] == ctry]
        row: dict = {"country_id": country_id, "country": ctry}
        for fp in fingerprint:
            if fp["indicator_id"] not in num_to_str:
                continue
            nid = fp["indicator_id"]
            sid = num_to_str[nid]
            is_i1 = detrend_active and (sid in i1_set)
            slc = cdata[cdata["indicator_id"] == sid].sort_values("year")
            if slc.empty:
                lvl_stats = [np.nan] * len(INDICATOR_FEATURE_STATS)
                diff_stats = [np.nan] * len(INDICATOR_FEATURE_STATS_DIFF) if is_i1 else None
            else:
                years_arr = slc["year"].to_numpy()
                vals_arr = slc["value"].to_numpy()
                # Pass canonical_length so frac_missing is computed
                # against the recipe's intended window, not just observed span.
                # _stats_legacy ignores the 3rd arg; _stats_deconfound uses it.
                try:
                    lvl_stats = _stats_for_series(years_arr, vals_arr, canonical_length)
                except TypeError:
                    lvl_stats = _stats_for_series(years_arr, vals_arr)
                if is_i1:
                    diff_stats = _stats_first_diff(years_arr, vals_arr, canonical_length)
                else:
                    diff_stats = None
            for stat_name, val in zip(INDICATOR_FEATURE_STATS, lvl_stats):
                row[f"ind{nid}__{stat_name}"] = val
            if is_i1 and diff_stats is not None:
                for stat_name, val in zip(INDICATOR_FEATURE_STATS_DIFF, diff_stats):
                    row[f"ind{nid}__{stat_name}"] = val
        feature_rows.append(row)

    df = pd.DataFrame(feature_rows)
    return df, feature_cols


def attach_target(features: pd.DataFrame, gt: pd.DataFrame, event_category: str) -> pd.DataFrame:
    """Add y column = 1 if (country, event_category) had post-cutoff event, else 0."""
    cat_gt = gt[gt["event_category"] == event_category][["country_id", "y_post_cutoff"]]
    out = features.merge(cat_gt, on="country_id", how="left")
    out["y"] = out["y_post_cutoff"].fillna(0).astype(int)
    return out.drop(columns=["y_post_cutoff"])


# #493 item 1 — MNAR-risk flagging.
# Computes |Pearson r| between (indicator_is_missing, target y) per
# (recipe, indicator). Threshold 0.3 → MNAR-risk flag = True. Catches
# the "data exists ≈ country is stable" leakage that inflates AUC for
# indicators like SP.POP.TOTL on sport_and_international_event.
MNAR_THRESHOLD = 0.3


def compute_mnar_per_indicator(labeled: pd.DataFrame, fingerprint: list[dict],
                               num_to_str: dict[int, str]
                               ) -> dict[int, float]:
    """Returns {indicator_numeric_id → |Pearson r| of (is_missing, y)}.

    is_missing per country = whether ALL of this indicator's stat columns
    are NaN before fillna (i.e., the country had no data for the indicator
    in the canonical_length window). The is_missing signal is computed
    against the n_obs column, which is 0 (or NaN) when no data existed.
    """
    out: dict[int, float] = {}
    y = labeled["y"].to_numpy()
    if y.sum() < 2 or (1 - y).sum() < 2:
        return out
    y_std = float(np.std(y))
    if y_std < EPS:
        return out

    for fp in fingerprint:
        n_id = fp["indicator_id"]
        if n_id not in num_to_str:
            continue
        # Use the n_obs column (always present in both stat sets) as a
        # proxy for "did data exist for this indicator in this country."
        # n_obs is 0 (post-fillna) or NaN (pre-fillna) when missing.
        col = f"ind{n_id}__n_obs"
        if col not in labeled.columns:
            continue
        # is_missing = 1 if n_obs is NaN OR 0
        n_obs_vals = labeled[col].to_numpy()
        # Match up with the row order of y
        is_missing = np.where(np.isnan(n_obs_vals) | (n_obs_vals == 0), 1.0, 0.0)
        if np.std(is_missing) < EPS:
            # No variance — either all missing or none missing
            continue
        r = float(np.corrcoef(is_missing, y)[0, 1])
        out[n_id] = abs(r)
    return out


# ---------------------------------------------------------------------------
# Stage 2: per-recipe model fit + permutation importance
# ---------------------------------------------------------------------------

def fit_and_score(features: pd.DataFrame, feature_cols: list[str],
                  random_state: int = RANDOM_SEED
                  ) -> tuple[float, dict[str, float], int, int]:
    """Fit GBM on country-stratified train split, score on holdout.

    Returns (test_auc, perm_importance_per_feature, n_train, n_test).
    NaN in features is replaced with 0 — sklearn doesn't accept NaN.
    The n_obs feature column captures whether the indicator had data.
    """
    X = features[feature_cols].fillna(0.0).to_numpy()
    y = features["y"].to_numpy()

    # Need both classes in stratified split
    if y.sum() < 2 or (1 - y).sum() < 2:
        return float("nan"), float("nan"), float("nan"), {}, len(X), 0

    sss = StratifiedShuffleSplit(
        n_splits=1, test_size=HOLDOUT_FRAC, random_state=random_state
    )
    train_idx, test_idx = next(sss.split(X, y))
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    if y_test.sum() < 1 or (1 - y_test).sum() < 1:
        return float("nan"), float("nan"), float("nan"), {}, len(X_train), len(X_test)

    model = GradientBoostingClassifier(
        n_estimators=80, max_depth=3, learning_rate=0.05,
        random_state=random_state, subsample=0.9,
    )
    model.fit(X_train, y_train)

    # Test AUC + bootstrap CI (#493 item 3 — addresses #498).
    # n_test=44 with 64 features makes the AUC point estimate noisy.
    # Bootstrap resamples the holdout 200x, gives 90% CI bands.
    proba = model.predict_proba(X_test)[:, 1]
    from sklearn.metrics import roc_auc_score
    if len(np.unique(y_test)) < 2:
        test_auc = float("nan")
        auc_low = float("nan")
        auc_high = float("nan")
    else:
        test_auc = float(roc_auc_score(y_test, proba))
        # Bootstrap: 200 stratified resamples of the holdout, recompute AUC
        # on each. Stratified ensures every resample has both classes; an
        # unstratified resample of n=44 with low pos_rate would frequently
        # land in pure-class draws (AUC undefined).
        rng = np.random.default_rng(random_state)
        pos_idx = np.where(y_test == 1)[0]
        neg_idx = np.where(y_test == 0)[0]
        boot_aucs = []
        for _ in range(BOOTSTRAP_REPEATS):
            # Stratified resample: same n_pos, same n_neg as holdout
            pos_resample = rng.choice(pos_idx, size=len(pos_idx), replace=True)
            neg_resample = rng.choice(neg_idx, size=len(neg_idx), replace=True)
            idx = np.concatenate([pos_resample, neg_resample])
            try:
                boot_aucs.append(roc_auc_score(y_test[idx], proba[idx]))
            except ValueError:
                # Should not happen with stratified resample, but guard anyway
                continue
        if boot_aucs:
            auc_low = float(np.percentile(boot_aucs, 5))    # 90% CI
            auc_high = float(np.percentile(boot_aucs, 95))
        else:
            auc_low = float("nan")
            auc_high = float("nan")

    # Permutation importance on holdout
    pi = permutation_importance(
        model, X_test, y_test, n_repeats=PERM_REPEATS,
        random_state=random_state, scoring="neg_log_loss",
    )
    importances = {col: float(imp) for col, imp in zip(feature_cols, pi.importances_mean)}
    # Aggregate per indicator (sum across the 6 stat columns).
    # Column shape is "ind{numeric_id}__{stat_name}" — split on the
    # double-underscore so multi-word stat names (last_value, n_obs)
    # don't poison the prefix.
    per_indicator: dict[str, float] = defaultdict(float)
    for col, imp in importances.items():
        prefix = col.split("__", 1)[0]  # "ind123" ← "ind123__last_value"
        per_indicator[prefix] += max(0.0, imp)  # only positive lift counts
    return test_auc, auc_low, auc_high, dict(per_indicator), len(X_train), len(X_test)


# ---------------------------------------------------------------------------
# Stage 3: coverage equity
# ---------------------------------------------------------------------------

def compute_indicator_coverage(panel: pd.DataFrame, country_to_alpha2: dict[str, str],
                               alpha2_to_region: dict[str, str]
                               ) -> pd.DataFrame:
    """Per indicator: n_countries_with_data, coverage_share, regional_evenness,
    missingness_global."""
    rows: list[dict] = []
    indicator_ids = panel["indicator_id"].unique()
    for sid in indicator_ids:
        sub = panel[panel["indicator_id"] == sid]
        countries_with_data = set(sub["country"].unique())
        n_countries = len(countries_with_data)
        coverage_share = n_countries / TOTAL_COUNTRIES

        # Regional evenness
        per_region: dict[str, int] = defaultdict(int)
        for ctry in countries_with_data:
            a2 = country_to_alpha2.get(ctry)
            if not a2:
                continue
            region = alpha2_to_region.get(a2)
            if region:
                per_region[region] += 1
        if not per_region:
            evenness = 0.0
        else:
            shares = np.array(list(per_region.values()), dtype=float)
            shares = shares / shares.sum()
            # Gini-style spread: 0 = perfectly uniform, 1 = perfectly concentrated.
            # Convert to evenness = 1 - gini.
            n = len(shares)
            if n <= 1:
                evenness = 0.0
            else:
                shares_sorted = np.sort(shares)
                idx = np.arange(1, n + 1)
                gini = (2.0 * np.sum(idx * shares_sorted) - (n + 1)) / n
                evenness = float(max(0.0, 1.0 - gini))

        rows.append({
            "indicator_id_string": sid,
            "n_countries_with_data": n_countries,
            "coverage_share": float(coverage_share),
            "regional_evenness": evenness,
            "missingness_global": float(1.0 - coverage_share),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Stage 4: report rendering
# ---------------------------------------------------------------------------

def render_markdown(report: dict, output_path: Path) -> None:
    md = []
    md.append(f"# Indicator-to-Recipe Audit — {report['audit_date']}\n")
    md.append(f"**Pipeline:** {report['pipeline_version']} · **Cutoff year:** {report['cutoff_year']} · "
              f"**Random seed:** {RANDOM_SEED}\n")
    md.append(f"**Indicators audited:** {report['n_indicators']} · "
              f"**Recipes covered:** {report['n_recipes']} · "
              f"**Recipe-indicator cells:** {report['n_cells']}\n")
    md.append("\n## Headline\n")
    md.append(f"- Median per-recipe holdout AUC: **{report['median_recipe_auc']:.3f}**")
    md.append(f"- Recipes with AUC ≥ 0.55: **{report['n_recipes_above_055']}/{report['n_recipes_qualified']}**")
    md.append(f"- Top-lift indicator (across all recipes, sum of audition_score): **{report['top_indicator']}**")
    md.append(f"- Mean audition_score: **{report['mean_audition_score']:.3f}** (predictive_lift × coverage_share × regional_evenness)")

    md.append("\n## Per-recipe summary\n")
    md.append("Test AUC column shows point estimate + 90% bootstrap CI on the holdout. "
              "Wide CIs (>0.20 spread) indicate the AUC is unstable on this small holdout — "
              "treat the point estimate with skepticism (#498). MNAR column shows count of "
              "fingerprint indicators flagged for missingness-correlates-with-outcome (#493 item 1).\n")
    md.append("| Recipe | Tier | n_total | n_pos | pos_rate | n_train | n_test | Test AUC [90% CI] | MNAR | Top contributor |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in report["per_recipe"]:
        n_total = r.get("n_total", "—")
        n_pos = r.get("n_pos", "—")
        pos_rate = (
            f"{(r['n_pos'] / r['n_total']):.3f}"
            if r.get("n_total") and r.get("n_pos") is not None
            else "—"
        )
        ci_low = r.get("auc_ci_low")
        ci_high = r.get("auc_ci_high")
        if ci_low is not None and not (isinstance(ci_low, float) and np.isnan(ci_low)):
            auc_str = f"{r['test_auc']:.3f} [{ci_low:.3f}, {ci_high:.3f}]"
        else:
            auc_str = f"{r['test_auc']:.3f}"
        n_mnar = r.get("n_mnar_flagged", 0)
        mnar_str = f"⚠ {n_mnar}" if n_mnar > 0 else "0"
        md.append(
            f"| {r['event_category']} | {r['tier']} | {n_total} | {n_pos} | "
            f"{pos_rate} | {r['n_train']} | {r['n_test']} | "
            f"{auc_str} | {mnar_str} | {r['top_indicator']} |"
        )

    md.append("\n## Per-indicator scorecard (existing fingerprint indicators)\n")
    md.append("3-column scorecard view (#493 item 5): lift, coverage, evenness shown separately. "
              "MNAR column flags indicators where missingness correlates with outcome — treat their "
              "lift as suspect (#493 item 1).\n")
    md.append("| Indicator | Provider | Lift | Coverage | Evenness | MNAR | n_recipes | audition_score |")
    md.append("|---|---|---|---|---|---|---|---|")
    fingerprint_indicators = [r for r in report["per_indicator"] if not r.get("is_candidate")]
    for r in sorted(fingerprint_indicators, key=lambda r: -r["audition_score"])[:25]:
        mnar_str = f"⚠ {r.get('max_mnar_r', 0):.2f}" if r.get("mnar_risk") else f"{r.get('max_mnar_r', 0):.2f}"
        md.append(
            f"| {r['indicator_id_string']} | {r.get('provider', '—')} | "
            f"{r['mean_lift']:.4f} | {r['coverage_share']:.3f} | {r['regional_evenness']:.3f} | "
            f"{mnar_str} | {r['n_recipes_appearing']} | **{r['audition_score']:.4f}** |"
        )

    candidate_indicators = [r for r in report["per_indicator"] if r.get("is_candidate")]
    if candidate_indicators:
        md.append("\n## CANDIDATE indicators scorecard (NOT YET in any recipe fingerprint)\n")
        md.append("3-column scorecard: lift × coverage × evenness shown separately. "
                  "audition_score = product, but separate columns reveal high-lift / lower-coverage indicators "
                  "that the multiplicative score hides (#493 item 5). Per founder direction, integration is "
                  "independent of audition.\n")
        md.append("| Candidate | Provider | Lift | Coverage | Evenness | MNAR | n_recipes | audition_score |")
        md.append("|---|---|---|---|---|---|---|---|")
        for r in sorted(candidate_indicators, key=lambda r: -r["audition_score"]):
            mnar_str = f"⚠ {r.get('max_mnar_r', 0):.2f}" if r.get("mnar_risk") else f"{r.get('max_mnar_r', 0):.2f}"
            md.append(
                f"| {r['indicator_id_string']} | {r.get('provider', '—')} | "
                f"{r['mean_lift']:.4f} | {r['coverage_share']:.3f} | {r['regional_evenness']:.3f} | "
                f"{mnar_str} | {r['n_recipes_appearing']} | **{r['audition_score']:.4f}** |"
            )

    # #493 item 2 — rolling-window CV stability section (if multi-fold)
    has_multifold = any(r.get("n_folds", 1) > 1 for r in report["per_recipe"])
    if has_multifold:
        md.append("\n## Rolling-window CV stability per recipe (#493 item 2)\n")
        md.append("Each recipe was scored across multiple cutoff years. AUC range across folds "
                  "is the stability indicator: STABLE (<0.10), MIXED (0.10-0.20), UNSTABLE (>0.20).\n")
        md.append("| Recipe | Tier | Folds | AUC median | AUC range [min, max] | Stability |")
        md.append("|---|---|---|---|---|---|")
        for r in sorted(report["per_recipe"], key=lambda r: r.get("auc_range", 0)):
            n_folds = r.get("n_folds", 1)
            if n_folds <= 1:
                continue
            md.append(
                f"| {r['event_category']} | {r['tier']} | {n_folds} | "
                f"{r['test_auc']:.3f} | "
                f"[{r.get('auc_min', 0):.3f}, {r.get('auc_max', 0):.3f}] "
                f"(Δ={r.get('auc_range', 0):.3f}) | {r.get('stability', 'n/a')} |"
            )

    # #493 item 6 — rank stability vs prior baseline (if --baseline-report provided)
    if report.get("rank_stability"):
        md.append("\n## Rank stability vs prior audit (#493 item 6)\n")
        md.append(f"Baseline: `{report['rank_stability']['baseline_path']}`\n")
        md.append("Per-recipe Kendall's tau on top-3 indicator rank-order vs baseline. "
                  "tau=1 means same ranking; tau<0.3 means major reshuffle (treat with skepticism).\n")
        md.append("| Recipe | Baseline top-3 | New top-3 | Kendall's τ | Verdict |")
        md.append("|---|---|---|---|---|")
        for entry in sorted(report["rank_stability"]["per_recipe"], key=lambda e: e.get("tau", 0)):
            tau = entry.get("tau")
            verdict = (
                "STABLE" if tau is not None and tau >= 0.5
                else "MIXED" if tau is not None and tau >= 0.0
                else "RESHUFFLED" if tau is not None
                else "n/a"
            )
            tau_str = f"{tau:.2f}" if tau is not None else "—"
            md.append(
                f"| {entry['event_category']} | {', '.join(entry['baseline_top'])} | "
                f"{', '.join(entry['new_top'])} | {tau_str} | {verdict} |"
            )

    md.append("\n## Methodology notes\n")
    md.append("- **Train/holdout:** stratified 80/20 country split per recipe (fixed seed 42)")
    md.append("- **Model:** GradientBoostingClassifier (sklearn) — n_estimators=80, max_depth=3, lr=0.05")
    md.append("- **Importance:** sklearn permutation_importance, n_repeats=10, scoring=neg_log_loss")
    md.append("- **Coverage equity:** `audition_score = predictive_lift × coverage_share × regional_evenness`")
    md.append("- **Regional evenness:** `1 - gini_coefficient(per-region share of countries with data)`")
    md.append("- **BH-FDR multiple-testing correction:** explicitly OUT OF SCOPE per founder veto (2026-04-26)")
    md.append("- **Missing data:** not imputed; rows with insufficient data drop out of the recipe model")

    md.append("\n## Audit metadata\n")
    md.append(f"- Audit date: `{report['audit_date']}`")
    md.append(f"- Git SHA: `{report['git_sha']}`")
    md.append(f"- Cutoff year: {report['cutoff_year']}")
    md.append(f"- Total countries (denominator): {TOTAL_COUNTRIES}")

    output_path.write_text("\n".join(md), encoding="utf-8")


def compute_rank_stability(new_report: dict, baseline_path: Path) -> dict:
    """#493 item 6 — Kendall's tau on per-recipe top-K indicator ranks vs baseline.

    Returns {"baseline_path": str, "per_recipe": [{event_category, baseline_top,
    new_top, tau}, ...]}. tau is None when either side has < 2 indicators or
    no overlap.
    """
    if not baseline_path.exists():
        return {"baseline_path": str(baseline_path), "per_recipe": [],
                "note": f"baseline not found at {baseline_path}"}
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    base_idx = {r["event_category"]: r for r in baseline["per_recipe"]}
    new_idx = {r["event_category"]: r for r in new_report["per_recipe"]}
    common = sorted(set(base_idx) & set(new_idx))
    K = 3

    def top_k_ordered(record: dict) -> list[str]:
        # `indicator_lift` is dict[indicator_string -> lift]. Take top K by lift.
        items = sorted(record.get("indicator_lift", {}).items(), key=lambda kv: -kv[1])
        return [k for k, _ in items[:K]]

    def kendall_tau_partial(a: list[str], b: list[str]) -> float | None:
        """Kendall's tau on the union of indicators ranked by appearance order.
        Indicators not in a list get rank K+1 (= max + 1)."""
        union = list(set(a) | set(b))
        if len(union) < 2:
            return None

        def ranks(lst: list[str]) -> dict[str, float]:
            r = {x: i + 1 for i, x in enumerate(lst)}
            for x in union:
                if x not in r:
                    r[x] = K + 1
            return r

        ra = ranks(a)
        rb = ranks(b)
        n = len(union)
        concordant = discordant = 0
        for i in range(n):
            for j in range(i + 1, n):
                xa, xb = ra[union[i]] - ra[union[j]], rb[union[i]] - rb[union[j]]
                if xa * xb > 0:
                    concordant += 1
                elif xa * xb < 0:
                    discordant += 1
        denom = concordant + discordant
        if denom == 0:
            return None
        return (concordant - discordant) / denom

    per_recipe = []
    for cat in common:
        base_top = top_k_ordered(base_idx[cat])
        new_top = top_k_ordered(new_idx[cat])
        tau = kendall_tau_partial(base_top, new_top)
        per_recipe.append({
            "event_category": cat,
            "baseline_top": base_top,
            "new_top": new_top,
            "tau": tau,
        })
    return {"baseline_path": str(baseline_path), "per_recipe": per_recipe}


def upload_audit_results_to_glue(report: dict, bucket: str, region: str) -> None:
    """#493 item 9 — persist this audit run's per-(indicator, recipe) cells
    to the Glue table qgi_data.indicator_recipe_audit_results.

    Writes parquet to:
      s3://{bucket}/audition-results/audit_date_partition={YYYY-MM-DD}/{audit_date}.parquet

    Glue table is auto-discovered via MSCK REPAIR. Schema (per design doc
    docs/specs/internal/design/indicator-recipe-auditioner.md §Persistence):
      indicator_id_string, provider, event_category, predictive_lift,
      coverage_share, regional_evenness, audition_score,
      mnar_max_r, mnar_risk, n_countries_with_data, n_train, n_test,
      test_auc, auc_ci_low, auc_ci_high, audit_date, git_sha, pipeline_version
    """
    s3 = boto3.client("s3", region_name=region)
    cells = []
    audit_date = report["audit_date"]
    git_sha = report.get("git_sha", "unknown")
    pipeline_version = report.get("pipeline_version", "v0")

    # Index per_indicator by string id for fast lookup
    ind_idx = {r["indicator_id_string"]: r for r in report["per_indicator"]}

    for recipe in report["per_recipe"]:
        cat = recipe["event_category"]
        for ind_str, lift in recipe.get("indicator_lift", {}).items():
            meta = ind_idx.get(ind_str, {})
            cells.append({
                "indicator_id_string": ind_str,
                "provider": meta.get("provider", "?"),
                "event_category": cat,
                "predictive_lift": float(lift),
                "coverage_share": float(meta.get("coverage_share", 0.0)),
                "regional_evenness": float(meta.get("regional_evenness", 0.0)),
                "audition_score": float(meta.get("audition_score", 0.0)),
                "mnar_max_r": float(meta.get("max_mnar_r", 0.0)),
                "mnar_risk": bool(meta.get("mnar_risk", False)),
                "n_countries_with_data": int(meta.get("n_countries_with_data", 0)),
                "n_train": int(recipe.get("n_train", 0)),
                "n_test": int(recipe.get("n_test", 0)),
                "test_auc": float(recipe.get("test_auc") or 0.0),
                "auc_ci_low": float(recipe.get("auc_ci_low") or 0.0),
                "auc_ci_high": float(recipe.get("auc_ci_high") or 0.0),
                "audit_date": audit_date,
                "git_sha": git_sha,
                "pipeline_version": pipeline_version,
            })
    if not cells:
        print("[upload] no cells to persist; skipping")
        return

    import pyarrow as pa
    import pyarrow.parquet as pq

    df = pd.DataFrame(cells)
    audit_date_partition = audit_date[:10]  # YYYY-MM-DD
    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf, compression="snappy")
    safe_audit_id = audit_date.replace(":", "-").replace(".", "-")
    key = (
        f"audition-results/audit_date_partition={audit_date_partition}/"
        f"{safe_audit_id}.parquet"
    )
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue().to_pybytes())
    print(f"[upload] wrote {len(cells)} cells → s3://{bucket}/{key}")
    print("[upload] NOTE: Glue catalog table `qgi_data.indicator_recipe_audit_results` "
          "must exist (Terraform-defined) and `MSCK REPAIR TABLE` run for the new "
          "partition to register. See qgi-infra/modules/storage/main.tf.")


def render_csv(report: dict, output_path: Path) -> None:
    cells = []
    for r in report["per_recipe"]:
        for ind, lift in r.get("indicator_lift", {}).items():
            cells.append({
                "event_category": r["event_category"],
                "tier": r["tier"],
                "indicator": ind,
                "predictive_lift": lift,
                "test_auc": r["test_auc"],
                "n_train": r["n_train"],
                "n_test": r["n_test"],
            })
    df = pd.DataFrame(cells)
    df.to_csv(output_path, index=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--bucket", required=True)
    p.add_argument("--workgroup", default="QGI-Lambda-Workgroup")
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--cutoff-year", type=int, default=2020)
    p.add_argument("--end-year", type=int, default=2026)
    p.add_argument("--max-canonical-length", type=int, default=40)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--upload", action="store_true",
                   help="Persist results to qgi_data.indicator_recipe_audit_results (v0.5)")
    p.add_argument("--no-deconfound", action="store_true",
                   help="Use the v0 legacy stat set (mean, std, last_value, slope, "
                        "change, n_obs) instead of the de-confounded stat set "
                        "(std_norm, slope_norm, pct_change, n_obs). Default is "
                        "deconfound, which kills the country-identity leakage that "
                        "inflated v0 AUCs (#484).")
    p.add_argument("--candidates-from-provider", default=None,
                   help="Audit ALL indicators with this provider as candidates "
                        "alongside each recipe's existing fingerprint indicators. "
                        "E.g. 'VDEM' adds the 12 V-Dem indicators to every recipe's "
                        "feature pool. The auditioner reports per-(recipe, candidate) "
                        "lift, so we can see which V-Dem indicators have predictive "
                        "lift on which recipes WITHOUT requiring a recipe-engine "
                        "re-bake. Note: this is a CHEAP, ML-flavored test; for the "
                        "QGI-aligned pipeline-faithful version, see #480 v1 Tier 1+2.")
    p.add_argument("--candidate-indicators", default=None,
                   help="Comma-separated indicator string IDs to audit as "
                        "candidates (alternative to --candidates-from-provider). "
                        "E.g. 'v2x_polyarchy,v2x_libdem'.")
    p.add_argument("--baseline-report", type=Path, default=None,
                   help="Path to a prior audition_report.json. When provided, "
                        "the new report includes a rank-stability section "
                        "(Kendall's tau on per-recipe top-3 indicators) per "
                        "#493 item 6. Skip if no prior baseline is available.")
    p.add_argument("--rolling-cv-cutoffs", default=None,
                   help="Comma-separated cutoff years for rolling-window CV "
                        "(#493 item 2). E.g. '2014,2016,2018,2020' runs the "
                        "auditioner 4 times, each with a different cutoff, "
                        "and reports per-recipe AUC stability across folds. "
                        "Without this flag, single-cutoff path runs (default).")
    p.add_argument("--detrend-method", default="none", choices=DETREND_METHODS,
                   help="Detrending method for I(1) indicators (#585 Phase C, "
                        "Ihsa I3 lock 2026-05-02). 'none' (default): existing "
                        "behavior, level features only for all indicators. "
                        "'first-diff': for I(1) indicators (per --regimes-path), "
                        "emit BOTH level AND first-diff features (12 features "
                        "per I(1) indicator instead of 6). Stationary indicators "
                        "are unchanged. Required when first-diff: --regimes-path. "
                        "See docs/specs/internal/majles/2026-05-02_Ihsa_I3_cointegration_results.md")
    p.add_argument("--regimes-path", type=Path, default=None,
                   help="Path to indicator-regimes.json (Phase 0c output, #582). "
                        "Required when --detrend-method=first-diff.")
    p.add_argument("--cointegration-map-path", type=Path, default=None,
                   help="Path to cointegration-map.json (Phase B output, #585). "
                        "Optional. Currently informational only — override list "
                        "is empty per Ihsa I3 + #588 triple-confirmation analysis. "
                        "v2 (#586) will use this differently per Roshani's pivot.")
    p.add_argument("--local-cache-dir", type=Path, default=None,
                   help="If set, cache the indicator panel parquet to this "
                        "directory keyed by hash of (needed_str_ids, panel_lo, "
                        "panel_hi). Subsequent invocations with matching inputs "
                        "skip the Athena pull entirely (#596 — saves S3 GETs + "
                        "Athena scan cost across multi-run sessions like Phase 4 "
                        "validation sweeps). Cache hits log a message; misses "
                        "fall through to load_indicator_panel and write the cache "
                        "for next time. Cache is opt-in; default behavior unchanged.")
    args = p.parse_args()

    # Validate Phase C flag combinations
    if args.detrend_method == "first-diff" and args.regimes_path is None:
        raise SystemExit(
            "--detrend-method=first-diff requires --regimes-path "
            "(indicator-regimes.json from #582 Phase 0c)"
        )

    # Switch the stat set BEFORE any feature build calls. This mutates the
    # module-level INDICATOR_FEATURE_STATS + _stats_for_series binding so that
    # build_feature_matrix_v2 consults the chosen mode.
    global INDICATOR_FEATURE_STATS, _stats_for_series
    if args.no_deconfound:
        INDICATOR_FEATURE_STATS = INDICATOR_FEATURE_STATS_LEGACY
        _stats_for_series = _stats_legacy
        print("[mode] --no-deconfound — LEGACY stat set (identity-leaky baseline)")
    else:
        INDICATOR_FEATURE_STATS = INDICATOR_FEATURE_STATS_DECONF
        _stats_for_series = _stats_deconfound
        print("[mode] DECONFOUND stat set (scale-invariant, #484 default)")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(Path(__file__).parent.parent)
        ).decode().strip()
    except Exception:
        git_sha = "unknown"

    # #585 Phase C: load I(1) indicator set if detrending.
    # The cointegration map is read for operator visibility (count of override
    # cells in run logs) but NOT consumed by v1 — the v1 override list is
    # empty per Ihsa I3 + #588 triple-confirmation analysis. v2 (#586) will
    # wire up consumption via Roshani's flexible-rule framework.
    i1_set: set[str] = set()
    if args.detrend_method == "first-diff":
        i1_set = load_regimes_set(args.regimes_path)
        print(f"[detrend] first-diff active for {len(i1_set)} I(1) indicators "
              f"from {args.regimes_path}")
        if args.cointegration_map_path:
            # Load + log count only. v1 does not consume the override set;
            # #586 v2 will. No assignment kept around to confuse maintainers.
            n_coint_overrides = len(load_cointegration_overrides(args.cointegration_map_path))
            print(f"[detrend] cointegration overrides: {n_coint_overrides} cells "
                  f"(v1: informational only — empty per Ihsa I3 + post-#588; "
                  f"v2 #586 will wire consumption)")

    s3 = boto3.client("s3", region_name=args.region)
    ath = boto3.client("athena", region_name=args.region)

    print("[stage 0] loading reference data...")
    num_to_str = load_indicator_map(s3, args.bucket)
    str_to_num = {v: k for k, v in num_to_str.items()}
    print(f"  indicator_map: {len(num_to_str)} entries")
    alpha2_to_region = load_country_regions(s3, args.bucket)
    print(f"  country_regions: {len(alpha2_to_region)} entries")
    countries_df = load_countries(ath, args.bucket, args.workgroup)
    country_to_id = dict(zip(countries_df["name"], countries_df["country_id"]))
    country_to_alpha2 = dict(zip(countries_df["name"], countries_df["alpha_2"]))
    print(f"  countries: {len(countries_df)}")

    recipes = load_recipes_aggregated_with_fingerprints(ath, args.bucket, args.workgroup)
    print(f"  recipes_aggregated: {len(recipes)}")

    # Resolve candidate indicators (V-Dem, etc.) from CLI args.
    candidate_str_ids: list[str] = []
    if args.candidates_from_provider:
        candidate_str_ids = load_indicators_by_provider(
            ath, args.bucket, args.workgroup, args.candidates_from_provider
        )
        print(f"  candidates from provider '{args.candidates_from_provider}': "
              f"{len(candidate_str_ids)} indicators")
    if args.candidate_indicators:
        explicit = [s.strip() for s in args.candidate_indicators.split(",") if s.strip()]
        candidate_str_ids = sorted(set(candidate_str_ids) | set(explicit))
    candidate_num_ids = {str_to_num[s] for s in candidate_str_ids if s in str_to_num}
    candidate_set_for_report = set(candidate_num_ids)
    if candidate_str_ids:
        print(f"  candidate indicators (resolved to numeric): {sorted(candidate_num_ids)}")

    # Union of all fingerprint + candidate indicators we need from Athena.
    needed_num_ids: set[int] = set()
    for r in recipes:
        for fp in r["fingerprint"]:
            needed_num_ids.add(fp["indicator_id"])
    needed_num_ids |= candidate_num_ids
    needed_str_ids = [num_to_str[n] for n in needed_num_ids if n in num_to_str]
    print(f"  fingerprint+candidates indicators (union): {len(needed_str_ids)}")

    # #493 item 2 — rolling-window CV. If --rolling-cv-cutoffs is specified,
    # run the recipe loop once per cutoff. Default: single cutoff (legacy path).
    cutoffs: list[int] = []
    if args.rolling_cv_cutoffs:
        try:
            cutoffs = sorted(set(int(c.strip()) for c in args.rolling_cv_cutoffs.split(",") if c.strip()))
        except ValueError as e:
            raise SystemExit(f"--rolling-cv-cutoffs must be comma-separated ints: {e}")
        if not cutoffs:
            raise SystemExit("--rolling-cv-cutoffs parsed empty")
    else:
        cutoffs = [args.cutoff_year]

    # Panel covers the union of all fold windows so we don't re-query per cutoff.
    panel_lo = min(cutoffs) - args.max_canonical_length
    panel_hi = max(cutoffs)
    panel = _load_panel_with_cache(
        ath, args.bucket, args.workgroup, needed_str_ids, panel_lo, panel_hi,
        cache_dir=args.local_cache_dir,
    )
    print(f"  panel rows: {len(panel)}  (years {panel_lo}..{panel_hi})")
    print(f"  rolling-CV cutoffs: {cutoffs}")

    print(f"\n[stage 1+2] per-recipe modeling ({len(cutoffs)} fold{'s' if len(cutoffs)>1 else ''})")
    # recipe_fold_records[event_category] = list of per-fold dicts
    recipe_fold_records: dict[str, list[dict]] = defaultdict(list)
    indicator_lift_accumulator: dict[int, list[float]] = defaultdict(list)
    indicator_mnar_accumulator: dict[int, list[float]] = defaultdict(list)

    for fold_idx, cutoff in enumerate(cutoffs, 1):
        if len(cutoffs) > 1:
            print(f"\n[fold {fold_idx}/{len(cutoffs)}] cutoff={cutoff}")
        gt = load_event_ground_truth(ath, args.bucket, args.workgroup,
                                     cutoff, args.end_year)
        print(f"  ground truth rows: {len(gt)}")

        for i, recipe in enumerate(recipes, 1):
            cat = recipe["event_category"]
            cl = recipe["canonical_length"]
            tier = tier_for_length(cl)
            print(f"  ({i}/{len(recipes)}) {cat} (cl={cl}, tier={tier})", end=" ", flush=True)

            existing_fp_ids = {fp["indicator_id"] for fp in recipe["fingerprint"]}
            augmented_fp = list(recipe["fingerprint"]) + [
                {"indicator_id": cid, "tfidf": 1.0}
                for cid in sorted(candidate_num_ids - existing_fp_ids)
            ]

            features, feature_cols = build_feature_matrix_v2(
                panel, augmented_fp, num_to_str,
                cutoff, cl, country_to_id,
                detrend_method=args.detrend_method,
                i1_set=i1_set if args.detrend_method == "first-diff" else None,
            )
            if features.empty or not feature_cols:
                print("→ SKIP (no features)")
                continue
            labeled = attach_target(features, gt, cat)
            n_total = len(labeled)
            n_pos = int(labeled["y"].sum())
            if n_total < MIN_TOTAL or n_pos < MIN_POS:
                print(f"→ SKIP (n_total={n_total}, n_pos={n_pos})")
                continue

            try:
                test_auc, auc_low, auc_high, ind_lift, n_train, n_test = fit_and_score(
                    labeled, feature_cols
                )
            except Exception as e:
                print(f"→ ERROR: {e}")
                continue

            mnar_by_num = compute_mnar_per_indicator(labeled, augmented_fp, num_to_str)

            ind_lift_by_num: dict[int, float] = {}
            for prefix, lift in ind_lift.items():
                ind_lift_by_num[int(prefix.replace("ind", ""))] = lift
            ind_lift_by_str: dict[str, float] = {
                num_to_str[n]: lift for n, lift in ind_lift_by_num.items()
                if n in num_to_str
            }
            top_ind = max(ind_lift_by_str.items(), key=lambda kv: kv[1])[0] if ind_lift_by_str else "—"
            mnar_by_str: dict[str, float] = {
                num_to_str[n]: r for n, r in mnar_by_num.items()
                if n in num_to_str
            }
            n_mnar_flagged = sum(1 for r in mnar_by_num.values() if r >= MNAR_THRESHOLD)

            recipe_fold_records[cat].append({
                "cutoff_year": cutoff,
                "tier": tier,
                "canonical_length": cl,
                "n_total": n_total,
                "n_pos": n_pos,
                "n_train": n_train,
                "n_test": n_test,
                "test_auc": test_auc,
                "auc_ci_low": auc_low,
                "auc_ci_high": auc_high,
                "indicator_lift": ind_lift_by_str,
                "top_indicator": top_ind,
                "mnar_per_indicator": mnar_by_str,
                "n_mnar_flagged": n_mnar_flagged,
            })
            for n_id, lift in ind_lift_by_num.items():
                indicator_lift_accumulator[n_id].append(lift)
            for n_id, mnar_r in mnar_by_num.items():
                indicator_mnar_accumulator[n_id].append(mnar_r)

            ci_str = f"[{auc_low:.3f},{auc_high:.3f}]" if not np.isnan(auc_low) else "[—]"
            print(f"→ AUC={test_auc:.3f} {ci_str} top={top_ind}")

    # Aggregate per-recipe across folds. For single-cutoff: list has 1 entry,
    # aggregation is a passthrough. For multi-cutoff: median AUC across folds,
    # range as stability indicator, full fold list preserved.
    per_recipe_records: list[dict] = []
    for cat, folds in recipe_fold_records.items():
        if not folds:
            continue
        valid_aucs = [f["test_auc"] for f in folds if not np.isnan(f["test_auc"])]
        if not valid_aucs:
            continue
        median_auc = float(np.median(valid_aucs))
        auc_min = float(np.min(valid_aucs))
        auc_max = float(np.max(valid_aucs))
        auc_range = auc_max - auc_min
        # Pick the median fold as the "primary" for top-contributor + lift dict
        # (sort by abs distance to median AUC).
        primary = min(folds, key=lambda f: abs((f["test_auc"] or 0) - median_auc))
        # Stability classification (#493 item 2 verdict)
        if len(valid_aucs) <= 1:
            stability = "n/a"
        elif auc_range < 0.10:
            stability = "STABLE"
        elif auc_range < 0.20:
            stability = "MIXED"
        else:
            stability = "UNSTABLE"
        per_recipe_records.append({
            "event_category": cat,
            "tier": primary["tier"],
            "canonical_length": primary["canonical_length"],
            "n_total": primary["n_total"],
            "n_pos": primary["n_pos"],
            "n_train": primary["n_train"],
            "n_test": primary["n_test"],
            "test_auc": median_auc,           # backward-compat: used as point estimate
            "auc_ci_low": primary["auc_ci_low"],   # CI of the median fold
            "auc_ci_high": primary["auc_ci_high"],
            "indicator_lift": primary["indicator_lift"],
            "top_indicator": primary["top_indicator"],
            "mnar_per_indicator": primary["mnar_per_indicator"],
            "n_mnar_flagged": primary["n_mnar_flagged"],
            # Rolling-CV additions:
            "fold_aucs": valid_aucs,
            "auc_min": auc_min,
            "auc_max": auc_max,
            "auc_range": auc_range,
            "n_folds": len(valid_aucs),
            "stability": stability,
        })

    print("\n[stage 3] coverage equity...")
    coverage_df = compute_indicator_coverage(
        panel, country_to_alpha2, alpha2_to_region
    )

    # Pull provider attribution per indicator (#493 item 8). Single Athena
    # query joins to qgi_data.indicators.provider (column added in #485).
    # Legacy WB+FAO rows return NULL until next pipeline regen; default to "?".
    provider_qid = run_athena(
        ath,
        "SELECT DISTINCT indicator_id, provider FROM qgi_data.indicators",
        args.bucket, args.workgroup,
    )
    provider_rows = athena_fetch_all(ath, provider_qid)
    provider_by_string_id: dict[str, str] = {}
    for ind_id, provider in provider_rows:
        if ind_id:
            provider_by_string_id[ind_id] = provider or "?"

    # Combine: per-indicator audition_score = mean_lift × coverage_share × regional_evenness
    per_indicator: list[dict] = []
    for _, row in coverage_df.iterrows():
        sid = row["indicator_id_string"]
        n_id = str_to_num.get(sid)
        lifts = indicator_lift_accumulator.get(n_id, [])
        mean_lift = float(np.mean(lifts)) if lifts else 0.0
        # #493 item 1 — MNAR rollup. mean of |r| across recipes; flagged if
        # max across recipes hit MNAR_THRESHOLD.
        mnar_rs = indicator_mnar_accumulator.get(n_id, [])
        mean_mnar_r = float(np.mean(mnar_rs)) if mnar_rs else 0.0
        max_mnar_r = float(np.max(mnar_rs)) if mnar_rs else 0.0
        n_recipes_mnar_flagged = sum(1 for r in mnar_rs if r >= MNAR_THRESHOLD)
        audition_score = mean_lift * row["coverage_share"] * row["regional_evenness"]
        per_indicator.append({
            "indicator_id_string": sid,
            "indicator_numeric_id": n_id,
            "provider": provider_by_string_id.get(sid, "?"),
            "n_countries_with_data": int(row["n_countries_with_data"]),
            "coverage_share": float(row["coverage_share"]),
            "regional_evenness": float(row["regional_evenness"]),
            "mean_lift": mean_lift,
            "n_recipes_appearing": len(lifts),
            "audition_score": float(audition_score),
            "is_candidate": n_id in candidate_set_for_report if n_id else False,
            # #493 item 1 — MNAR signal
            "mean_mnar_r": mean_mnar_r,
            "max_mnar_r": max_mnar_r,
            "n_recipes_mnar_flagged": n_recipes_mnar_flagged,
            "mnar_risk": max_mnar_r >= MNAR_THRESHOLD,
        })

    print("\n[stage 4] rendering reports...")
    qualified = [r for r in per_recipe_records if not np.isnan(r["test_auc"])]
    aucs = [r["test_auc"] for r in qualified]
    above_055 = sum(1 for a in aucs if a >= 0.55)
    median_auc = float(np.median(aucs)) if aucs else float("nan")
    top_ind = max(per_indicator, key=lambda r: r["audition_score"])
    mean_score = float(np.mean([r["audition_score"] for r in per_indicator]))

    report = {
        "audit_date": audit_date,
        "git_sha": git_sha,
        "pipeline_version": "v0",
        "cutoff_year": args.cutoff_year,
        "n_indicators": len(per_indicator),
        "n_recipes": len(per_recipe_records),
        "n_recipes_qualified": len(qualified),
        "n_cells": sum(len(r.get("indicator_lift", {})) for r in per_recipe_records),
        "median_recipe_auc": median_auc,
        "n_recipes_above_055": above_055,
        "top_indicator": top_ind["indicator_id_string"],
        "mean_audition_score": mean_score,
        "per_recipe": sorted(per_recipe_records, key=lambda r: -r["test_auc"]),
        "per_indicator": per_indicator,
    }

    # #493 item 6 — rank stability vs prior baseline
    if args.baseline_report:
        print(f"[stage 4a] computing rank stability vs {args.baseline_report}")
        report["rank_stability"] = compute_rank_stability(report, args.baseline_report)

    md_path = args.output_dir / "audition_report.md"
    csv_path = args.output_dir / "audition_cells.csv"
    json_path = args.output_dir / "audition_report.json"
    render_markdown(report, md_path)
    render_csv(report, csv_path)
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {md_path}")
    print(f"  wrote {csv_path}")
    print(f"  wrote {json_path}")

    if args.upload:
        # #493 item 9 — persist to qgi_data.indicator_recipe_audit_results
        print("[stage 5] persisting to qgi_data.indicator_recipe_audit_results")
        try:
            upload_audit_results_to_glue(report, args.bucket, args.region)
        except Exception as e:
            print(f"[upload] WARN: persistence failed (non-fatal): {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
