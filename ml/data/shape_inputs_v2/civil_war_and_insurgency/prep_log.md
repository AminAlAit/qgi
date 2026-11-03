# Shape Input Panel — Prep Log

**Recipe:** `civil_war_and_insurgency`  
**Canonical length T_r:** 5  
**Prepared:** 2026-05-17T21:51:21.052566+00:00  
**Commit:** `94af5a290b776099458d1e419f5c4d56ff604aae`  

## Instance counts

| Stage | Count |
|-------|-------|
| n_pos_input (curated events, training window 1789-2021) | 574 |
| Country not in local panel | -2 |
| BASELINE_TOO_SHORT (§3.2.2) | -316 |
| After baseline filter | 256 |
| Alignment dropouts | -0 |
| **Final instances in parquet** | **256** |

## Indicator coverage

**5/5** (100%) key indicators available in local panel snapshot.

**Available:** ['SM.POP.NETM', 'SP.DYN.LE00.IN', 'v2cacamps', 'v2csreprss', 'v2x_clphy']

**Missing (BLOCKED — not in local 37-indicator snapshot):**
[]

> **Honesty disclosure:** G3/G4 substrate verdicts are BLOCKED-on-substrate-availability. Re-run on full 104-indicator production panel required (substrate-audit-phase-1.json P0 actions).

## Dropout sample (first 10)

| country_id | event_year | reason |
|------------|-----------|--------|
| afghanistan | 1974 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=9<20, baseline=[1949,1968]) |
| afghanistan | 1975 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=10<20, baseline=[1950,1969]) |
| afghanistan | 1978 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=13<20, baseline=[1953,1972]) |
| afghanistan | 1979 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=14<20, baseline=[1954,1973]) |
| afghanistan | 1980 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=15<20, baseline=[1955,1974]) |
| afghanistan | 1981 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=16<20, baseline=[1956,1975]) |
| afghanistan | 1983 | BASELINE_TOO_SHORT:SM.POP.NETM (n_obs=18<20, baseline=[1958,1977]) |
| afghanistan | 1989 | BASELINE_TOO_SHORT:v2cacamps (country not in panel) |
| afghanistan | 1992 | BASELINE_TOO_SHORT:v2cacamps (country not in panel) |
| afghanistan | 1993 | BASELINE_TOO_SHORT:v2cacamps (country not in panel) |

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
    --recipe civil_war_and_insurgency \
    --indicator-panel data\shape_inputs_v2\civil_war_and_insurgency\indicator_panel.parquet \
    --positive-instances data\shape_inputs_v2\civil_war_and_insurgency\positives.csv \
    --indicator-ids SM.POP.NETM,SP.DYN.LE00.IN,v2cacamps,v2csreprss,v2x_clphy \
    --T-r 5
```