#!/usr/bin/env python3
"""
add_vdem_sheet.py — # THROWAWAY (per #373) — one-shot migration script
that adds a `vdem_indicators` sheet to `indicators/control-surface.xlsx`
with all 39 V-Dem indicators (VD-01..VD-39).

Filed under #494 (V-Dem SF-pipeline expansion). Replaces the hardcoded
`VDEM_INDICATORS` Python list in `scripts/ingest_vdem.py` with
spreadsheet-driven indicator selection — same pattern WB uses today.

Why a script (not just an XLSX edit):
  - Reproducible: the data source-of-truth (the indicator catalog at
    `docs/specs/methodology/indicator-catalog-detailed.md`) lives in a
    different repo. Codifying the migration shows the provenance.
  - Reviewable: the rows + categories + descriptions land as a
    reviewable Python file before they land in a binary XLSX.
  - Re-runnable: if the XLSX gets corrupted or needs to be regenerated
    from scratch, this script does it deterministically.

Run from qgi-data root:
  python scripts/add_vdem_sheet.py

Numeric IDs:
  - WB indicators occupy 1..260
  - 261..275 reserved for WB hold/new expansion (#487)
  - V-Dem starts at 276 → 314 (276..287 = VD-01..VD-12, the original
    Tier-1 set; 288..314 = VD-13..VD-39, the Tier-2 expansion #492)

# THROWAWAY — single-run data migration. After commit, this file
# documents what was done; no consumer should re-import or call this
# at runtime.
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl


SCRIPT_DIR = Path(__file__).parent
XLSX_PATH = SCRIPT_DIR.parent / "indicators" / "control-surface.xlsx"


# ---------------------------------------------------------------------------
# 39 V-Dem indicators (VD-01..VD-39).
#
# Source: docs/specs/methodology/indicator-catalog-detailed.md §V-Dem.
# Numeric IDs start at 276 (after the WB 1..260 + 15 reserved spots
# 261..275 for the planned WB expansion #487).
#
# Categories use the existing XLSX taxonomy (Economic / Demographic /
# Governance / Health / Education / Infrastructure / Military / Social /
# Environment / Other) — V-Dem indicators map naturally to Governance
# (institutional / political-system measures) and Social (rights,
# repression, civil-society, group-power measures).
#
# Descriptions are TIGHTENED from the catalog's recipe-rich version to
# a 1-sentence definition matching the WB rows' style. The longer
# recipe-mapping commentary stays in indicator-catalog-detailed.md.
# ---------------------------------------------------------------------------

VDEM_ROWS: list[tuple[str, int, str, str, str, str]] = [
    # (id_string, numeric_id, name, status, category, description)
    ("v2x_polyarchy",     276, "Electoral Democracy Index",
     "process", "Governance",
     "Composite measure of electoral democracy on a 0-1 scale (V-Dem). Combines suffrage, fair elections, freedom of expression, alternative information sources, and freedom of association."),
    ("v2x_libdem",        277, "Liberal Democracy Index",
     "process", "Governance",
     "Liberal democracy on a 0-1 scale (V-Dem). Adds rule of law, judicial constraints, and civil liberties on top of the electoral democracy index."),
    ("v2x_jucon",         278, "Judicial Constraints on Executive",
     "process", "Governance",
     "Extent to which the executive respects the constitution, complies with judicial rulings, and is constrained by the courts (V-Dem, 0-1)."),
    ("v2xlg_legcon",      279, "Legislative Constraints on Executive",
     "process", "Governance",
     "Extent to which the legislature and government agencies investigate and constrain the executive (V-Dem, 0-1)."),
    ("v2csreprss",        280, "Civil Society Repression",
     "process", "Social",
     "Government attempts to repress civil society organizations (V-Dem, 0-4 scale, higher = less repression)."),
    ("v2cacamps",         281, "Political Polarization",
     "process", "Social",
     "Extent to which society is polarized into antagonistic camps (V-Dem, 0-4)."),
    ("v2excrptps",        282, "Executive Corruption",
     "process", "Governance",
     "Pervasiveness of corruption among executive-branch officials (V-Dem, 0-4)."),
    ("v2x_freexp_altinf", 283, "Freedom of Expression and Alternative Information",
     "process", "Social",
     "Composite of media freedom, freedom of expression, and access to alternative information sources (V-Dem, 0-1)."),
    ("v2x_partip",        284, "Political Participation Index",
     "process", "Governance",
     "Active engagement of citizens in political processes beyond voting — civil society, local government, direct democracy (V-Dem, 0-1)."),
    ("v2x_regime",        285, "Regime Type",
     "process", "Governance",
     "Categorical regime classification (V-Dem): 0=closed autocracy, 1=electoral autocracy, 2=electoral democracy, 3=liberal democracy."),
    ("v2stfisccap",       286, "Fiscal Capacity",
     "process", "Economic",
     "State capacity to extract revenue and provide public goods (V-Dem, 0-1). Substitutes for the legacy v2stcapacity, retired in V-Dem v16."),
    ("v2x_clphy",         287, "Physical Violence Index",
     "process", "Social",
     "Physical integrity rights — freedom from torture, extrajudicial killing, political imprisonment (V-Dem, 0-1)."),
    # ---- Tier 2 expansion (#492) ----
    ("v2clkill",          288, "Freedom from Political Killings",
     "process", "Social",
     "Extent to which the state refrains from political killings (V-Dem, 0-4)."),
    ("v2cltort",          289, "Freedom from Torture",
     "process", "Social",
     "Extent to which the state refrains from physical or psychological torture of political prisoners (V-Dem, 0-4)."),
    ("v2x_clpol",         290, "Political Civil Liberties Index",
     "process", "Social",
     "Composite of freedom of association, expression, and assembly (V-Dem, 0-1)."),
    ("v2x_clpriv",        291, "Private Civil Liberties Index",
     "process", "Social",
     "Composite of property rights, freedom of movement, freedom of religion, and equality before the law (V-Dem, 0-1)."),
    ("v2mecenefm",        292, "Print/Broadcast Media Censorship",
     "process", "Governance",
     "Extent of government censorship of print or broadcast media (V-Dem, 0-4)."),
    ("v2x_corr",          293, "Political Corruption Index",
     "process", "Governance",
     "System-wide political corruption — public-sector, executive, legislative, and judicial corruption combined (V-Dem, 0-1)."),
    ("v2jureform",        294, "Judicial Reform Attempts",
     "process", "Governance",
     "Frequency of executive-led attempts to reform the judiciary (V-Dem, 0-4)."),
    ("v2lgbicam",         295, "Bicameralism",
     "process", "Governance",
     "Whether the legislature is unicameral or bicameral (V-Dem, 0-2 categorical)."),
    ("v2exl_legitlead",   296, "Legitimacy of Political Leadership",
     "process", "Governance",
     "Public legitimacy enjoyed by the head of state and head of government (V-Dem, 0-3)."),
    ("v2exremhog",        297, "Head of Government Removal Mechanism",
     "process", "Governance",
     "Categorical encoding of how the head of government left office (V-Dem): regular term, election loss, vote of no confidence, coup, assassination, etc."),
    ("v2xeg_eqprotec",    298, "Equal Protection Index",
     "process", "Social",
     "Extent to which civil rights are extended equally to all groups regardless of ethnicity, religion, gender, or socioeconomic position (V-Dem, 0-1)."),
    ("v2cseeorgs",        299, "Civil Society Organization Entry/Exit Freedom",
     "process", "Social",
     "Freedom for civil society organizations to form and dissolve without government interference (V-Dem, 0-4)."),
    ("v2csprtcpt",        300, "Civil Society Participatory Environment",
     "process", "Social",
     "Active participation in civil society organizations by the population at large (V-Dem, 0-4)."),
    ("v2x_gender",        301, "Women's Political Empowerment Index",
     "process", "Social",
     "Composite of women's civil liberties, civil society participation, and political participation (V-Dem, 0-1)."),
    ("v2pepwrgen",        302, "Power Distributed by Gender",
     "process", "Social",
     "Extent to which political power is distributed equally between men and women (V-Dem, 0-4)."),
    ("v2pepwrsoc",        303, "Power Distributed by Socioeconomic Position",
     "process", "Social",
     "Extent to which political power is distributed across socioeconomic strata (V-Dem, 0-4)."),
    ("v2pepwrort",        304, "Power Distributed by Sexual Orientation",
     "process", "Social",
     "Extent to which political power is distributed across sexual orientations (V-Dem, 0-4)."),
    ("v2pepwrses",        305, "Power Distributed by Social Group (Ethnic)",
     "process", "Social",
     "Extent to which political power is distributed across ethnic / social groups (V-Dem, 0-4)."),
    ("v2x_neopat",        306, "Neopatrimonialism Index",
     "process", "Governance",
     "Extent to which government is characterized by patronage networks, presidentialism, and clientelism (V-Dem, 0-1)."),
    ("v2xel_frefair",     307, "Free and Fair Elections Index",
     "process", "Governance",
     "Extent to which elections are free of irregularities and fair to all parties and candidates (V-Dem, 0-1)."),
    ("v2elintmon",        308, "International Election Monitoring",
     "process", "Governance",
     "Whether independent international monitors observed the most recent election (V-Dem, 0-1 binary)."),
    ("v2ex_hosw",         309, "Head of State — Who Holds Power",
     "process", "Governance",
     "Categorical encoding of who holds the head-of-state position (V-Dem): president, monarch, council, etc."),
    ("v2exaphogp",        310, "Appointment of Head of Government",
     "process", "Governance",
     "Categorical encoding of how the head of government is appointed (V-Dem): elected by legislature, elected directly, appointed by head of state, etc."),
    ("v2svdomaut",        311, "Domestic Autonomy",
     "process", "Governance",
     "Extent to which the state has autonomy from foreign powers in domestic decisions (V-Dem, 0-1)."),
    ("v2x_rule",          312, "Rule of Law Index",
     "process", "Governance",
     "Composite measure of rule of law — predictable law enforcement, judicial independence, equality before the law (V-Dem, 0-1)."),
    ("v2lgqstexp",        313, "Legislature Questions Officials in Practice",
     "process", "Governance",
     "Whether the legislature actively questions executive officials in practice (V-Dem, 0-4)."),
    ("v2psprlnks",        314, "Party Linkages to Voters",
     "process", "Governance",
     "Predominant linkage type between political parties and voters — programmatic, clientelistic, or identity-based (V-Dem, categorical)."),
]


def main() -> int:
    if not XLSX_PATH.exists():
        print(f"[error] XLSX not found at {XLSX_PATH}", file=sys.stderr)
        return 1

    print(f"[load] {XLSX_PATH}")
    wb = openpyxl.load_workbook(XLSX_PATH)

    if "vdem_indicators" in wb.sheetnames:
        print("[skip] sheet 'vdem_indicators' already exists; nothing to do.")
        return 0

    print(f"[create] new sheet 'vdem_indicators' ({len(VDEM_ROWS)} indicator rows)")
    ws = wb.create_sheet("vdem_indicators")

    # Header row — match phase_2_indicators column order exactly
    ws.append(["id_string", "numeric_id", "name", "status", "category", "description"])

    # Data rows
    for row in VDEM_ROWS:
        ws.append(list(row))

    # Numeric ID uniqueness check across both sheets — defensive
    wb_phase2 = wb["phase_2_indicators"]
    existing_ids = set()
    for row in wb_phase2.iter_rows(min_row=2, values_only=True):
        if row and row[1] is not None:
            existing_ids.add(int(row[1]))
    new_ids = {r[1] for r in VDEM_ROWS}
    overlap = existing_ids & new_ids
    if overlap:
        print(f"[error] numeric_id overlap with phase_2_indicators: {sorted(overlap)}",
              file=sys.stderr)
        return 1
    print(f"[verify] no numeric_id overlap "
          f"(WB: {min(existing_ids)}..{max(existing_ids)}, V-Dem: "
          f"{min(new_ids)}..{max(new_ids)})")

    wb.save(XLSX_PATH)
    print(f"[write] {XLSX_PATH} (sheets: {wb.sheetnames})")
    print(f"[done] V-Dem migration complete: 39 indicators added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
