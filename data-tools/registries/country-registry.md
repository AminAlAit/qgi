# Country Registry

> Owner: Amin Al-Ait | Last updated: 2026-04-03
> Related tickets: #70 (Knowledge extraction parent)

---

## Purpose

Central single source of truth for ALL countries. Solves the perpetual name-matching problem (legacy has "Turkiye" vs "Türkiye" vs "Turkey", "USA" vs "United States"). Every pipeline step resolves country names through this registry.

Replaces the primitive `countries.csv` from legacy.

## Storage: DynamoDB

Table name: `qgi-country-registry`

**Why DynamoDB:**
- Same reasoning as indicator registry
- Low-latency Lambda lookups
- Small dataset (~260 rows)
- Real-time updates

## Schema

| Field | Type | Key | Description |
|-------|------|-----|-------------|
| country_id | string | PK | ISO 3166-1 alpha-3 code (e.g., `USA`, `GBR`, `EGY`) |
| name | string | | Canonical display name ("United States") |
| alt_names | list[string] | | All known aliases: `["USA", "US", "America", "United States of America"]` |
| iso_alpha2 | string | | ISO 3166-1 alpha-2: `US`, `GB`, `EG` |
| iso_numeric | string | | ISO 3166-1 numeric: `840`, `826`, `818` |
| region | string | GSI-PK | Geographic region: `Middle East`, `Sub-Saharan Africa`, `Western Europe`, etc. |
| sub_region | string | | Sub-region: `North Africa`, `Gulf States`, `Nordics`, etc. |
| indicator_coverage | map | | `{provider: count}` — how many indicators per source |
| events_count | int | | Total events in our dataset for this country |
| scdi_count | int | | Total SCDIs involving this country |
| pattern_count | int | | Total patterns involving this country |
| profile_last_updated | string | | ISO timestamp: when country profile was last computed |

## Global Secondary Indexes

1. **region-index**: PK = `region`, SK = `country_id` — query all countries in a region

## Name Resolution

Every pipeline step that encounters a country name should:
1. Check exact match against `name`
2. Check against `alt_names` list
3. If no match, flag for human review

This eliminates the scattered `Turkiye`/`Türkiye`/`Turkey` problems that plague current data.

## Country Profiles (derived, not stored here)

Country Profiles are computed aggregates stored separately (in S3 Parquet / Glue table `qgi_data.country_profiles`). They reference this registry via `country_id`. See `country-profiles.md`.
