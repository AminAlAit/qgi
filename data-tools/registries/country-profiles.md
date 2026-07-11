# Country Profiles

> Owner: Amin Al-Ait | Last updated: 2026-04-03
> Related tickets: #70 (Knowledge extraction parent), #101 (Frontend views)

---

## Purpose

Country Profiles are **derived aggregates** computed from recipes, early warnings, events, and patterns. They are NOT a pipeline phase — they are a materialized view recomputed periodically (after each pipeline run).

They power radar/spider charts, country comparisons, and risk dashboards.

## Storage

S3 Parquet, registered as Glue table `qgi_data.country_profiles`.

## Schema

| Field | Type | Description |
|-------|------|-------------|
| country_id | string | FK to country registry |
| country_name | string | Display name |
| active_warnings_count | int | How many early warnings are active |
| dominant_risk_category | string | Highest-confidence event category |
| risk_score | float | Composite 0-100 score (QGI-exclusive) |
| risk_score_trend | string | `rising`, `stable`, `falling` |
| pattern_diversity | int | How many distinct indicators are in active patterns |
| recipe_coverage | float | What % of known recipes this country has active matches for |
| historical_accuracy | float | Backtesting accuracy for this country (from #80) |
| peer_countries | list[string] | Countries currently on most similar trajectories |
| event_category_scores | map | `{category: confidence}` — per-category signal strength |
| top_analogues | list[map] | `[{country, year, similarity}]` — historical analogues |
| computed_at | string | ISO timestamp |

## Risk Score Computation

```
risk_score = normalize_to_100(
    active_warnings_count * w1 +
    max(event_category_scores.values()) * w2 +
    pattern_diversity * w3 +
    recipe_coverage * w4 +
    trend_acceleration * w5
)
```

Weights (w1-w5) are tuned via backtesting — maximize correlation between risk_score and actual event occurrence.

**This is a QGI-exclusive derived indicator** — proprietary, not sourced from any provider.

## Country Comparison (Nearest-Neighbor)

"Show me countries with similar profiles to Egypt right now" = nearest-neighbor search in the feature space defined by `event_category_scores` vector.

Distance metric: cosine similarity on the vector `[cat1_score, cat2_score, ..., catN_score]`.

## Computation Trigger

Recomputed after:
1. Each pipeline run (new patterns → new warnings → new profiles)
2. Each events dataset update
3. On-demand for specific countries
