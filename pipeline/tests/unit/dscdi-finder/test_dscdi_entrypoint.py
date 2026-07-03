"""Unit tests for run_dscdi_entrypoint.py — the DSCDI Batch entrypoint.

These tests cover the orchestration layer that the pure-function
test_dscdi_finder.py suite does NOT exercise:
  - env-var contract (missing INDICATOR_ID raises)
  - load_panel pivots long → wide
  - output schema matches Glue dscdis table (negative + dtype assertions)
  - output partitioned by country_a_id
  - both A→B and B→A pairs (no upper-triangle dedup)
  - self-correlation excluded
  - Class A → two row groups (is_demeaned=True AND False)
  - Class A has exactly two distinct is_demeaned values
  - Class B → only is_demeaned=False
  - empty panel → no files written
  - manifest schema matches Glue dscdi_indicator_manifest table
  - demeaning_insufficient flag propagates from DSCDIResult to manifest
  - suppressed_reason='no_transform_outlier' for NY.GDP.MKTP.KD.ZG
  - country label NaN guard (M-1 from plan v5)

All tests use moto[s3] for the S3 layer. No real AWS calls.
"""

from __future__ import annotations

import os
import sys
from io import BytesIO

import boto3
import numpy as np
import pandas as pd
import pytest
from moto import mock_aws

from conftest import (
    COUNTRIES_DEFAULT,
    COUNTRIES_TO_ID_DEFAULT,
    TEST_BUCKET,
    TEST_INDICATOR_ID,
    make_audit_json,
    make_countries_csv,
    make_indicator_map_csv,
    make_long_panel_parquet,
    make_synthetic_panel,
)


# ---------------------------------------------------------------------------
# Test 1 — Env-var contract
# ---------------------------------------------------------------------------


def test_env_var_contract_missing_indicator_id_raises(monkeypatch, dscdi_finder_mod, s3_mock):
    """main() returns 1 when INDICATOR_ID is not set."""
    _, bucket = s3_mock
    monkeypatch.setenv("S3_BUCKET", bucket)
    monkeypatch.delenv("INDICATOR_ID", raising=False)

    sys.modules.pop("run_dscdi_entrypoint", None)
    import importlib.util
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "batch"
        / "dscdi-finder"
        / "src"
        / "run_dscdi_entrypoint.py"
    )
    spec = importlib.util.spec_from_file_location("run_dscdi_entrypoint", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_dscdi_entrypoint"] = mod
    spec.loader.exec_module(mod)

    assert mod.main() == 1


# ---------------------------------------------------------------------------
# Test 2 — load_panel pivots long → wide
# ---------------------------------------------------------------------------


def test_load_panel_pivots_long_to_wide(entrypoint_mod, populated_s3):
    _, bucket = populated_s3
    panel = entrypoint_mod.load_panel(bucket, "panels/", "v2x_libdem")

    assert isinstance(panel, pd.DataFrame)
    assert panel.index.name == "year"
    # 20 default countries from COUNTRIES_DEFAULT
    assert set(panel.columns) == set(COUNTRIES_DEFAULT)
    # 30 default years (1990..2019)
    assert len(panel) == 30
    # Both axes named — production panels come from
    # `df.pivot_table(columns="country", ...)` which sets the columns
    # axis name. _matrix_to_long depends on this contract; see the
    # 2026-05-10 Stage F smoke regression test below.
    assert panel.columns.name == "country"


# ---------------------------------------------------------------------------
# Test 2b — _matrix_to_long handles a corr matrix with both axes named
# (regression for the 2026-05-10 Stage F smoke run failure)
# ---------------------------------------------------------------------------


def test_matrix_to_long_handles_named_axes(entrypoint_mod):
    """Regression: _matrix_to_long must not crash when both axes are named.

    Stage F smoke run on 2026-05-10 (job 69fd0374, indicator v2x_libdem)
    crashed with `ValueError: cannot insert country, already exists`
    because:
      1. load_panel pivots with `pivot_table(columns="country", ...)`
         which names the panel's columns axis "country"
      2. panel.corr() inherits that name on BOTH index and columns of
         the resulting square matrix
      3. _matrix_to_long.stack().reset_index() then tries to insert two
         columns both called "country"

    The fix uses `rename_axis(index=..., columns=...)` BEFORE the stack
    so the resulting MultiIndex level names are unique. This test fixes
    the input to match the production shape (both axes named) and would
    have caught the bug pre-merge.
    """
    countries = ["A", "B", "C", "D"]
    countries_map = {c: i + 1 for i, c in enumerate(countries)}

    # Match production: square matrix with both axes named "country"
    # (what panel.corr() returns when the panel was pivot_table'd).
    corr = pd.DataFrame(
        [[1.0, 0.8, 0.6, 0.4], [0.8, 1.0, 0.5, 0.3], [0.6, 0.5, 1.0, 0.2], [0.4, 0.3, 0.2, 1.0]],
        index=pd.Index(countries, name="country"),
        columns=pd.Index(countries, name="country"),
    )

    # Should not raise
    out = entrypoint_mod._matrix_to_long(corr, countries_map)

    # 4 countries → 4*3 = 12 directed pairs (self excluded)
    assert len(out) == 12
    assert set(out.columns) == {"country_a_id", "country_b_id", "correlation"}
    assert out["country_a_id"].dtype == np.uint16
    assert out["country_b_id"].dtype == np.uint16
    assert out["correlation"].dtype == np.float32

    # Value spot-check: the (A=1, B=2) pair must carry corr=0.8 from the
    # source matrix (pins the country-a vs country-b mapping so a future
    # refactor that transposes the stack would fail loudly).
    ab = out[(out["country_a_id"] == 1) & (out["country_b_id"] == 2)]
    assert len(ab) == 1
    assert ab["correlation"].iloc[0] == pytest.approx(0.8, rel=1e-5)
    # Symmetric: (A=2, B=1) also exists and has the same correlation
    ba = out[(out["country_a_id"] == 2) & (out["country_b_id"] == 1)]
    assert len(ba) == 1
    assert ba["correlation"].iloc[0] == pytest.approx(0.8, rel=1e-5)


# ---------------------------------------------------------------------------
# Test 3 — output schema matches Glue dscdis table
# ---------------------------------------------------------------------------


def test_output_schema_matches_glue_table(entrypoint_mod, dscdi_finder_mod):
    """Pairwise output columns + dtypes match qgi_data.dscdis Glue schema.

    Glue schema (post PR-2b):
      country_b_id smallint, correlation float, indicator_numeric_id smallint,
      contains_predicted boolean, is_demeaned boolean, indicator_class string
      (partition: country_a_id smallint)

    Negative assertions verify the dropped SCDI columns (length,
    start_year_a, start_year_b) are ABSENT from the entrypoint output.
    """
    panel = make_synthetic_panel(COUNTRIES_DEFAULT[:5])
    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    output = entrypoint_mod.build_pairwise_rows(
        result,
        indicator_numeric_id=1001,
        countries_map={c: i for i, c in enumerate(COUNTRIES_DEFAULT[:5], 1)},
    )

    # Expected columns present (country_a_id is included pre-write,
    # dropped at partition write time)
    expected = {
        "country_a_id",
        "country_b_id",
        "correlation",
        "indicator_numeric_id",
        "contains_predicted",
        "is_demeaned",
        "indicator_class",
    }
    assert set(output.columns) == expected, f"unexpected columns: {set(output.columns) ^ expected}"

    # Negative assertions (M-5 from plan v5 strict review): SCDI columns absent
    assert "length" not in output.columns
    assert "start_year_a" not in output.columns
    assert "start_year_b" not in output.columns

    # Dtype assertions (M-6 from plan v5)
    assert str(output["country_a_id"].dtype) == "uint16"
    assert str(output["country_b_id"].dtype) == "uint16"
    assert str(output["indicator_numeric_id"].dtype) == "uint16"
    assert str(output["correlation"].dtype) == "float32"
    assert output["is_demeaned"].dtype == bool
    assert output["contains_predicted"].dtype == bool
    # indicator_class is a string-typed column. Pandas 2.0 → object;
    # pandas 2.2+ default may infer the new StringDtype. Both serialize
    # to Athena `string` correctly via pyarrow.
    indicator_class_dtype = output["indicator_class"].dtype
    assert pd.api.types.is_object_dtype(indicator_class_dtype) or pd.api.types.is_string_dtype(indicator_class_dtype), (
        f"indicator_class dtype must be string-typed, got {indicator_class_dtype!r}"
    )


# ---------------------------------------------------------------------------
# Test 4 — output partitioned by country_a_id
# ---------------------------------------------------------------------------


def test_output_partitioned_by_country_a_id(entrypoint_mod, populated_s3):
    """write_pairwise_output writes one Parquet per unique country_a_id."""
    client, bucket = populated_s3
    countries = COUNTRIES_DEFAULT[:5]
    country_map = {c: i for i, c in enumerate(countries, 1)}
    panel = make_synthetic_panel(countries)

    import importlib.util
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent.parent.parent / "batch" / "dscdi-finder" / "src" / "dscdi_finder.py"
    spec = importlib.util.spec_from_file_location("dscdi_finder", src)
    df_mod = importlib.util.module_from_spec(spec)
    sys.modules["dscdi_finder"] = df_mod
    spec.loader.exec_module(df_mod)

    result = df_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    output = entrypoint_mod.build_pairwise_rows(result, 1001, country_map)

    n_files = entrypoint_mod.write_pairwise_output(output, bucket, "dscdis", "v2x_libdem")

    # 5 countries → up to 5 partition files (one per country_a)
    assert 1 <= n_files <= 5

    # Verify keys follow Hive partition pattern
    listing = client.list_objects_v2(Bucket=bucket, Prefix="dscdis/")
    keys = [obj["Key"] for obj in listing.get("Contents", [])]
    assert all("/country_a_id=" in k for k in keys), f"non-Hive keys found: {keys}"
    assert all(k.endswith("v2x_libdem.parquet") for k in keys)


# ---------------------------------------------------------------------------
# Test 5 — both A→B and B→A pairs (no upper-triangle dedup)
# ---------------------------------------------------------------------------


def test_pairs_include_both_directions(entrypoint_mod, dscdi_finder_mod):
    countries = COUNTRIES_DEFAULT[:4]
    country_map = {c: i for i, c in enumerate(countries, 1)}
    panel = make_synthetic_panel(countries)

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    output = entrypoint_mod.build_pairwise_rows(result, 1001, country_map)

    # For 4 countries: 4 × 3 = 12 directed pairs (excluding self).
    # Both (A=1, B=2) and (A=2, B=1) must appear.
    pairs = set(zip(output["country_a_id"], output["country_b_id"]))
    assert (1, 2) in pairs and (2, 1) in pairs


# ---------------------------------------------------------------------------
# Test 6 — self-correlation excluded
# ---------------------------------------------------------------------------


def test_self_correlation_excluded(entrypoint_mod, dscdi_finder_mod):
    countries = COUNTRIES_DEFAULT[:5]
    country_map = {c: i for i, c in enumerate(countries, 1)}
    panel = make_synthetic_panel(countries)

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    output = entrypoint_mod.build_pairwise_rows(result, 1001, country_map)

    self_pairs = output[output["country_a_id"] == output["country_b_id"]]
    assert len(self_pairs) == 0, f"self-correlation rows found: {self_pairs}"


# ---------------------------------------------------------------------------
# Test 7 — Class A writes both demeaned and undemeaned rows
# ---------------------------------------------------------------------------


def test_class_a_writes_both_demeaned_and_undemeaned_rows(entrypoint_mod, dscdi_finder_mod):
    """v2x_libdem (Class A) produces both is_demeaned=True AND False rows."""
    countries = COUNTRIES_DEFAULT[:6]
    country_map = {c: i for i, c in enumerate(countries, 1)}
    panel = make_synthetic_panel(countries)

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    assert result.demeaning_applied is True  # sanity: Class A panel
    assert result.baseline_undemeaned is not None

    output = entrypoint_mod.build_pairwise_rows(result, 1001, country_map)

    is_demeaned_values = set(output["is_demeaned"].unique().tolist())
    assert True in is_demeaned_values
    assert False in is_demeaned_values


# ---------------------------------------------------------------------------
# Test 8 — Class A has exactly two row groups (no third category)
# ---------------------------------------------------------------------------


def test_class_a_has_exactly_two_row_groups(entrypoint_mod, dscdi_finder_mod):
    countries = COUNTRIES_DEFAULT[:6]
    country_map = {c: i for i, c in enumerate(countries, 1)}
    panel = make_synthetic_panel(countries)

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    output = entrypoint_mod.build_pairwise_rows(result, 1001, country_map)

    is_demeaned_values = set(output["is_demeaned"].unique().tolist())
    assert is_demeaned_values == {True, False}, f"expected exactly {{True, False}}, got {is_demeaned_values}"


# ---------------------------------------------------------------------------
# Test 9 — Class B writes only is_demeaned=False rows
# ---------------------------------------------------------------------------


def test_class_b_writes_only_demeaned_false_rows(entrypoint_mod, dscdi_finder_mod):
    """RL.EST (Class B) has no baseline substrate; only is_demeaned=False."""
    countries = COUNTRIES_DEFAULT[:6]
    country_map = {c: i for i, c in enumerate(countries, 1)}
    panel = make_synthetic_panel(countries)

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="RL.EST", panel=panel, audit_classification="I(0)")
    assert result.demeaning_applied is False
    assert result.baseline_undemeaned is None
    assert result.disposition.indicator_class == "B"

    output = entrypoint_mod.build_pairwise_rows(result, 2001, country_map)
    assert output["is_demeaned"].all() == False  # noqa: E712 — explicit
    assert (output["is_demeaned"] == False).all()  # noqa: E712


# ---------------------------------------------------------------------------
# Test 10 — empty panel → no files written
# ---------------------------------------------------------------------------


def test_empty_panel_does_not_write_output(entrypoint_mod, populated_s3, dscdi_finder_mod):
    client, bucket = populated_s3
    # Minimum-2-country panel filtered out by min_obs (need ≥ 15 obs after diff,
    # so 30-year panel barely qualifies; trim to 4 years to force exclusion)
    panel = make_synthetic_panel(COUNTRIES_DEFAULT[:5], n_years=4)

    result = dscdi_finder_mod.run_dscdi_pass(
        indicator_id="v2x_libdem",
        panel=panel,
        audit_classification="I(1)",
        min_obs=15,
    )
    # All countries filtered out by min_obs → empty correlation matrix
    assert result.n_countries == 0

    country_map = {c: i for i, c in enumerate(COUNTRIES_DEFAULT[:5], 1)}
    output = entrypoint_mod.build_pairwise_rows(result, 1001, country_map)
    assert output.empty

    n_files = entrypoint_mod.write_pairwise_output(output, bucket, "empty-test", "v2x_libdem")
    assert n_files == 0
    listing = client.list_objects_v2(Bucket=bucket, Prefix="empty-test/")
    assert listing.get("KeyCount", 0) == 0


# ---------------------------------------------------------------------------
# Test 11 — manifest schema matches Glue dscdi_indicator_manifest
# ---------------------------------------------------------------------------


def test_manifest_schema_matches_glue_table(entrypoint_mod, populated_s3, dscdi_finder_mod):
    """Manifest Parquet has all 8 columns matching the Glue table schema."""
    client, bucket = populated_s3
    countries = COUNTRIES_DEFAULT[:6]
    panel = make_synthetic_panel(countries)

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    key = entrypoint_mod.write_manifest(result, bucket, "manifest/")

    obj = client.get_object(Bucket=bucket, Key=key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    expected_cols = {
        "indicator_id",
        "indicator_class",
        "transform",
        "n_countries",
        "mean_abs_pairwise_corr",
        "demeaning_applied",
        "demeaning_insufficient",
        "suppressed_reason",
    }
    assert set(df.columns) == expected_cols
    assert len(df) == 1


# ---------------------------------------------------------------------------
# Test 12 — manifest demeaning_insufficient flag propagates
# ---------------------------------------------------------------------------


def test_manifest_demeaning_insufficient_flag_propagates(entrypoint_mod, populated_s3, dscdi_finder_mod):
    """Build a panel where demeaning fails to reduce mean_abs below 0.25.

    Mirrors test_dscdi_finder.py::test_run_dscdi_pass_demeaning_insufficient_positive_path.
    """
    client, bucket = populated_s3
    rng = np.random.default_rng(7)
    n_years = 60
    countries = COUNTRIES_DEFAULT[:8]

    # Two orthogonal common factors → demeaning removes only one,
    # leaving residual cross-section structure.
    factor_a = np.linspace(0, 5, n_years)
    factor_b = np.cos(np.linspace(0, 6 * np.pi, n_years))
    data = {}
    for i, c in enumerate(countries):
        weight_a = 1.0 + 0.1 * i  # near-identical loadings on factor A (demeaning targets)
        weight_b = 0.8 + 0.5 * (i % 2)  # different loadings on factor B (residual)
        idiosyncratic = rng.normal(0, 0.05, n_years)
        data[c] = weight_a * factor_a + weight_b * factor_b + idiosyncratic
    panel = pd.DataFrame(data, index=pd.Index(range(1990, 1990 + n_years), name="year"))
    panel.columns.name = "country"  # match production-shaped pivot_table output

    result = dscdi_finder_mod.run_dscdi_pass(
        indicator_id="v2x_libdem",
        panel=panel,
        audit_classification="I(1)",
        min_obs=15,
    )

    key = entrypoint_mod.write_manifest(result, bucket, "manifest/")
    obj = client.get_object(Bucket=bucket, Key=key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    assert df.iloc[0]["demeaning_applied"] == result.demeaning_applied
    assert df.iloc[0]["demeaning_insufficient"] == result.demeaning_insufficient
    assert df.iloc[0]["mean_abs_pairwise_corr"] == pytest.approx(result.mean_abs_pairwise_corr, rel=1e-5)


# ---------------------------------------------------------------------------
# Test 13 — suppressed_reason='no_transform_outlier' for NY.GDP.MKTP.KD.ZG
# ---------------------------------------------------------------------------


def test_manifest_suppressed_reason_no_transform_outlier(entrypoint_mod, populated_s3, dscdi_finder_mod):
    """NY.GDP.MKTP.KD.ZG (Class A but I(0) growth rate) → demeaning suppressed.

    Per the qgi-infra PR-2b producer contract, the entrypoint MUST encode
    suppressed_reason='no_transform_outlier' for this indicator.
    """
    client, bucket = populated_s3
    countries = COUNTRIES_DEFAULT[:6]
    panel = make_synthetic_panel(countries)

    result = dscdi_finder_mod.run_dscdi_pass(
        indicator_id="NY.GDP.MKTP.KD.ZG",
        panel=panel,
        audit_classification="I(0)",
    )
    assert result.demeaning_applied is False
    assert result.disposition.indicator_class == "A"

    key = entrypoint_mod.write_manifest(result, bucket, "manifest/")
    obj = client.get_object(Bucket=bucket, Key=key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    assert df.iloc[0]["suppressed_reason"] == "no_transform_outlier"


def test_manifest_suppressed_reason_null_for_class_b(entrypoint_mod, populated_s3, dscdi_finder_mod):
    """Class B indicators have suppressed_reason=None (no demeaning expected)."""
    client, bucket = populated_s3
    panel = make_synthetic_panel(COUNTRIES_DEFAULT[:6])

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="RL.EST", panel=panel, audit_classification="I(0)")
    key = entrypoint_mod.write_manifest(result, bucket, "manifest/")
    obj = client.get_object(Bucket=bucket, Key=key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    assert df.iloc[0]["suppressed_reason"] is None or pd.isna(df.iloc[0]["suppressed_reason"])


def test_manifest_suppressed_reason_null_for_class_a_demeaned(entrypoint_mod, populated_s3, dscdi_finder_mod):
    """Class A indicators where demeaning WAS applied have suppressed_reason=None."""
    client, bucket = populated_s3
    panel = make_synthetic_panel(COUNTRIES_DEFAULT[:6])

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    assert result.demeaning_applied is True

    key = entrypoint_mod.write_manifest(result, bucket, "manifest/")
    obj = client.get_object(Bucket=bucket, Key=key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    assert df.iloc[0]["suppressed_reason"] is None or pd.isna(df.iloc[0]["suppressed_reason"])


# ---------------------------------------------------------------------------
# Test 14 — country label NaN guard (M-1 from plan v5)
# ---------------------------------------------------------------------------


def test_country_label_mapping_raises_on_unknown_country(entrypoint_mod, dscdi_finder_mod):
    """If a country in the panel isn't in countries_map, raise — don't silent-NaN."""
    countries = COUNTRIES_DEFAULT[:5]
    # countries_map missing the last country → should raise
    incomplete_map = {c: i for i, c in enumerate(countries[:4], 1)}
    panel = make_synthetic_panel(countries)

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")

    with pytest.raises(ValueError, match="not found in countries_map"):
        entrypoint_mod.build_pairwise_rows(result, 1001, incomplete_map)


# ---------------------------------------------------------------------------
# Test 15 — manifest n_countries dtype is bigint-compatible (int64)
# ---------------------------------------------------------------------------


def test_manifest_n_countries_is_int64(entrypoint_mod, populated_s3, dscdi_finder_mod):
    """n_countries Parquet dtype must be int64 to match Glue bigint column."""
    client, bucket = populated_s3
    panel = make_synthetic_panel(COUNTRIES_DEFAULT[:6])

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    key = entrypoint_mod.write_manifest(result, bucket, "manifest/")
    obj = client.get_object(Bucket=bucket, Key=key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    assert df["n_countries"].dtype == np.int64


# ---------------------------------------------------------------------------
# Test 16 — manifest mean_abs_pairwise_corr dtype is float64 (Glue double)
# ---------------------------------------------------------------------------


def test_manifest_mean_abs_pairwise_corr_is_float64(entrypoint_mod, populated_s3, dscdi_finder_mod):
    """mean_abs_pairwise_corr Parquet dtype must be float64 to match Glue double."""
    client, bucket = populated_s3
    panel = make_synthetic_panel(COUNTRIES_DEFAULT[:6])

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    key = entrypoint_mod.write_manifest(result, bucket, "manifest/")
    obj = client.get_object(Bucket=bucket, Key=key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    assert df["mean_abs_pairwise_corr"].dtype == np.float64


# ---------------------------------------------------------------------------
# Test 17 — writer-side indicator_class vocabulary assertion (#613 Flag 1)
# ---------------------------------------------------------------------------


def test_write_pairwise_output_rejects_invalid_indicator_class(entrypoint_mod, populated_s3, dscdi_finder_mod):
    """write_pairwise_output must raise ValueError when indicator_class
    contains values outside the {A, B, C} vocabulary.

    Glue/Hive Metastore doesn't support CHECK constraints natively, and
    the IndicatorClass Literal["A", "B", "C"] in dscdi_finder.py is a
    type-check-time guarantee only (Python doesn't enforce Literal at
    runtime). The runtime assertion in write_pairwise_output is the
    canonical enforcement point — without it, a future writer bug
    emitting 'a' / 'Class A' / '' / NaN would silently mis-filter
    downstream Athena queries like `WHERE indicator_class = 'A'`.
    """
    _, bucket = populated_s3
    panel = make_synthetic_panel(COUNTRIES_DEFAULT[:4])
    country_map = {c: i for i, c in enumerate(COUNTRIES_DEFAULT[:4], 1)}

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    output = entrypoint_mod.build_pairwise_rows(result, 1001, country_map)
    # Corrupt one row's indicator_class — simulate a future writer bug
    output.loc[0, "indicator_class"] = "a"  # lowercase variant

    with pytest.raises(ValueError, match="indicator_class"):
        entrypoint_mod.write_pairwise_output(output, bucket, "dscdis", "v2x_libdem")


def test_write_pairwise_output_rejects_multiple_invalid_indicator_classes(
    entrypoint_mod, populated_s3, dscdi_finder_mod
):
    """When several rows carry different invalid values, the error must
    list all of them sorted so the reporter sees the full vocabulary
    drift, not just the first one encountered."""
    _, bucket = populated_s3
    panel = make_synthetic_panel(COUNTRIES_DEFAULT[:5])
    country_map = {c: i for i, c in enumerate(COUNTRIES_DEFAULT[:5], 1)}

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    output = entrypoint_mod.build_pairwise_rows(result, 1001, country_map)
    output.loc[0, "indicator_class"] = "Class A"
    output.loc[1, "indicator_class"] = ""
    output.loc[2, "indicator_class"] = "a"

    with pytest.raises(ValueError) as exc_info:
        entrypoint_mod.write_pairwise_output(output, bucket, "dscdis", "v2x_libdem")
    msg = str(exc_info.value)
    # All three bad values should appear in the error
    assert "Class A" in msg
    assert "'a'" in msg or '"a"' in msg or " a" in msg  # tolerate repr formatting
    # indicator_id should be in the message for log triage
    assert "v2x_libdem" in msg


def test_write_pairwise_output_accepts_canonical_classes(entrypoint_mod, populated_s3, dscdi_finder_mod):
    """Sanity guard: the happy path (Class A demeaned + undemeaned rows)
    must not be broken by the new assertion."""
    client, bucket = populated_s3
    panel = make_synthetic_panel(COUNTRIES_DEFAULT[:4])
    country_map = {c: i for i, c in enumerate(COUNTRIES_DEFAULT[:4], 1)}

    result = dscdi_finder_mod.run_dscdi_pass(indicator_id="v2x_libdem", panel=panel, audit_classification="I(1)")
    output = entrypoint_mod.build_pairwise_rows(result, 1001, country_map)
    # Cover all three canonical classes — the writer might emit any
    # mix in production, so the assertion must accept the full vocabulary
    output.loc[0, "indicator_class"] = "A"
    output.loc[1, "indicator_class"] = "B"
    output.loc[2, "indicator_class"] = "C"

    n_files = entrypoint_mod.write_pairwise_output(output, bucket, "dscdis", "v2x_libdem")
    assert n_files >= 1
