# Shape Input Panel — Prep Log

**Recipe:** `elections_and_voting`  
**Canonical length T_r:** 5  
**Prepared:** 2026-05-23T14:46:30.871433+00:00  
**Commit:** `a090a927aa735b5bc25512d6f9be0616438ce4ca`  

## Instance counts

| Stage | Count |
|-------|-------|
| n_pos_input (curated events, training window 1789-2021) | 1142 |
| Country not in local panel | -132 |
| BASELINE_TOO_SHORT (§3.2.2) | -93 |
| After baseline filter | 917 |
| Alignment dropouts | -0 |
| **Final instances in parquet** | **917** |

## Indicator coverage

**2/2** (100%) key indicators available in local panel snapshot.

**Available:** ['v2x_polyarchy', 'v2xel_frefair']

**Missing (BLOCKED — not in local 37-indicator snapshot):**
[]

> **Honesty disclosure:** G3/G4 substrate verdicts are BLOCKED-on-substrate-availability. Re-run on full 104-indicator production panel required (substrate-audit-phase-1.json P0 actions).

## Dropout sample (first 10)

| country_id | event_year | reason |
|------------|-----------|--------|
| andorra | 1933 | COUNTRY_NOT_IN_PANEL |
| andorra | 1970 | COUNTRY_NOT_IN_PANEL |
| andorra | 1994 | COUNTRY_NOT_IN_PANEL |
| antigua_and_barbuda | 1984 | COUNTRY_NOT_IN_PANEL |
| antigua_and_barbuda | 1989 | COUNTRY_NOT_IN_PANEL |
| antigua_and_barbuda | 1999 | COUNTRY_NOT_IN_PANEL |
| antigua_and_barbuda | 2004 | COUNTRY_NOT_IN_PANEL |
| antigua_and_barbuda | 2009 | COUNTRY_NOT_IN_PANEL |
| antigua_and_barbuda | 2014 | COUNTRY_NOT_IN_PANEL |
| antigua_and_barbuda | 2018 | COUNTRY_NOT_IN_PANEL |

## Output files

| File | Description |
|------|-------------|
| `positives_aligned.parquet` | Long-format aligned+normalized trajectories |
| `positives.csv` | Positives CSV for fitter `--positive-instances` |
| `indicator_panel.parquet` | Indicator panel for fitter `--indicator-panel` |
| `prep_manifest.json` | Full provenance manifest |

## Fitter invocation (Chunk C.2)

```bash
python scripts/fit_shape_prototype.py \
    --recipe elections_and_voting \
    --indicator-panel data\shape_inputs_v2\elections_and_voting\indicator_panel.parquet \
    --positive-instances data\shape_inputs_v2\elections_and_voting\positives.csv \
    --indicator-ids v2x_polyarchy,v2xel_frefair \
    --T-r 5
```