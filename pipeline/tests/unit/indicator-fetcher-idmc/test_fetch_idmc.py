"""Tests for the IDMC fetcher transform (enrichment stage 2).

Pure logic only - no AWS, no network. The base's AWS clients are lazy and the
IDMC HTTP call is lazy-imported inside fetch_idmc_raw(), so importing these
modules needs neither boto3 nor requests.

Synthetic payload mirrors the live public-figure-analyses response shape
confirmed on 2026-06-25:
  {
    "iso3":                 "IRQ",
    "year":                 2024,
    "figure_cause_name":    "Conflict",   # "Conflict" | "Disaster"
    "figure_category_name": "IDPs",       # "IDPs" | "Internal Displacements"
    "figures":              1031475,
  }
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_QGI_PIPELINE = Path(__file__).resolve().parents[3]
_BASE_DIR = _QGI_PIPELINE / "batch" / "_fetcher_base"
_IDMC_SRC = _QGI_PIPELINE / "batch" / "indicator-fetcher-idmc" / "src"
for _p in (_BASE_DIR, _IDMC_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qgi_fetcher_base as base  # noqa: E402
import fetch_idmc as f  # noqa: E402


# ---------------------------------------------------------------------------
# Shared base sanity checks (same as UNHCR suite; ensures base importable)
# ---------------------------------------------------------------------------


def test_iso3_map_from_df_uppercases_and_skips_blanks():
    df = pd.DataFrame(
        {
            "iso_alpha3": ["afg", "SDN", "", None],
            "qgi_name": ["Afghanistan", "Sudan", "Nowhere", "AlsoNowhere"],
        }
    )
    m = base.iso3_map_from_df(df)
    assert m == {"AFG": "Afghanistan", "SDN": "Sudan"}


def test_to_canonical_frame_coerces_dedups_sorts_drops_nan():
    df = pd.DataFrame(
        {
            "country": ["B", "A", "A", "A"],
            "year": ["2010", 2009, 2009, 2011],
            "value": [10.0, 5.0, 9.0, np.nan],
        }
    )
    out = base.to_canonical_frame(df)
    assert list(out.columns) == base.OUTPUT_COLUMNS
    assert out["year"].dtype == np.int64
    assert out["value"].dtype == np.float64
    assert (out["is_predicted"] == False).all()  # noqa: E712
    records = out.to_dict("records")
    # (A, 2009) deduped: keep-last = 9.0; (A, 2011) NaN dropped; (B, 2010) = 10.0
    assert records == [
        {"country": "A", "year": 2009, "value": 9.0, "is_predicted": False},
        {"country": "B", "year": 2010, "value": 10.0, "is_predicted": False},
    ]


# ---------------------------------------------------------------------------
# ISO3 map used across IDMC tests
# ---------------------------------------------------------------------------

ISO3 = {
    "AFG": "Afghanistan",
    "SYR": "Syria",
    "SDN": "Sudan",
    "USA": "United States",
}

# ---------------------------------------------------------------------------
# Representative synthetic payload (25 records spanning all 3 ID indicators
# plus noise rows that must be filtered out)
# ---------------------------------------------------------------------------

SYNTHETIC_RECORDS = [
    # --- ID-01 Conflict / Internal Displacements ---
    {
        "iso3": "AFG",
        "year": 2020,
        "figure_cause_name": "Conflict",
        "figure_category_name": "Internal Displacements",
        "figures": 400000,
    },
    {
        "iso3": "AFG",
        "year": 2021,
        "figure_cause_name": "Conflict",
        "figure_category_name": "Internal Displacements",
        "figures": 500000,
    },
    {
        "iso3": "SYR",
        "year": 2020,
        "figure_cause_name": "Conflict",
        "figure_category_name": "Internal Displacements",
        "figures": 300000,
    },
    {
        "iso3": "SDN",
        "year": 2021,
        "figure_cause_name": "Conflict",
        "figure_category_name": "Internal Displacements",
        "figures": 150000,
    },
    # --- ID-02 Disaster / Internal Displacements ---
    {
        "iso3": "AFG",
        "year": 2020,
        "figure_cause_name": "Disaster",
        "figure_category_name": "Internal Displacements",
        "figures": 80000,
    },
    {
        "iso3": "SYR",
        "year": 2020,
        "figure_cause_name": "Disaster",
        "figure_category_name": "Internal Displacements",
        "figures": 20000,
    },
    {
        "iso3": "SDN",
        "year": 2021,
        "figure_cause_name": "Disaster",
        "figure_category_name": "Internal Displacements",
        "figures": 90000,
    },
    # --- ID-03 Conflict / IDPs (stock) ---
    {"iso3": "AFG", "year": 2020, "figure_cause_name": "Conflict", "figure_category_name": "IDPs", "figures": 3500000},
    {"iso3": "SYR", "year": 2020, "figure_cause_name": "Conflict", "figure_category_name": "IDPs", "figures": 6000000},
    {"iso3": "SDN", "year": 2021, "figure_cause_name": "Conflict", "figure_category_name": "IDPs", "figures": 2000000},
    # --- noise: unknown ISO3 -> must be dropped ---
    {
        "iso3": "ZZZ",
        "year": 2020,
        "figure_cause_name": "Conflict",
        "figure_category_name": "Internal Displacements",
        "figures": 999,
    },
    # --- noise: Disaster / IDPs category -> not wired to any indicator ---
    {"iso3": "AFG", "year": 2020, "figure_cause_name": "Disaster", "figure_category_name": "IDPs", "figures": 111},
    # --- noise: missing year -> must be dropped ---
    {
        "iso3": "SDN",
        "year": None,
        "figure_cause_name": "Conflict",
        "figure_category_name": "Internal Displacements",
        "figures": 50000,
    },
    # --- noise: blank figures -> treated as 0.0 ---
    {
        "iso3": "USA",
        "year": 2021,
        "figure_cause_name": "Conflict",
        "figure_category_name": "Internal Displacements",
        "figures": "",
    },
]


# ---------------------------------------------------------------------------
# ID-01: new displacements by conflict
# ---------------------------------------------------------------------------


def test_parse_id01_filters_conflict_internal_displacements():
    cfg = f.SPECS["ID-01"]
    out = f.parse_idmc_records(SYNTHETIC_RECORDS, cfg, ISO3)
    # only rows: AFG/2020, AFG/2021, SYR/2020, SDN/2021, USA/2021(0.0)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert recs[("Afghanistan", 2020)] == 400000.0
    assert recs[("Afghanistan", 2021)] == 500000.0
    assert recs[("Syria", 2020)] == 300000.0
    assert recs[("Sudan", 2021)] == 150000.0
    assert recs[("United States", 2021)] == 0.0  # blank figures -> 0.0
    # Disaster rows must not appear
    assert ("Afghanistan", 2020) not in {k for k, v in recs.items() if v == 80000.0}


def test_parse_id01_excludes_unknown_iso3():
    cfg = f.SPECS["ID-01"]
    out = f.parse_idmc_records(SYNTHETIC_RECORDS, cfg, ISO3)
    assert "ZZZ" not in [r["country"] for r in out.to_dict("records")]


def test_parse_id01_excludes_missing_year():
    cfg = f.SPECS["ID-01"]
    out = f.parse_idmc_records(SYNTHETIC_RECORDS, cfg, ISO3)
    # The None-year SDN row must not appear
    assert not any(
        r["country"] == "Sudan" and r["year"] != r["year"]  # nan check
        for r in out.to_dict("records")
    )
    # More directly: all year values must be non-null integers
    years = out["year"].tolist()
    assert all(isinstance(y, int) for y in years)


# ---------------------------------------------------------------------------
# ID-02: new displacements by disaster
# ---------------------------------------------------------------------------


def test_parse_id02_filters_disaster_internal_displacements():
    cfg = f.SPECS["ID-02"]
    out = f.parse_idmc_records(SYNTHETIC_RECORDS, cfg, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert recs[("Afghanistan", 2020)] == 80000.0
    assert recs[("Syria", 2020)] == 20000.0
    assert recs[("Sudan", 2021)] == 90000.0
    # Conflict rows must not appear
    assert ("Afghanistan", 2021) not in recs  # AFG/2021 only in conflict rows


def test_parse_id02_does_not_include_idps_category():
    cfg = f.SPECS["ID-02"]
    out = f.parse_idmc_records(SYNTHETIC_RECORDS, cfg, ISO3)
    # The Disaster/IDPs noise row (AFG 2020 figures=111) must not inflate the result
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert recs.get(("Afghanistan", 2020)) == 80000.0  # not 80000 + 111


# ---------------------------------------------------------------------------
# ID-03: IDP stock by conflict
# ---------------------------------------------------------------------------


def test_parse_id03_filters_conflict_idps():
    cfg = f.SPECS["ID-03"]
    out = f.parse_idmc_records(SYNTHETIC_RECORDS, cfg, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert recs[("Afghanistan", 2020)] == 3500000.0
    assert recs[("Syria", 2020)] == 6000000.0
    assert recs[("Sudan", 2021)] == 2000000.0
    # Disaster/IDPs noise row must not appear
    assert len(recs) == 3  # exactly the 3 Conflict/IDPs rows


def test_parse_id03_excludes_disaster_idps():
    cfg = f.SPECS["ID-03"]
    out = f.parse_idmc_records(SYNTHETIC_RECORDS, cfg, ISO3)
    # The Disaster/IDPs row for AFG (figures=111) must not be included
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # If it were included it would have made AFG/2020 = 3500111
    assert recs.get(("Afghanistan", 2020)) == 3500000.0


# ---------------------------------------------------------------------------
# Empty / edge-case handling
# ---------------------------------------------------------------------------


def test_parse_empty_when_nothing_resolves():
    cfg = f.SPECS["ID-01"]
    out = f.parse_idmc_records(
        [
            {
                "iso3": "ZZZ",
                "year": 2020,
                "figure_cause_name": "Conflict",
                "figure_category_name": "Internal Displacements",
                "figures": 5,
            }
        ],
        cfg,
        ISO3,
    )
    assert list(out.columns) == ["country", "year", "value"]
    assert len(out) == 0


def test_parse_empty_records_list():
    cfg = f.SPECS["ID-02"]
    out = f.parse_idmc_records([], cfg, ISO3)
    assert list(out.columns) == ["country", "year", "value"]
    assert len(out) == 0


def test_parse_deduplicates_country_year():
    """Duplicate (country, year) rows sum to a single row."""
    cfg = f.SPECS["ID-01"]
    records = [
        {
            "iso3": "AFG",
            "year": 2020,
            "figure_cause_name": "Conflict",
            "figure_category_name": "Internal Displacements",
            "figures": 100,
        },
        {
            "iso3": "AFG",
            "year": 2020,
            "figure_cause_name": "Conflict",
            "figure_category_name": "Internal Displacements",
            "figures": 50,
        },
    ]
    out = f.parse_idmc_records(records, cfg, ISO3)
    assert len(out) == 1
    assert out.iloc[0]["value"] == 150.0


def test_parse_non_numeric_figures_skipped():
    """Records with non-numeric, non-blank figures values are skipped."""
    cfg = f.SPECS["ID-01"]
    records = [
        {
            "iso3": "AFG",
            "year": 2020,
            "figure_cause_name": "Conflict",
            "figure_category_name": "Internal Displacements",
            "figures": "n/a",
        },
    ]
    out = f.parse_idmc_records(records, cfg, ISO3)
    assert len(out) == 0


# ---------------------------------------------------------------------------
# SPECS coverage
# ---------------------------------------------------------------------------


def test_specs_cover_all_three():
    assert set(f.SPECS) == {"ID-01", "ID-02", "ID-03"}


def test_specs_each_has_required_keys():
    for iid, cfg in f.SPECS.items():
        assert "figure_cause_name" in cfg, f"{iid} missing figure_cause_name"
        assert "figure_category_name" in cfg, f"{iid} missing figure_category_name"


def test_specs_cause_values():
    causes = {v["figure_cause_name"] for v in f.SPECS.values()}
    assert causes <= {"Conflict", "Disaster"}


def test_specs_category_values():
    categories = {v["figure_category_name"] for v in f.SPECS.values()}
    assert categories <= {"Internal Displacements", "IDPs"}
