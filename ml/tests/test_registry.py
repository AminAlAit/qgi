"""Tests for the indicator-enrichment candidate registry (stage 0)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ENRICH_DIR = Path(__file__).resolve().parents[1] / "scripts" / "enrichment"
if str(ENRICH_DIR) not in sys.path:
    sys.path.insert(0, str(ENRICH_DIR))

import registry as rg  # noqa: E402


def _reg_with(*entries):
    reg = rg.empty_registry()
    for kw in entries:
        rg.add_indicator(reg, **kw)
    return reg


def test_add_allocates_numeric_id_in_provider_block():
    reg = rg.empty_registry()
    e = rg.add_indicator(reg, indicator_id="UC-01", provider="UCDP",
                         name="Battle deaths", category="Military")
    lo, hi = rg.PROVIDER_BLOCKS["UCDP"]
    assert lo <= e["numeric_id"] <= hi
    assert e["status"] == "candidate"
    # next allocation is distinct and still in-block
    e2 = rg.add_indicator(reg, indicator_id="UC-02", provider="UCDP",
                          name="Active conflicts", category="Military")
    assert e2["numeric_id"] == e["numeric_id"] + 1


def test_allocate_returns_lowest_free_in_block():
    reg = rg.empty_registry()
    lo, _ = rg.PROVIDER_BLOCKS["UNHCR"]
    rg.add_indicator(reg, indicator_id="UN-x", provider="UNHCR", name="x",
                     category="Demographic", numeric_id=lo)   # occupy block start
    assert rg.allocate_numeric_id(reg, "UNHCR") == lo + 1      # next free
    reg["indicators"] = []
    assert rg.allocate_numeric_id(reg, "UNHCR") == lo          # lowest free when empty


def test_add_rejects_duplicate_id_and_bad_category():
    reg = rg.empty_registry()
    rg.add_indicator(reg, indicator_id="IL-01", provider="ILOSTAT", name="x", category="Economic")
    with pytest.raises(rg.RegistryError):
        rg.add_indicator(reg, indicator_id="IL-01", provider="ILOSTAT", name="y", category="Economic")
    with pytest.raises(rg.RegistryError):
        rg.add_indicator(reg, indicator_id="IL-02", provider="ILOSTAT", name="z", category="Nonsense")


def test_allocate_raises_when_block_full():
    reg = rg.empty_registry()
    lo, hi = rg.PROVIDER_BLOCKS["IDMC"]
    for i in range(lo, hi + 1):
        rg.add_indicator(reg, indicator_id=f"ID-{i}", provider="IDMC", name="x", category="Demographic")
    with pytest.raises(rg.RegistryError, match="full"):
        rg.allocate_numeric_id(reg, "IDMC")


def test_transition_enforces_legal_paths():
    reg = _reg_with(dict(indicator_id="UN-01", provider="UNHCR", name="Refugees", category="Demographic"))
    # candidate -> vetted -> active is legal and stamps lifecycle dates
    rg.transition(reg, "UN-01", "vetted")
    assert rg.get_indicator(reg, "UN-01")["lifecycle"]["vetted"] is not None
    rg.transition(reg, "UN-01", "active")
    assert rg.get_indicator(reg, "UN-01")["lifecycle"]["activated"] is not None
    # active -> candidate is illegal
    with pytest.raises(rg.RegistryError, match="illegal transition"):
        rg.transition(reg, "UN-01", "candidate")


def test_transition_quarantine_with_reason():
    reg = _reg_with(dict(indicator_id="OE-05", provider="OECD", name="Gini", category="Social"))
    rg.transition(reg, "OE-05", "quarantined", reason="coverage:38 countries")
    e = rg.get_indicator(reg, "OE-05")
    assert e["status"] == "quarantined"
    assert e["lifecycle"]["reason"] == "coverage:38 countries"


def test_validate_clean_and_detects_collisions():
    reg = _reg_with(
        dict(indicator_id="UC-01", provider="UCDP", name="a", category="Military"),
        dict(indicator_id="IL-01", provider="ILOSTAT", name="b", category="Economic"),
    )
    assert rg.validate_registry(reg) == []
    # inject a numeric_id collision and an out-of-block id
    reg["indicators"][1]["numeric_id"] = reg["indicators"][0]["numeric_id"]
    reg["indicators"].append({
        "indicator_id": "BAD", "provider": "UCDP", "numeric_id": 99999,
        "name": "n", "status": "candidate", "category": "Military",
    })
    errs = rg.validate_registry(reg)
    assert any("duplicate numeric_id" in e for e in errs)
    assert any("outside UCDP block" in e for e in errs)


def test_to_control_surface_maps_status_and_excludes_unready():
    reg = rg.empty_registry()
    rg.add_indicator(reg, indicator_id="UC-01", provider="UCDP", name="a", category="Military",
                     status="active", provider_meta={"endpoint": "ucdpapi"})
    rg.add_indicator(reg, indicator_id="UC-02", provider="UCDP", name="b", category="Military",
                     status="held")
    rg.add_indicator(reg, indicator_id="UC-03", provider="UCDP", name="c", category="Military",
                     status="candidate")      # not ready -> excluded
    rg.add_indicator(reg, indicator_id="UC-04", provider="UCDP", name="d", category="Military",
                     status="quarantined")    # failed -> excluded
    sheets = rg.to_control_surface(reg)
    rows = sheets["ucdp_indicators"]
    ids = {r["id_string"]: r["status"] for r in rows}
    assert ids == {"UC-01": "process", "UC-02": "hold"}   # only active+held, mapped
    # canonical header present + provider_meta passed through
    row = next(r for r in rows if r["id_string"] == "UC-01")
    for col in rg.CANONICAL_HEADER:
        assert col in row
    assert row["endpoint"] == "ucdpapi"


def test_to_control_surface_uses_legacy_sheet_names():
    reg = rg.empty_registry()
    rg.add_indicator(reg, indicator_id="NY.GDP.MKTP.KD.ZG", provider="WB", name="GDP growth",
                     category="Economic", status="active", numeric_id=1)
    rg.add_indicator(reg, indicator_id="v2x_libdem", provider="VDEM", name="Lib dem",
                     category="Governance", status="active", numeric_id=276)
    sheets = rg.to_control_surface(reg)
    assert "phase_2_indicators" in sheets   # WB legacy sheet name
    assert "vdem_indicators" in sheets


def test_ext_blocks_resolve_to_base_provider_sheet():
    # overflow blocks map back to the base provider; plain providers pass through
    assert rg.base_provider("WB_EXT") == "WB"
    assert rg.base_provider("VDEM_EXT") == "VDEM"
    assert rg.base_provider("UCDP") == "UCDP"
    assert rg.provider_for_sheet("WB_EXT") == "phase_2_indicators"
    assert rg.provider_for_sheet("VDEM_EXT") == "vdem_indicators"
    # a new WB indicator allocated from WB_EXT lands in the legacy WB sheet,
    # NOT a dead 'wb_ext_indicators' sheet nothing reads.
    reg = rg.empty_registry()
    lo, _ = rg.PROVIDER_BLOCKS["WB_EXT"]
    rg.add_indicator(reg, indicator_id="SL.UEM.NEET.ZS", provider="WB_EXT",
                     name="NEET", category="Social", status="active", numeric_id=lo)
    sheets = rg.to_control_surface(reg)
    assert "phase_2_indicators" in sheets
    assert "wb_ext_indicators" not in sheets
    assert sheets["phase_2_indicators"][0]["id_string"] == "SL.UEM.NEET.ZS"


def test_to_allow_list_is_active_only():
    reg = rg.empty_registry()
    rg.add_indicator(reg, indicator_id="UC-01", provider="UCDP", name="a", category="Military",
                     status="active")
    rg.add_indicator(reg, indicator_id="UC-02", provider="UCDP", name="b", category="Military",
                     status="vetted")     # not active -> not in allow-list
    al = rg.to_allow_list(reg)
    assert al["counts"]["active_indicators"] == 1
    assert len(al["allow_list_numeric_ids"]) == 1
    assert al["allow_list_numeric_ids"] == sorted(al["allow_list_numeric_ids"])
