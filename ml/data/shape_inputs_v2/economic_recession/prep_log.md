# Shape Input Panel — Prep Log

**Recipe:** `economic_recession`  
**Canonical length T_r:** 5  
**Prepared:** 2026-05-17T21:51:22.106742+00:00  
**Commit:** `94af5a290b776099458d1e419f5c4d56ff604aae`  

## Instance counts

| Stage | Count |
|-------|-------|
| n_pos_input (curated events, training window 1789-2021) | 273 |
| Country not in local panel | -0 |
| BASELINE_TOO_SHORT (§3.2.2) | -171 |
| After baseline filter | 102 |
| Alignment dropouts | -0 |
| **Final instances in parquet** | **102** |

## Indicator coverage

**5/5** (100%) key indicators available in local panel snapshot.

**Available:** ['NE.CON.GOVT.ZS', 'NE.CON.PRVT.ZS', 'NE.GDI.TOTL.ZS', 'NY.GDP.MKTP.KD', 'v2xel_frefair']

**Missing (BLOCKED — not in local 37-indicator snapshot):**
[]

> **Honesty disclosure:** G3/G4 substrate verdicts are BLOCKED-on-substrate-availability. Re-run on full 104-indicator production panel required (substrate-audit-phase-1.json P0 actions).

## Dropout sample (first 10)

| country_id | event_year | reason |
|------------|-----------|--------|
| afghanistan | 1961 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (country not in panel) |
| afghanistan | 1962 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (country not in panel) |
| andorra | 2020 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (country not in panel) |
| angola | 2014 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (n_obs=7<20, baseline=[1989,2008]) |
| angola | 2016 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (n_obs=9<20, baseline=[1991,2010]) |
| antigua_and_barbuda | 2009 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (country not in panel) |
| argentina | 1952 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (country not in panel) |
| argentina | 1975 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (n_obs=10<20, baseline=[1950,1969]) |
| argentina | 2001 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (n_obs=13<20, baseline=[1976,1995]) |
| armenia | 2008 | BASELINE_TOO_SHORT:NE.CON.GOVT.ZS (n_obs=13<20, baseline=[1983,2002]) |

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
    --recipe economic_recession \
    --indicator-panel data\shape_inputs_v2\economic_recession\indicator_panel.parquet \
    --positive-instances data\shape_inputs_v2\economic_recession\positives.csv \
    --indicator-ids NE.CON.GOVT.ZS,NE.CON.PRVT.ZS,NE.GDI.TOTL.ZS,NY.GDP.MKTP.KD,v2xel_frefair \
    --T-r 5
```