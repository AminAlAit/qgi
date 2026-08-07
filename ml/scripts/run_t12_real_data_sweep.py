"""
T12 real-data MCMC driver: 36-config K-§2.5 sweep + production config.

Loads the four Path A v6.6 sidecar JSONs (qgi-data `14ebded`), builds the
real-data CellsArray via `prep_cells_from_arm_jsons`, and runs the Path B
partial-pooling model under each of the 36 sweep configurations defined
at `qgi-data/reference/v0.2-bayes-sweep-config.json` (qgi-data `b059cd6`).

Pre-registration discipline:
  - 36-config sweep verbatim from JSON (no analyst-tuned axes)
  - Per-config posterior + diagnostics JSON
  - Baseline config (tau_arm=0.30, halfcauchy=0.05, mu_center=0.168)
    routed against §5.2.2 4-tier table for the headline verdict
  - Sweep-stability check: verdict consistent across all 36 → trust
    the headline; verdict flips → QA-reviewable amber artefact

Ratification trail:
  - 6-seat T10 amendment (docs-specs `0db64f9`, 2026-05-15)
  - K-§2.5 sweep config (qgi-data `b059cd6`, 2026-05-15)
  - 3/3 trio READY-TO-FIRE (signoffs at c:/tmp/v0.2-T12-ready-to-fire/, 2026-05-15)
  - Founder per-session pipeline-run approval 2026-05-15

Per Kwame transparency requirement: `sweep_scope` field cited in every
result JSON.

Usage:
    python qgi-ml/scripts/run_t12_real_data_sweep.py \\
        --sweep-scope full36 \\
        --output-dir /tmp/t12-sweep-output
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent.parent.parent
SWEEP_CONFIG_JSON = ROOT / "qgi-data" / "reference" / "v0.2-bayes-sweep-config.json"


def _load_bayes_module():
    """Import the validate_weight_matrix_bayes module as a sibling."""
    bayes_path = Path(__file__).resolve().parent / "validate_weight_matrix_bayes.py"
    spec = importlib.util.spec_from_file_location(
        "validate_weight_matrix_bayes", bayes_path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_weight_matrix_bayes"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_sweep_configs(sweep_config_path: Path = SWEEP_CONFIG_JSON) -> dict:
    """Load the K-§2.5 sweep config from qgi-data."""
    with sweep_config_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def enumerate_sweep_grid(sweep_cfg: dict) -> list[dict]:
    """Enumerate the 3 × 3 × 4 = 36 Cartesian product of sweep axes."""
    axes = sweep_cfg["sweep_config_space"]["axes"]
    tau_arm_scales = axes["tau_arm_prior_scale"]["values"]
    halfcauchy_scales = axes["half_cauchy_scale"]["values"]
    mu_centers = axes["mu_center"]["values"]
    mu_scale = axes["mu_center"]["scale_held_at"]

    configs = []
    for tau in tau_arm_scales:
        for hc in halfcauchy_scales:
            for mu_c in mu_centers:
                configs.append({
                    "tau_arm_prior_scale": tau,
                    "half_cauchy_scale": hc,
                    "mu_prior_center": mu_c,
                    "mu_prior_scale": mu_scale,
                    "is_baseline": (
                        tau == axes["tau_arm_prior_scale"]["baseline_value"] and
                        hc == axes["half_cauchy_scale"]["baseline_value"] and
                        mu_c == axes["mu_center"]["baseline_value"]
                    ),
                })
    # QA pace-decision 2026-05-16: reorder baseline FIRST so it
    # completes even under a tight ceiling. The §5.2.2 verdict requires
    # baseline; sweep-stability check works on whatever else completes.
    configs.sort(key=lambda c: (not c["is_baseline"]))
    return configs


def build_model_with_overrides(cells, *, tau_arm_prior_scale: float,
                                half_cauchy_scale: float,
                                mu_prior_center: float, mu_prior_scale: float):
    """Build the PyMC partial-pooling model with sweep-config priors.

    Mirrors validate_weight_matrix_bayes.build_model() but takes prior
    values as kwargs instead of reading the module-level constants. The
    module constants represent the baseline; sweep configs perturb them.
    """
    import pymc as pm  # local import — heavy

    n_arms, n_countries, n_categories = cells.anomaly_score.shape
    arm_idx, country_idx, category_idx = np.indices(cells.anomaly_score.shape)
    arm_idx_flat = arm_idx.ravel()
    country_idx_flat = country_idx.ravel()
    category_idx_flat = category_idx.ravel()
    sector_idx_flat = cells.sector_idx_for_category[category_idx_flat]
    score_flat = cells.anomaly_score.ravel()
    observed = np.ma.masked_invalid(score_flat)

    coords = {
        "arm": cells.arm_labels,
        "country": cells.country_labels,
        "category": cells.category_labels,
        "sector": cells.sector_labels,
        "obs_id": np.arange(score_flat.size),
    }

    with pm.Model(coords=coords) as model:
        mu = pm.Normal("mu", mu=mu_prior_center, sigma=mu_prior_scale)
        tau_arm = pm.Normal("tau_arm", mu=0.0, sigma=tau_arm_prior_scale, dims="arm")
        sigma_sector = pm.HalfCauchy("sigma_sector", beta=half_cauchy_scale)
        alpha_sector = pm.Normal("alpha_sector", mu=0.0, sigma=sigma_sector, dims="sector")
        sigma_cat = pm.HalfCauchy("sigma_cat", beta=half_cauchy_scale, dims="sector")
        beta_cat_raw = pm.Normal("beta_cat_raw", mu=0.0, sigma=1.0, dims="category")
        beta_cat = pm.Deterministic(
            "beta_cat",
            beta_cat_raw * sigma_cat[cells.sector_idx_for_category],
            dims="category",
        )
        sigma_country = pm.HalfCauchy("sigma_country", beta=half_cauchy_scale)
        country_intercept_raw = pm.Normal(
            "country_intercept_raw", mu=0.0, sigma=1.0, dims="country"
        )
        country_intercept = pm.Deterministic(
            "country_intercept",
            sigma_country * country_intercept_raw,
            dims="country",
        )
        sigma = pm.HalfCauchy("sigma", beta=half_cauchy_scale)
        mean = (
            mu
            + tau_arm[arm_idx_flat]
            + alpha_sector[sector_idx_flat]
            + beta_cat[category_idx_flat]
            + country_intercept[country_idx_flat]
        )
        pm.Normal("anomaly_score_obs", mu=mean, sigma=sigma, observed=observed, dims="obs_id")

    return model


def route_verdict_against_5_2_2(
    posterior_mean: float, hdi_low: float, hdi_high: float,
    posterior_prob_swing_gt_005: float,
    anchor_battery_pass_count: int,
) -> dict:
    """Route the posterior result against the §5.2.2 4-tier exit table
    (Miriam Move 3, docs-specs `0db64f9` verbatim):

      HARD-FALSIFY: 94% HDI straddles zero AND P(swing > 0.05) < 0.05
                    AND anchor ≤ 2/8 evaluable pass
      SOFT-FALSIFY: 94% HDI straddles zero AND P(swing > 0.05) ∈ [0.05, 0.25]
                    AND anchor ≤ 2/8 evaluable pass
      PARTIAL:      94% HDI does NOT straddle zero AND lower bound < 0.10
                    (methodology-favoring direction); OR anchor 3-5/8 mixed
      PASS:         94% HDI lower bound ≥ 0.10 anomaly_score units
                    AND anchor ≥ 6/8 evaluable pass

    **Verdict-template §2.3 silent-corner branches (this function's
    responsibility):** The spec's PARTIAL/PASS tiers assume HDI is on
    the methodology-favoring side of zero (lower bound > 0). The spec
    §5.2.2 4-tier table is SILENT on two corner cases:
      (a) HDI entirely negative (anti-methodology direction; methodology
          arm A below null baseline arm D)
      (b) HDI straddles zero with P(swing > 0.05) > 0.25 (geometrically
          unlikely but not strictly excluded under fat-tailed posteriors)

    Per the verdict-routing template (docs-specs `5fc0980`) §2.3 step 2
    last branch + the QA-ratified Protocol-5 fidelity ruling, the
    silent corners route to "INCONSISTENT" with mandatory escalation
    to fresh 6-seat. (Spec §5.2.5 is the historical-clause section
    preserving the Path A pre-reg protocol verbatim; the silent-corner
    escalation authority comes from the verdict template, not §5.2.5.)
    The driver does NOT invent literal HARD-FALSIFY routing for the
    entirely-negative case even though the substantive read is
    anti-methodology — that is a 6-seat call, not a driver call.

    Returns dict with `tier`, `tier_definition`, `consequence`.
    """
    # Note on boundary conventions:
    # - hdi_straddles_zero uses NON-STRICT <= and >= (inclusive).
    #   Verdict template §2.3 step 1 uses STRICT (< 0 AND > 0). Inclusive
    #   is the conservative choice: hdi_high == 0 exactly (measure-zero in
    #   practice) routes to straddle/HARD-FALSIFY rather than to PARTIAL.
    # - hdi_entirely_negative uses STRICT < 0 on hdi_high — i.e. the boundary
    #   hdi_high == 0 falls to straddles_zero, NOT to entirely-negative.
    #   This is intentional: hdi_high == 0 is geometrically the boundary case
    #   between straddle and entirely-negative, and we prefer to route it
    #   through the spec's HARD-FALSIFY check (which has explicit P-threshold
    #   logic) rather than to the silent-corner escalation.
    hdi_straddles_zero = (hdi_low <= 0) and (hdi_high >= 0)
    hdi_entirely_negative = (hdi_high < 0)

    if hdi_entirely_negative:
        # verdict-template §2.3 silent corner (a): HDI entirely on the anti-methodology
        # side. Spec is silent; substantive read is HARD-FALSIFY-direction
        # but the routing call is 6-seat per Protocol-5 fidelity.
        return {
            "tier": "INCONSISTENT-anti-methodology",
            "tier_definition": (
                "94% HDI entirely below zero (entirely anti-methodology "
                "direction; methodology arm A below null baseline arm D). "
                "Spec §5.2.2 is silent on this corner; substantive read is "
                "HARD-FALSIFY-direction but routing requires 6-seat per "
                "verdict template §2.3 silent-corner branch."
            ),
            "consequence": (
                "Escalate to fresh 6-seat Majles. Convening reads the "
                "posterior magnitude + anchor-battery breakdown and rules "
                "among: (a) ratify HARD-FALSIFY-by-conscience close (route "
                "to T14 / #678), (b) ratify INERT (substrate-vs-methodology "
                "decomposition push to ML track), (c) re-execute Path B with "
                "Tariq A6/A7/A8 substrate refinement."
            ),
            "anchor_battery_required": "informational",
            "anchor_battery_actual": f"{anchor_battery_pass_count}/8",
        }

    if hdi_straddles_zero:
        if posterior_prob_swing_gt_005 < 0.05:
            return {
                "tier": "HARD-FALSIFY",
                "tier_definition": "94% HDI straddles zero AND P(swing > 0.05) < 0.05",
                "consequence": "Methodology direction closes on Path B. Route to T14 / #678.",
                "anchor_battery_required": "≤ 2/8 pass",
                "anchor_battery_actual": f"{anchor_battery_pass_count}/8",
            }
        elif 0.05 <= posterior_prob_swing_gt_005 <= 0.25:
            return {
                "tier": "SOFT-FALSIFY",
                "tier_definition": "94% HDI straddles zero AND P(swing > 0.05) ∈ [0.05, 0.25]",
                "consequence": "Halt Path B; ML track absorbs methodology load.",
                "anchor_battery_required": "≤ 2/8 pass",
                "anchor_battery_actual": f"{anchor_battery_pass_count}/8",
            }
        else:
            # verdict-template §2.3 silent corner (b): HDI straddles zero with P > 0.25.
            # Per verdict template §2.3 step 2 last branch, route to
            # INCONSISTENT-routing-anomaly with mandatory escalation. This
            # is NOT spec-PARTIAL — PARTIAL requires HDI to EXCLUDE zero
            # in the methodology-favoring direction.
            return {
                "tier": "INCONSISTENT-routing-anomaly",
                "tier_definition": (
                    "94% HDI straddles zero AND P(swing > 0.05) > 0.25. "
                    "Spec §5.2.2 is silent on this corner; geometrically "
                    "unlikely combination but not strictly excluded under "
                    "fat-tailed posteriors. Route to 6-seat per verdict "
                    "template §2.3 silent-corner branch."
                ),
                "consequence": "Escalate to fresh 6-seat convening (spec-silent corner).",
                "anchor_battery_required": "informational",
                "anchor_battery_actual": f"{anchor_battery_pass_count}/8",
            }

    # HDI does NOT straddle zero AND is in the methodology-favoring
    # direction (HDI_low > 0 here, since hdi_entirely_negative was
    # handled above). This is the case the spec's PARTIAL/PASS branches
    # were written to handle.
    if hdi_low < 0.10:
        return {
            "tier": "PARTIAL",
            "tier_definition": (
                "94% HDI excludes zero (methodology-favoring direction) "
                "BUT lower bound < 0.10 anomaly_score units, OR anchor "
                "battery 3/8 – 5/8 mixed"
            ),
            "consequence": "Escalate to fresh 6-seat convening.",
            "anchor_battery_required": "3/8 – 5/8 mixed",
            "anchor_battery_actual": f"{anchor_battery_pass_count}/8",
        }

    # HDI lower bound ≥ 0.10 in methodology-favoring direction
    if anchor_battery_pass_count >= 6:
        return {
            "tier": "PASS",
            "tier_definition": "94% HDI lower bound ≥ 0.10 AND ≥ 6/8 anchor",
            "consequence": "Phase 6 fires. Methodology vindicated.",
            "anchor_battery_required": "≥ 6/8 pass",
            "anchor_battery_actual": f"{anchor_battery_pass_count}/8",
        }
    else:
        return {
            "tier": "PARTIAL",
            "tier_definition": (
                "94% HDI lower bound ≥ 0.10 BUT anchor battery < 6/8 — "
                "swing real but country-axis evidence insufficient"
            ),
            "consequence": "Escalate to fresh 6-seat convening.",
            "anchor_battery_required": "≥ 6/8 pass",
            "anchor_battery_actual": f"{anchor_battery_pass_count}/8",
        }


def compute_anchor_battery(idata, country_labels: list[str],
                            anchor_country_ids: list[int]) -> dict:
    """§5.2.3 anchor battery per-country pass criterion:
       country_intercept[k] 94% HDI excludes zero AND lower bound ≥ 0.05.

    Note: anchor_country_ids are integer country_ids matching the substrate.
    Path A's cascade-anchor-case-battery.json has: Tunisia, Sri Lanka,
    Switzerland, Yemen, etc. (8 entries). We'll match by country_id (the
    label values, which are str(int) in our CellsArray).
    """
    import arviz as az  # local import
    pass_count = 0
    fail_count = 0
    skip_count = 0
    per_country = []
    ci_post = idata.posterior["country_intercept"]

    for anchor_cid in anchor_country_ids:
        anchor_str = str(anchor_cid)
        if anchor_str not in country_labels:
            skip_count += 1
            per_country.append({
                "country_id": anchor_cid,
                "status": "SKIP",
                "reason": "country not in substrate universe",
            })
            continue
        # Extract this country's country_intercept HDI
        ci_country = ci_post.sel(country=anchor_str)
        hdi = az.hdi(ci_country, hdi_prob=0.94)
        # arviz Dataset; the variable name is "country_intercept" but
        # after .sel(country=...) it remains keyed under that name
        try:
            lo = float(hdi["country_intercept"].sel(hdi="lower").item())
            hi = float(hdi["country_intercept"].sel(hdi="higher").item())
        except Exception:
            # Fallback: positional
            arr = list(hdi.data_vars.values())[0].values
            lo, hi = float(arr[0]), float(arr[1])

        excludes_zero = (lo > 0) or (hi < 0)
        passes_lower_bound = lo >= 0.05
        passed = excludes_zero and passes_lower_bound

        per_country.append({
            "country_id": anchor_cid,
            "status": "PASS" if passed else "FAIL",
            "hdi_94_low": lo,
            "hdi_94_high": hi,
            "excludes_zero": excludes_zero,
            "lower_bound_geq_005": passes_lower_bound,
        })
        if passed:
            pass_count += 1
        else:
            fail_count += 1

    return {
        "n_pass": pass_count,
        "n_fail": fail_count,
        "n_skip": skip_count,
        "per_country": per_country,
    }


def run_single_config(mod, cells, config: dict, *,
                      n_chains: int, n_draws: int, n_tune: int,
                      n_cores: int,
                      anchor_country_ids: list[int]) -> dict:
    """Run NUTS for a single sweep configuration; return diagnostics + posterior summary."""
    import arviz as az  # local import
    import pymc as pm

    config_id = (
        f"tau{config['tau_arm_prior_scale']}_"
        f"hc{config['half_cauchy_scale']}_"
        f"mu{config['mu_prior_center']}"
    )
    print(f"\n=== Config {config_id} {'(BASELINE)' if config['is_baseline'] else ''} ===", flush=True)
    t0 = time.time()

    model = build_model_with_overrides(
        cells,
        tau_arm_prior_scale=config["tau_arm_prior_scale"],
        half_cauchy_scale=config["half_cauchy_scale"],
        mu_prior_center=config["mu_prior_center"],
        mu_prior_scale=config["mu_prior_scale"],
    )

    with model:
        idata = pm.sample(
            draws=n_draws,
            tune=n_tune,
            chains=n_chains,
            cores=n_cores,
            random_seed=list(mod.CHAIN_SEEDS[:n_chains]),
            target_accept=mod.TARGET_ACCEPT,
            nuts={"max_treedepth": mod.MAX_TREEDEPTH},
            progressbar=False,
            return_inferencedata=True,
        )

    diagnostics = mod.compute_diagnostics(idata)

    # §5.2.1 headline metric: 94% HDI on tau_arm[A] - tau_arm[D]
    tau_post = idata.posterior["tau_arm"]
    a_minus_d = (tau_post.sel(arm="A") - tau_post.sel(arm="D")).rename("tau_arm_A_minus_D")
    hdi_94 = az.hdi(a_minus_d, hdi_prob=0.94)
    hdi_low = float(hdi_94["tau_arm_A_minus_D"].sel(hdi="lower").item())
    hdi_high = float(hdi_94["tau_arm_A_minus_D"].sel(hdi="higher").item())
    posterior_mean = float(a_minus_d.mean().item())
    # Posterior probability that the swing exceeds the 0.05 threshold
    flat = a_minus_d.values.ravel()
    posterior_prob_swing_gt_005 = float((flat > 0.05).mean())

    # §5.2.3 anchor battery
    anchor_battery = compute_anchor_battery(idata, cells.country_labels, anchor_country_ids)

    # §5.2.2 routing — only computed/cited for the BASELINE config
    verdict = None
    if config["is_baseline"]:
        verdict = route_verdict_against_5_2_2(
            posterior_mean=posterior_mean,
            hdi_low=hdi_low,
            hdi_high=hdi_high,
            posterior_prob_swing_gt_005=posterior_prob_swing_gt_005,
            anchor_battery_pass_count=anchor_battery["n_pass"],
        )

    elapsed = time.time() - t0
    print(f"  done in {elapsed/60:.1f} min", flush=True)
    print(f"  posterior tau[A]-tau[D] mean={posterior_mean:+.4f} HDI=[{hdi_low:+.4f}, {hdi_high:+.4f}]", flush=True)
    print(f"  diagnostics: rhat={diagnostics['max_r_hat']:.4f} nEff={diagnostics['min_n_eff']:.0f} "
          f"div={diagnostics['n_divergences']} eBfmi={diagnostics['min_e_bfmi']:.3f} "
          f"treedepth_sat={diagnostics['treedepth_saturation_rate']:.4f}", flush=True)
    if verdict:
        print(f"  §5.2.2 VERDICT: {verdict['tier']}", flush=True)

    return {
        "config": config,
        "config_id": config_id,
        "is_baseline": config["is_baseline"],
        "elapsed_seconds": elapsed,
        "posterior_a_minus_d": {
            "mean": posterior_mean,
            "hdi_94_low": hdi_low,
            "hdi_94_high": hdi_high,
            "posterior_prob_swing_gt_005": posterior_prob_swing_gt_005,
        },
        "anchor_battery": anchor_battery,
        "diagnostics": diagnostics,
        "verdict": verdict,  # only populated for baseline
    }


def _load_anchor_country_ids(cells, anchor_battery_json_path: Path) -> list[int]:
    """Load the 8 anchor-case country_ids from cascade-anchor-case-battery.json.

    Path B's §5.2.3 uses the same anchor cohort as Path A:
    Malta, Iceland, Norway, Tunisia, Sri Lanka, Venezuela, Switzerland,
    Yemen. The source-of-truth JSON top-level array is `cases` (NOT
    `anchor_cases` — that was a confused reading of the v6 sidecar's
    `anchor_case_battery.cases` resolved-results structure).

    **Country_id wired post-2026-05-16** per qgi-data#54: each case
    now carries a `country_id` integer field (resolved from the
    canonical pipeline-A countries.csv master), matching the
    country_id values that the v6 cells tensor uses to index countries.

    Only in-universe cases are returned; cases with
    `in_evaluation_universe == false` (Malta #1, Iceland #2 at v0.1a)
    are skipped per the JSON's universe_note — they will count toward
    the §5.2.3 denominator only when the universe flag flips at Phase 6.

    Args:
        cells: CellsArray (used to validate country_ids are in
            cells.country_labels for graceful degradation if a v6
            sidecar dropped a country).
        anchor_battery_json_path: path to qgi-data/reference/
            cascade-anchor-case-battery.json (qgi-data `45cf568` or later
            for the country_id-enriched version).

    Returns:
        list of integer country_ids for the in-universe anchor cases
        whose IDs are present in cells.country_labels. Empty list if
        the JSON is missing or schema-incompatible.
    """
    if not anchor_battery_json_path.exists():
        print(
            f"  WARNING: anchor-case-battery.json not found at "
            f"{anchor_battery_json_path}; using empty anchor list",
            flush=True,
        )
        return []
    with anchor_battery_json_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    cases = data.get("cases", [])
    n_total = len(cases)

    # Build set of cells country_ids (labels are str(int))
    cells_country_ids = set()
    for label in cells.country_labels:
        try:
            cells_country_ids.add(int(label))
        except (ValueError, TypeError):
            pass

    in_universe = []
    out_of_universe = []
    missing_id_field = []
    missing_from_cells = []
    for case in cases:
        cid = case.get("country_id")
        country = case.get("country", "<unknown>")
        if cid is None:
            missing_id_field.append(country)
            continue
        if not case.get("in_evaluation_universe", True):
            out_of_universe.append(f"{country}({cid})")
            continue
        if int(cid) not in cells_country_ids:
            missing_from_cells.append(f"{country}({cid})")
            continue
        in_universe.append(int(cid))

    print(
        f"  anchor battery: {n_total} cases declared; "
        f"{len(in_universe)} in-universe + resolvable; "
        f"{len(out_of_universe)} out-of-universe (Phase 6 gate); "
        f"{len(missing_from_cells)} missing from v6 cells; "
        f"{len(missing_id_field)} missing country_id field",
        flush=True,
    )
    if missing_id_field:
        print(
            f"  WARNING: missing country_id on: {missing_id_field}. "
            f"Update qgi-data/reference/cascade-anchor-case-battery.json "
            f"per qgi-data#54 enrichment.",
            flush=True,
        )
    if out_of_universe:
        print(f"  out-of-universe: {out_of_universe}", flush=True)
    if missing_from_cells:
        print(f"  missing-from-cells: {missing_from_cells}", flush=True)

    return in_universe


def main():
    parser = argparse.ArgumentParser(description="T12 real-data MCMC sweep")
    parser.add_argument("--sweep-scope", choices=["full36", "baseline-only"], default="full36",
                        help="Pre-registration field: which subset of K-§2.5 configs to run")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/t12-sweep-output"),
                        help="Where to write per-config + aggregate JSONs")
    parser.add_argument("--n-chains", type=int, default=None,
                        help="Override module N_CHAINS (default: production ratified)")
    parser.add_argument("--n-draws", type=int, default=None,
                        help="Override module N_DRAWS (default: production ratified)")
    parser.add_argument("--n-tune", type=int, default=None,
                        help="Override module N_TUNE (default: production ratified)")
    parser.add_argument("--n-cores", type=int, default=None,
                        help="Override default chain parallelism. Default = n_chains "
                             "(parallel). Set to 1 to run chains sequentially in a "
                             "single process — workaround for cold-start multiprocess "
                             "pipe race on arm64 AL2023 per QA pace-decision-2 "
                             "abort signal (2026-05-16).")
    args = parser.parse_args()

    mod = _load_bayes_module()

    n_chains = args.n_chains or mod.N_CHAINS
    n_draws = args.n_draws or mod.N_DRAWS
    n_tune = args.n_tune or mod.N_TUNE
    n_cores = args.n_cores if args.n_cores is not None else n_chains

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("=== T12 real-data MCMC sweep ===", flush=True)
    print(f"  Sweep scope: {args.sweep_scope}", flush=True)
    print(f"  Sampling config: {n_chains} chains x {n_draws} draws + {n_tune} tune", flush=True)
    print(f"  Output dir: {args.output_dir}", flush=True)

    print(f"\n[1/4] Loading sweep config from {SWEEP_CONFIG_JSON}", flush=True)
    sweep_cfg = load_sweep_configs(SWEEP_CONFIG_JSON)
    all_configs = enumerate_sweep_grid(sweep_cfg)
    print(f"  enumerated {len(all_configs)} configs (expect 36)", flush=True)

    if args.sweep_scope == "baseline-only":
        configs_to_run = [c for c in all_configs if c["is_baseline"]]
        print(f"  baseline-only mode: running {len(configs_to_run)} configs (expect 1)", flush=True)
    else:
        configs_to_run = all_configs

    print("\n[2/4] Loading real-data CellsArray via prep_cells_from_arm_jsons", flush=True)
    cells = mod.prep_cells_from_arm_jsons()
    print(f"  cells shape: {cells.anomaly_score.shape}", flush=True)
    print(f"  non-NaN cells: {int(np.sum(~np.isnan(cells.anomaly_score)))}/{cells.anomaly_score.size}", flush=True)
    cells_sha = cells.sha256_provenance()
    print(f"  cells SHA-256: {cells_sha}", flush=True)

    anchor_country_ids = _load_anchor_country_ids(
        cells,
        ROOT / "qgi-data" / "reference" / "cascade-anchor-case-battery.json",
    )
    print(f"  anchor battery: {len(anchor_country_ids)} cases loaded", flush=True)

    print(f"\n[3/4] Running {len(configs_to_run)} configurations", flush=True)
    started_at = datetime.now(timezone.utc).isoformat()
    per_config_results = []
    for idx, config in enumerate(configs_to_run):
        print(f"\n--- {idx+1}/{len(configs_to_run)} ---", flush=True)
        try:
            result = run_single_config(
                mod, cells, config,
                n_chains=n_chains, n_draws=n_draws, n_tune=n_tune,
                n_cores=n_cores,
                anchor_country_ids=anchor_country_ids,
            )
            per_config_results.append(result)
            # Write per-config JSON immediately so partial failures don't lose progress
            cfg_json_path = args.output_dir / f"config_{result['config_id']}.json"
            cfg_json_path.write_text(
                json.dumps(result, indent=2, default=str), encoding="utf-8"
            )
        except Exception as e:
            print(f"  CONFIG FAILED: {e}", flush=True)
            per_config_results.append({
                "config": config,
                "config_id": (
                    f"tau{config['tau_arm_prior_scale']}_"
                    f"hc{config['half_cauchy_scale']}_"
                    f"mu{config['mu_prior_center']}"
                ),
                "error": str(e),
            })

    finished_at = datetime.now(timezone.utc).isoformat()

    print("\n[4/4] Writing aggregate sweep JSON", flush=True)
    baseline_verdict = None
    for r in per_config_results:
        if r.get("is_baseline") and r.get("verdict"):
            baseline_verdict = r["verdict"]
            break

    # Stability check: do all configs agree with baseline §5.2.2 verdict?
    # Simpler check: do all configs have an HDI that excludes zero in the same direction?
    stability = {
        "n_configs_run": len(per_config_results),
        "n_configs_successful": sum(1 for r in per_config_results if "error" not in r),
        "n_configs_failed": sum(1 for r in per_config_results if "error" in r),
    }

    # Cross-config HDI summary
    hdi_lows = [r["posterior_a_minus_d"]["hdi_94_low"]
                for r in per_config_results if "error" not in r]
    hdi_highs = [r["posterior_a_minus_d"]["hdi_94_high"]
                for r in per_config_results if "error" not in r]
    if hdi_lows:
        stability["cross_config_hdi_low_min"] = min(hdi_lows)
        stability["cross_config_hdi_low_max"] = max(hdi_lows)
        stability["cross_config_hdi_high_min"] = min(hdi_highs)
        stability["cross_config_hdi_high_max"] = max(hdi_highs)
        # Verdict stability: do all HDIs straddle zero or do all exclude zero?
        all_straddle_zero = all(lo <= 0 <= hi for lo, hi in zip(hdi_lows, hdi_highs))
        all_exclude_zero_positive = all(lo > 0 for lo in hdi_lows)
        all_exclude_zero_negative = all(hi < 0 for hi in hdi_highs)
        stability["all_configs_straddle_zero"] = all_straddle_zero
        stability["all_configs_exclude_zero_positive"] = all_exclude_zero_positive
        stability["all_configs_exclude_zero_negative"] = all_exclude_zero_negative

    aggregate = {
        "schema_version": 1,
        "sweep_scope": args.sweep_scope,
        "started_at": started_at,
        "finished_at": finished_at,
        "sweep_config_source": "qgi-data/reference/v0.2-bayes-sweep-config.json @ b059cd6",
        "spec_commit": "docs-specs `0db64f9` (6-seat amendment 2026-05-15)",
        "trio_ready_to_fire_ratification": {
            "convening_date": "2026-05-15",
            "verdict": "3/3 unanimous READY-TO-FIRE",
            "signoffs_at": "c:/tmp/v0.2-T12-ready-to-fire/signoff_{priya,kwame,jihoon}.md",
        },
        "cells_provenance": {
            "shape": list(cells.anomaly_score.shape),
            "n_non_nan": int(np.sum(~np.isnan(cells.anomaly_score))),
            "sha256": cells_sha,
            "source": "Path A v6.6 sidecars at qgi-data `14ebded` / phase4-validation-arm{A,B,C,D}-v6.json",
        },
        "sampling_config_per_run": {
            "n_chains": n_chains,
            "n_draws": n_draws,
            "n_tune": n_tune,
            "target_accept": mod.TARGET_ACCEPT,
            "max_treedepth": mod.MAX_TREEDEPTH,
            "chain_seeds": list(mod.CHAIN_SEEDS[:n_chains]),
        },
        "baseline_5_2_2_verdict": baseline_verdict,
        "sweep_stability": stability,
        "per_config": per_config_results,
        "audit_trail": {
            "amended_priors_baseline": {
                "tau_arm_scale": mod.TAU_ARM_PRIOR_SCALE,
                "half_cauchy_scale": mod.HALF_CAUCHY_SCALE,
                "mu_center": mod.MU_PRIOR_CENTER,
                "mu_scale": mod.MU_PRIOR_SCALE,
            },
            "diagnostic_var_names": list(mod.DIAGNOSTIC_VAR_NAMES),
            "diagnostic_thresholds": {
                "r_hat_max": mod.R_HAT_THRESHOLD,
                "n_eff_min": mod.N_EFF_THRESHOLD,
                "divergence_pct_max": mod.DIVERGENCE_THRESHOLD_PCT,
                "e_bfmi_min": mod.E_BFMI_THRESHOLD,
                "treedepth_saturation_rate_max": mod.TREEDEPTH_SATURATION_THRESHOLD,
            },
        },
    }

    agg_path = args.output_dir / "sweep_aggregate.json"
    agg_path.write_text(json.dumps(aggregate, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {agg_path}", flush=True)
    if baseline_verdict:
        print("\n=== HEADLINE §5.2.2 VERDICT (baseline config) ===", flush=True)
        print(f"  {baseline_verdict['tier']}: {baseline_verdict['tier_definition']}", flush=True)
        print(f"  Consequence: {baseline_verdict['consequence']}", flush=True)
        print(f"  Anchor: {baseline_verdict['anchor_battery_actual']}", flush=True)
    print("\n=== Sweep complete ===", flush=True)


if __name__ == "__main__":
    main()
