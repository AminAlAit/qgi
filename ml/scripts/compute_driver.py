"""Per-country driver analysis for QGI Trajectory Engine (TE capability #4).

TE add-on #4: per-country driver ("why this country").
Per te-new-capabilities-spec.md §4 (locked 2026-05-24, chat QGI-R&D | 002).

Answers: "What's driving THIS country's score?" — a pure transform of the
existing recipe-similarity-scores artifact. No model re-fit, no panels needed.

## Method

For each country, reads `scores[country].per_indicator[ind].weighted_contribution`;
ranks descending; expresses each as a share of the total ABSOLUTE contribution
mass (bounded [-100, +100]; sign = direction toward/away from the crisis profile):

    signal_share_pct = weighted_contribution / sum(|weighted_contribution|) * 100

(Dividing by the signed sum cosine_similarity_S is incoherent when S is near-zero
or negative — a single positive contribution then exceeds S, yielding "shares"
>100% or sign-inverted. Absolute-mass sharing fixes this; review 2026-05-24.)

## Honesty gate (binding — M8-R5)

Framed as ATTRIBUTION to the similarity score, NOT advice, NOT probability.
Mandatory copy: "X contributes N% of this country's similarity score" —
never "X causes the risk."

Indicator labels loaded verbatim from docs/specs/methodology/indicator-catalog-detailed.md
(the v2elintmon = "International Election Monitoring" lesson — never confabulate).

## Usage

    python scripts/compute_driver.py \\
        --scores-file ../qgi-data/reference/recipe-similarity-scores-foreign_intervention-2021.json \\
        --output-dir ../qgi-data/reference/ \\
        [--catalog-file ../docs/specs/methodology/indicator-catalog-detailed.md]

Output:
    driver-{recipe_id}-{eval_year}.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Indicator label catalog — verbatim from docs/specs/methodology/indicator-catalog-detailed.md
# and related docs. Never confabulate. Unknown codes get a TODO note.
# Spec §4 binding: "indicator labels verbatim from indicator-catalog-detailed.md
# (the v2elintmon = 'International Election Monitoring' lesson)."
# ---------------------------------------------------------------------------

# Hand-curated from docs/specs/methodology/indicator-catalog-detailed.md (VD-XX table)
# and docs/specs/methodology/indicator-license-audit.md (WB WGI section).
# Update this dict when new indicators are added to the catalog.
_CATALOG_LABELS: dict[str, str] = {
    # V-Dem indicators — VD-XX from indicator-catalog-detailed.md
    "v2x_libdem": "Liberal Democracy Index",
    "v2x_polyarchy": "Electoral Democracy Index",
    "v2x_corr": "Political Corruption Index",
    "v2x_cspart": "Civil Society Participation Index",
    "v2xlg_legcon": "Legislative Constraints on the Executive",
    "v2x_jucon": "Judicial Constraints on the Executive",
    "v2x_pubcorr": "Public Sector Corruption Index",
    "v2x_freexp_altinf": "Freedom of Expression",
    "v2x_partip": "Political Participation",
    "v2x_regime": "Regime Type",
    "v2stfisccap": "Fiscal Capacity",        # VD-11; renamed from v2stcapacity in V-Dem v16
    "v2x_clphy": "Physical Violence Index",
    "v2clkill": "Freedom from Political Killings",
    "v2cltort": "Freedom from Torture",
    "v2mecenefm": "Print/Broadcast Media Censorship",  # catalog VD-17 (NOT "internet filtering" — verified 2026-05-24)
    "v2x_gender": "Women's Political Empowerment Index",
    "v2pepwrgen": "Power Distributed by Gender",   # VD-27
    "v2pepwrsoc": "Power Distributed by Socioeconomic Position",
    "v2pepwrort": "Power Distributed by Sexual Orientation",
    "v2pepwrses": "Power Distributed by Social Group (Ethnic)",
    "v2x_neopat": "Neopatrimonialism Index",
    "v2xel_frefair": "Free and Fair Elections Index",
    "v2svdomaut": "Domestic Autonomy / Sovereignty",
    "v2x_rule": "Rule of Law Index",
    "v2lgqstexp": "Legislature Questions Officials in Practice",
    "v2psprlnks": "Party Linkages to Voters",
    "v2cseeorgs": "CSO Entry/Exit Freedom",
    "v2csprtcpt": "Civil Society Participatory Environment",
    # VD-33: v2elintmon = International Election Monitoring
    # (explicitly named in spec §4 as the "lesson" case — must be exact)
    "v2elintmon": "International Election Monitoring",   # VD-33
    "v2ex_hosw": "Head of State — Who Holds Power",
    "v2exaphogp": "Appointment of Head of Government",
    # World Bank WGI indicators — from indicator-license-audit.md + composite-indicators.md
    "CC.EST": "Control of Corruption (WGI)",
    "GE.EST": "Government Effectiveness (WGI)",
    "PV.EST": "Political Stability and Absence of Violence (WGI)",
    "RL.EST": "Rule of Law (WGI)",
    "RQ.EST": "Regulatory Quality (WGI)",     # Used in foreign_intervention
    "VA.EST": "Voice and Accountability (WGI)",
    # World Bank non-WGI — WB-XX from indicator-catalog-detailed.md
    "VC.BTL.DETH": "Battle-related deaths per 100K",
    "VC.IHR.PSRC.P5": "Intentional homicide rate",
    "SM.POP.REFG.OR": "Refugees by country of origin",
    "SM.POP.REFG": "Refugees hosted by country",
    "VC.IDP.NWDS": "New internal displacements",
    "IC.REG.COST.PC.ZS": "Business startup cost % GNI",
    "IC.LGL.DURS": "Contract enforcement time (days)",
    "BM.TRF.PWKR.CD.DT": "Remittance outflows",
    "FX.OWN.TOTL.ZS": "Financial account ownership % pop",
    "GC.DOD.TOTL.GD.ZS": "Government debt-to-GDP",
    "DT.INT.DECT.GN.ZS": "Interest on external debt % GNI",
    "DT.DOD.DSTC.ZS": "Short-term debt % total external",
    "FB.AST.NPER.ZS": "Bank non-performing loans % gross",
    "GFDD.DI.01": "Bank assets % GDP",
    "DC.ODA.TOTL.GD.ZS": "Net ODA disbursed % GDP",
    # FAOSTAT — FA-XX
    "FA-01": "Prevalence of undernourishment (%)",
}


def get_indicator_label(indicator_code: str) -> str:
    """Return the canonical indicator label from the catalog.

    If the code is not in the catalog, returns the raw code with a TODO note
    to prevent confabulation (per feedback_indicator_labels_canonical_catalog.md).

    Parameters
    ----------
    indicator_code : str — the raw indicator code (e.g. 'v2elintmon', 'RQ.EST')

    Returns
    -------
    str — canonical label from catalog, or '{code} [TODO: add to catalog]' if unknown
    """
    if indicator_code in _CATALOG_LABELS:
        return _CATALOG_LABELS[indicator_code]
    return f"{indicator_code} [TODO: add to indicator-catalog-detailed.md]"


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_country_drivers(
    country_entry: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compute per-indicator drivers for one country.

    Ranks indicators by weighted_contribution descending.
    signal_share_pct = weighted_contribution / sum(|weighted_contribution|) * 100
    (share of total ABSOLUTE contribution mass; bounded [-100, +100]; sign =
    direction toward/away from the crisis profile).

    Parameters
    ----------
    country_entry : dict — one entry from scores[country], with keys:
        cosine_similarity_S, risk_score, zone, per_indicator

    Returns
    -------
    List of dicts, one per indicator, sorted by weighted_contribution descending.
    Each dict: {indicator, indicator_label, weighted_contribution, signal_share_pct, cosine}
    """
    per_ind = country_entry["per_indicator"]

    # Denominator = total ABSOLUTE contribution mass, NOT the signed sum S.
    # Dividing by S is incoherent when S is near-zero or negative (a single
    # positive contribution then exceeds S, producing "shares" >100% or sign-
    # inverted — see review 2026-05-24). Sharing by absolute mass keeps every
    # signal_share_pct bounded in [-100, +100], makes |shares| sum to 100%, and
    # preserves the sign (direction toward / away from the crisis profile).
    abs_mass = sum(abs(float(d["weighted_contribution"])) for d in per_ind.values())

    rows: list[dict[str, Any]] = []
    for ind, ind_data in per_ind.items():
        wc = float(ind_data["weighted_contribution"])
        cos = float(ind_data["cosine"])
        signal_share_pct = (wc / abs_mass * 100.0) if abs_mass > 0.0 else 0.0
        rows.append({
            "indicator": ind,
            "indicator_label": get_indicator_label(ind),
            "weighted_contribution": wc,
            "signal_share_pct": signal_share_pct,
            "cosine": cos,
        })

    # Rank by weighted_contribution descending
    rows.sort(key=lambda r: r["weighted_contribution"], reverse=True)
    return rows


def compute_all_drivers(
    scores_data: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Compute per-country drivers for all countries in the scores artifact.

    Parameters
    ----------
    scores_data : dict — parsed recipe-similarity-scores-{recipe}-{year}.json

    Returns
    -------
    Dict mapping country name → sorted list of driver dicts
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for country, entry in scores_data["scores"].items():
        result[country] = compute_country_drivers(entry)
    return result


# ---------------------------------------------------------------------------
# Artifact builder
# ---------------------------------------------------------------------------


def build_output(
    scores_data: dict[str, Any],
    drivers: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Build the full driver artifact dict.

    Parameters
    ----------
    scores_data : dict — parsed recipe-similarity-scores artifact
    drivers : dict — output of compute_all_drivers()

    Returns
    -------
    dict — the full artifact, ready for json.dumps
    """
    return {
        "recipe_id": scores_data["recipe_id"],
        "eval_year": int(scores_data["evaluation_year"]),
        "capability": "per-country-driver",
        "capability_spec_section": "#4",
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "binding_provenance": (
            "docs/specs/internal/ops/ml-track/te-new-capabilities-spec.md §4 "
            "(locked 2026-05-24, chat QGI-R&D | 002). "
            "Pure transform of recipe-similarity-scores artifact; no model re-fit."
        ),
        "m8_r5_note": (
            "M8-R5 BINDING: ATTRIBUTION to the similarity score only. "
            "signal_share_pct = an indicator's share of this country's total "
            "absolute contribution mass (sign indicates direction toward/away "
            "from the crisis profile) — this is NOT advice and NOT a probability "
            "claim. The model is discriminative, not causal. "
            "Never interpret as 'X causes the risk'."
        ),
        "method": (
            "Rank indicators by weighted_contribution descending. "
            "signal_share_pct = weighted_contribution / sum(|weighted_contribution|) "
            "* 100 — share of total ABSOLUTE contribution mass, bounded [-100, +100], "
            "|shares| sum to 100%. (Denominator is the absolute mass, NOT the signed "
            "sum S, which is incoherent near S=0; review 2026-05-24.) "
            "No computation beyond sort + normalize of existing per_indicator data."
        ),
        "selected_indicators": scores_data.get("selected_indicators", []),
        "chosen_window": scores_data.get("chosen_window"),
        "n_countries": len(drivers),
        "drivers": drivers,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scores-file", type=Path, required=True,
        help="Path to recipe-similarity-scores-{recipe}-{year}.json.",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Output directory for driver-{recipe}-{year}.json.",
    )
    parser.add_argument(
        "--catalog-file", type=Path, default=None,
        help=(
            "Optional path to indicator-catalog-detailed.md. "
            "Currently unused (labels are baked in from the catalog); "
            "reserved for future dynamic catalog loading."
        ),
    )
    return parser


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.scores_file, encoding="utf-8") as f:
        scores_data = json.load(f)

    recipe_id = scores_data["recipe_id"]
    eval_year = int(scores_data["evaluation_year"])
    n_countries = len(scores_data.get("scores", {}))

    print(f"Recipe: {recipe_id}, eval_year: {eval_year}, n_countries: {n_countries}")

    drivers = compute_all_drivers(scores_data)
    artifact = build_output(scores_data, drivers)

    out_path = args.output_dir / f"driver-{recipe_id}-{eval_year}.json"
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")

    # Sanity print: top driver for first 3 countries
    print("\n=== TOP DRIVER SANITY CHECK ===")
    for i, (country, drv_list) in enumerate(drivers.items()):
        if i >= 5:
            break
        top = drv_list[0]
        print(
            f"  {country}: top driver = {top['indicator']} "
            f"({top['indicator_label']!r}), "
            f"signal_share_pct={top['signal_share_pct']:.1f}%, "
            f"weighted_contribution={top['weighted_contribution']:.4f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
