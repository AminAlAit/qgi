#!/usr/bin/env python3
"""Tests for generate_gpr_country_json.py (test-first per the QGI script rule).

Locks the tier thresholds and the validated-record counts so the published
GPR methodology table can never silently drift. Notably pins Colombia in
Tier C (delta_spearman 0.3463 < 0.35), correcting a downstream miscount.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_gpr_country_json as gen  # noqa: E402


@pytest.fixture(scope="module")
def results() -> dict:
    with open(gen.RESULTS, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def payload(results: dict) -> dict:
    return gen.build(results)


def test_tier_boundaries():
    # Strict thresholds: >= 0.50 -> A, [0.35, 0.50) -> B, < 0.35 -> C.
    assert gen.tier_for(0.50) == "A"
    assert gen.tier_for(0.4999) == "B"
    assert gen.tier_for(0.35) == "B"
    assert gen.tier_for(0.3499) == "C"
    assert gen.tier_for(0.3463) == "C"  # Colombia


def test_all_44_validated(payload: dict):
    countries = payload["countries"]
    assert len(countries) == 44
    assert all(c["validated"] is True for c in countries.values())
    assert all(c["tier"] in ("A", "B", "C") for c in countries.values())
    assert all(c["tier_label"] for c in countries.values())


def test_no_validated_missing_metric(payload: dict):
    for c in payload["countries"].values():
        assert isinstance(c["delta_spearman"], float)
        assert isinstance(c["spike_recall"], float)
        assert c["n_months"] > 0
        assert c["name"] and c["name"] != c["iso3"]  # every iso3 has a real name


def test_tier_counts_match_validated_record(payload: dict):
    # From gpr-full-validation-results.md section 2: 16 / 21 / 7, and the
    # headline "37 of 44 pass the 0.35 soft bar" (A + B).
    counts = payload["meta"]["tier_counts"]
    assert counts == {"A": 16, "B": 21, "C": 7}
    assert counts["A"] + counts["B"] == 37


def test_known_country_classifications(payload: dict):
    c = payload["countries"]
    assert c["SAU"]["tier"] == "A" and c["SAU"]["delta_spearman"] > 0.69
    assert c["TWN"]["tier"] == "A"  # 0.5029, just over the A bar
    assert c["NOR"]["tier"] == "B"  # 0.359, just over the B bar
    assert c["COL"]["tier"] == "C"  # 0.3463, just under the B bar
    assert c["PER"]["tier"] == "C" and c["PER"]["delta_spearman"] < 0.20
    assert c["SAU"]["name"] == "Saudi Arabia"


def test_meta_block(payload: dict):
    m = payload["meta"]
    assert m["n_validated"] == 44
    assert m["n_total"] == 215
    assert 0.45 <= m["headline_delta_spearman"] <= 0.47
    assert m["pct_passing_soft_bar"] == round(37 / 44, 4)
    assert m["source"].endswith("gpr-full-results.json")


def test_ranked_insertion_order(payload: dict):
    # Countries inserted by descending signal strength for scannable diffs.
    deltas = [c["delta_spearman"] for c in payload["countries"].values()]
    assert deltas == sorted(deltas, reverse=True)


def test_series_shape(payload: dict):
    # Every validated country carries a movement series (may be empty in CI).
    for c in payload["countries"].values():
        s = c["series"]
        assert set(s.keys()) == {"dates", "values"}
        assert len(s["dates"]) == len(s["values"])
        assert all(isinstance(v, float) for v in s["values"])
        assert s["dates"] == sorted(s["dates"])  # ascending YYYY-MM


@pytest.mark.skipif(
    not os.path.exists(gen.PROXY_PATH), reason="proxy series file absent (CI)"
)
def test_series_content(payload: dict):
    sau = payload["countries"]["SAU"]["series"]
    assert len(sau["dates"]) == 136
    assert sau["dates"][0] == "2015-02" and sau["dates"][-1] == "2026-05"
    assert all(0.0 <= v <= 1.0 for v in sau["values"])
