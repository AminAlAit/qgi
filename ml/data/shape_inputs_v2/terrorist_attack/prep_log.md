# Shape Input Panel — Prep Log

**Recipe:** `terrorist_attack`  
**Canonical length T_r:** 5  
**Prepared:** 2026-05-22T18:21:09.380753+00:00  
**Commit:** `d7529d9219aff97176ea49d51d22d047aaae5004`  

## Instance counts

| Stage | Count |
|-------|-------|
| n_pos_input (curated events, training window 1789-2021) | 257 |
| Country not in local panel | -1 |
| BASELINE_TOO_SHORT (§3.2.2) | -10 |
| After baseline filter | 246 |
| Alignment dropouts | -0 |
| **Final instances in parquet** | **246** |

## Indicator coverage

**5/5** (100%) key indicators available in local panel snapshot.

**Available:** ['v2csreprss', 'v2pepwrgen', 'v2x_clpol', 'v2x_libdem', 'v2x_polyarchy']

**Missing (BLOCKED — not in local 37-indicator snapshot):**
[]

> **Honesty disclosure:** G3/G4 substrate verdicts are BLOCKED-on-substrate-availability. Re-run on full 104-indicator production panel required (substrate-audit-phase-1.json P0 actions).

## Dropout sample (first 10)

| country_id | event_year | reason |
|------------|-----------|--------|
| armenia | 1972 | BASELINE_TOO_SHORT:v2csreprss (country not in panel) |
| armenia | 1983 | BASELINE_TOO_SHORT:v2csreprss (country not in panel) |
| belarus | 2010 | BASELINE_TOO_SHORT:v2csreprss (n_obs=15<20, baseline=[1985,2004]) |
| germany | 1972 | BASELINE_TOO_SHORT:v2csreprss (n_obs=18<20, baseline=[1947,1966]) |
| israel | 1972 | BASELINE_TOO_SHORT:v2csreprss (n_obs=19<20, baseline=[1947,1966]) |
| kyrgyzstan | 1999 | BASELINE_TOO_SHORT:v2csreprss (n_obs=4<20, baseline=[1974,1993]) |
| nigeria | 1980 | BASELINE_TOO_SHORT:v2x_libdem (n_obs=19<20, baseline=[1955,1974]) |
| nigeria | 1981 | BASELINE_TOO_SHORT:v2x_libdem (n_obs=19<20, baseline=[1956,1975]) |
| uzbekistan | 1999 | BASELINE_TOO_SHORT:v2csreprss (n_obs=4<20, baseline=[1974,1993]) |
| uzbekistan | 2004 | BASELINE_TOO_SHORT:v2csreprss (n_obs=9<20, baseline=[1979,1998]) |

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
    --recipe terrorist_attack \
    --indicator-panel data\shape_inputs_v2\terrorist_attack\indicator_panel.parquet \
    --positive-instances data\shape_inputs_v2\terrorist_attack\positives.csv \
    --indicator-ids v2csreprss,v2pepwrgen,v2x_clpol,v2x_libdem,v2x_polyarchy \
    --T-r 5
```