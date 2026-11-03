# Shape Input Panel — Prep Log

**Recipe:** `foreign_intervention`  
**Canonical length T_r:** 5  
**Prepared:** 2026-05-17T21:51:23.301154+00:00  
**Commit:** `94af5a290b776099458d1e419f5c4d56ff604aae`  

## Instance counts

| Stage | Count |
|-------|-------|
| n_pos_input (curated events, training window 1789-2021) | 202 |
| Country not in local panel | -3 |
| BASELINE_TOO_SHORT (§3.2.2) | -89 |
| After baseline filter | 110 |
| Alignment dropouts | -0 |
| **Final instances in parquet** | **110** |

## Indicator coverage

**5/5** (100%) key indicators available in local panel snapshot.

**Available:** ['SM.POP.NETM', 'SP.DYN.LE00.IN', 'SP.DYN.TFRT.IN', 'v2x_clpol', 'v2x_clpriv']

**Missing (BLOCKED — not in local 37-indicator snapshot):**
[]

> **Honesty disclosure:** G3/G4 substrate verdicts are BLOCKED-on-substrate-availability. Re-run on full 104-indicator production panel required (substrate-audit-phase-1.json P0 actions).

## Dropout sample (first 10)

| country_id | event_year | reason |
|------------|-----------|--------|
| afghanistan | 1973 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=8<20, baseline=[1948,1967]) |
| afghanistan | 1979 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=14<20, baseline=[1954,1973]) |
| algeria | 1976 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=11<20, baseline=[1951,1970]) |
| angola | 1975 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=10<20, baseline=[1950,1969]) |
| angola | 1978 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=13<20, baseline=[1953,1972]) |
| angola | 1981 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=16<20, baseline=[1956,1975]) |
| barbados | 1983 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=18<20, baseline=[1958,1977]) |
| belize | 1993 | BASELINE_TOO_SHORT:v2x_clpol (country not in panel) |
| bolivia | 1967 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=2<20, baseline=[1942,1961]) |
| bosnia_and_herzegovina | 1992 | BASELINE_TOO_SHORT:v2x_clpol (country not in panel) |

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
    --recipe foreign_intervention \
    --indicator-panel data\shape_inputs_v2\foreign_intervention\indicator_panel.parquet \
    --positive-instances data\shape_inputs_v2\foreign_intervention\positives.csv \
    --indicator-ids SM.POP.NETM,SP.DYN.LE00.IN,SP.DYN.TFRT.IN,v2x_clpol,v2x_clpriv \
    --T-r 5
```