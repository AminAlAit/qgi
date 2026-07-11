# Indicator Registry

> Owner: Amin Al-Ait | Last updated: 2026-04-03
> Related tickets: #68 (Multi-source ingestion), #33 (Soft Power Index)

---

## Purpose

Central single source of truth for ALL indicators across ALL providers. Every pipeline step references this registry for indicator metadata. Future providers that don't have native IDs get IDs generated and registered here.

## Storage: DynamoDB

Table name: `qgi-indicator-registry`

**Why DynamoDB (not Athena):**
- Low-latency Lambda lookups by ID
- Small dataset (1K-10K rows, not millions)
- Real-time updates during ingestion
- Schema flexibility per provider

## Schema

| Field | Type | Key | Description |
|-------|------|-----|-------------|
| indicator_id | string | PK | Universal ID. WB: use their code (e.g., `NY.GDP.MKTP.CD`). Others: generate `{provider}_{sequential}` (e.g., `oecd_0042`) |
| provider | string | GSI-PK | Provider name: `world_bank`, `oecd`, `un`, `imf`, `soft_power_index` |
| provider_native_id | string | | Original provider's ID (nullable for providers without IDs) |
| name | string | | Human-readable name (e.g., "GDP (current US$)") |
| description | string | | What this indicator measures |
| unit | string | | Measurement unit: `%`, `USD`, `per_capita`, `index`, etc. |
| frequency | string | | Data frequency: `annual`, `quarterly`, `monthly` |
| sector | string | | Sector/topic: `economic`, `health`, `education`, `environment`, `military`, `trade`, etc. |
| s3_data_path | string | | S3 URI pointing to raw data: `s3://qgi-data-lake-{account}/indicators/{indicator_id}/` |
| first_year | int | | Earliest data available |
| last_year | int | | Latest data available |
| country_coverage | int | | Number of countries with data for this indicator |
| license | string | | Data license: `cc-by-4.0`, `custom`, `unknown` |
| commercial_use | boolean | | Whether commercial use is permitted |
| attribution | string | | Required attribution text |
| registered_at | string | | ISO timestamp: when this indicator was first added |
| last_updated | string | | ISO timestamp: when data was last refreshed |

## Global Secondary Indexes

1. **provider-index**: PK = `provider`, SK = `indicator_id` — query all indicators from a provider
2. **sector-index**: PK = `sector`, SK = `indicator_id` — query all indicators in a sector

## ID Generation Rules

1. **World Bank**: use WB's indicator code as-is (e.g., `NY.GDP.MKTP.CD`)
2. **OECD**: use OECD's code if available, else generate `oecd_{sequential}`
3. **UN**: use UN's code if available, else generate `un_{sequential}`
4. **Custom/unknown providers**: generate `{provider_short}_{sequential}` with a counter stored in DynamoDB

## Licensing Verification (per #33)

Before onboarding a new provider:
1. Verify commercial use permission
2. Document attribution requirements
3. Check redistribution rights (raw data vs. derivatives only)
4. Record in `license`, `commercial_use`, `attribution` fields

**Current status:**
- World Bank: CC-BY 4.0, commercial use confirmed
- Soft Power Index: UNCLEAR — requires investigation before integration
