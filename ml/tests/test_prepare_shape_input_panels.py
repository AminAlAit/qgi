"""Tests for scripts/prepare_shape_input_panels.py (Chunk C.1).

Authority: Stage 6 pre-reg §3.2 (end-alignment + indicator-level normalization)
+ §3.2.2 (BASELINE_TOO_SHORT rule).

Test inventory:
  1. Synthetic events + synthetic panels → expected aligned + normalized output.
  2. BASELINE_TOO_SHORT correctly drops a country with < 20 pre-window years.
  3. End-alignment correctly excludes the event year (t=0 NOT included).
  4. z-score normalization recovers expected values on a known panel.
  5. sigma_min floor fires on near-constant series.
  6. Idempotent on re-run (same output bytes).
  7. Determinism: same inputs → same output parquet hash.
"""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

import sys

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO / "scripts"))

from prepare_shape_input_panels import (
    BASELINE_YEARS,
    SIGMA_MIN_MULTIPLIER,
    _check_baseline_too_short,
    _compute_sigma_min,
    _normalize_trajectory,
    _panel_country_to_id,
    prepare_recipe,
)

# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

T_R_FIXTURE = 5  # canonical length for all fixture tests
INDICATOR_A = "IND_A"
INDICATOR_B = "IND_B"

# Countries in the fixture:
#   "alpha"  — has 20 good pre-window years + T_r window years: survives
#   "bravo"  — has only 10 pre-window years on IND_A: BASELINE_TOO_SHORT
#   "charlie" — has 20 good pre-window years + T_r window years: survives

# Event year used throughout.
EVENT_YEAR = 2000


def _make_indicator_rows(
    country_id: str,
    indicator_id: str,
    year_start: int,
    year_end: int,
    base_value: float = 1.0,
    noise_scale: float = 0.1,
    seed: int = 0,
) -> pd.DataFrame:
    """Return long-format rows for one (country, indicator) series."""
    rng = np.random.default_rng(seed)
    years = list(range(year_start, year_end + 1))
    values = base_value + rng.normal(0, noise_scale, size=len(years))
    return pd.DataFrame(
        {
            "country_id": country_id,
            "year": years,
            "indicator_id": indicator_id,
            "value": values,
        }
    )


def _make_synthetic_panel(
    countries: list[str],
    indicators: list[str],
    event_year: int = EVENT_YEAR,
    T_r: int = T_R_FIXTURE,
    *,
    short_baseline_country: str | None = None,
    short_baseline_indicator: str | None = None,
) -> pd.DataFrame:
    """Build a synthetic long-format panel for fixture tests.

    ``short_baseline_country`` / ``short_baseline_indicator`` specifies a
    (country, indicator) pair that intentionally has < BASELINE_YEARS observations
    in the pre-window (triggers BASELINE_TOO_SHORT).
    """
    frames: list[pd.DataFrame] = []
    baseline_start_full = event_year - T_r - BASELINE_YEARS
    window_end = event_year - 1  # event year EXCLUDED

    for country_id in countries:
        for indicator_id in indicators:
            is_short = (
                country_id == short_baseline_country
                and indicator_id == short_baseline_indicator
            )
            if is_short:
                # Only 10 years of pre-window baseline (< 20 required).
                start = event_year - T_r - 10  # only 10 baseline years
            else:
                start = baseline_start_full
            frames.append(
                _make_indicator_rows(
                    country_id,
                    indicator_id,
                    year_start=start,
                    year_end=window_end,
                    seed=hash((country_id, indicator_id)) % (2**31),
                )
            )

    panel = pd.concat(frames, ignore_index=True)
    panel["year"] = panel["year"].astype(int)
    return panel


def _make_synthetic_events_dir(
    tmp_path: Path,
    pairs: list[tuple[str, int]],
    recipe_id: str,
) -> Path:
    """Write synthetic curated event JSON files to a temp directory."""
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    by_country: dict[str, list[dict]] = {}
    for country_id, year in pairs:
        by_country.setdefault(country_id, []).append(
            {
                "year": year,
                "title": f"Synthetic event {year}",
                "description": "Fixture event",
                "category": recipe_id,
                "verified": True,
                "verification_source": None,
            }
        )
    for country_id, evs in by_country.items():
        (events_dir / f"{country_id}.json").write_text(
            json.dumps(evs), encoding="utf-8"
        )
    return events_dir


def _make_synthetic_audit(
    tmp_path: Path,
    recipe_id: str,
    key_indicators: list[str],
    canonical_length_T: int = T_R_FIXTURE,
) -> Path:
    """Write a minimal substrate-audit JSON for the recipe."""
    audit = {
        "recipes": {
            recipe_id: {
                "key_indicators": key_indicators,
                "canonical_length_T": canonical_length_T,
            }
        }
    }
    audit_path = tmp_path / "substrate-audit-phase-1.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    return audit_path


# ---------------------------------------------------------------------------
# Monkey-patch helpers (replace module-level paths with fixture paths)
# ---------------------------------------------------------------------------


def _make_env(
    tmp_path: Path,
    *,
    recipe_id: str = "test_recipe",
    country_pairs: list[tuple[str, int]] | None = None,
    indicators: list[str] | None = None,
    short_baseline: tuple[str, str] | None = None,
) -> tuple[Path, Path, Path, pd.DataFrame]:
    """Return (events_dir, audit_path, output_dir, panel_df) for a fixture."""
    if country_pairs is None:
        country_pairs = [("alpha", EVENT_YEAR), ("charlie", EVENT_YEAR)]
    if indicators is None:
        indicators = [INDICATOR_A]
    countries = sorted({c for c, _ in country_pairs})
    panel = _make_synthetic_panel(
        countries,
        indicators,
        event_year=EVENT_YEAR,
        T_r=T_R_FIXTURE,
        short_baseline_country=short_baseline[0] if short_baseline else None,
        short_baseline_indicator=short_baseline[1] if short_baseline else None,
    )
    events_dir = _make_synthetic_events_dir(tmp_path, country_pairs, recipe_id)
    audit_path = _make_synthetic_audit(tmp_path, recipe_id, indicators)
    output_dir = tmp_path / "shape_inputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    return events_dir, audit_path, output_dir, panel


# ---------------------------------------------------------------------------
# Test 1 — Basic happy path: synthetic events + panel → expected output
# ---------------------------------------------------------------------------


def test_basic_happy_path(tmp_path, monkeypatch):
    """Synthetic events + panel → positives_aligned.parquet is non-empty
    with correct schema and all t_offset values in {-T_r, ..., -1}."""
    recipe_id = "test_recipe"
    country_pairs = [("alpha", EVENT_YEAR), ("charlie", EVENT_YEAR + 5)]
    indicators = [INDICATOR_A, INDICATOR_B]
    events_dir, audit_path, output_dir, panel = _make_env(
        tmp_path,
        recipe_id=recipe_id,
        country_pairs=country_pairs,
        indicators=indicators,
    )

    import prepare_shape_input_panels as prep

    monkeypatch.setattr(prep, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(prep, "SUBSTRATE_AUDIT_PATH", audit_path)

    result = prepare_recipe(
        recipe_id,
        output_dir=output_dir,
        canonical_length_T=T_R_FIXTURE,
        key_indicators_path=audit_path,
        panel=panel,
    )

    assert result["n_pos_input"] == 2
    assert result["n_pos_kept"] > 0

    aligned_path = output_dir / recipe_id / "positives_aligned.parquet"
    assert aligned_path.exists()
    df = pd.read_parquet(aligned_path)

    # Schema check.
    for col in ["country_id", "instance_idx", "indicator_id", "t_offset", "y_normalized"]:
        assert col in df.columns, f"Missing column: {col}"

    # t_offset must only contain values in {-T_r, ..., -1}.
    expected_offsets = set(range(-T_R_FIXTURE, 0))
    actual_offsets = set(df["t_offset"].unique())
    assert actual_offsets <= expected_offsets, (
        f"Unexpected t_offset values: {actual_offsets - expected_offsets}"
    )

    # Each instance_idx has exactly T_r rows per indicator.
    for (idx, iid), grp in df.groupby(["instance_idx", "indicator_id"]):
        assert len(grp) == T_R_FIXTURE, (
            f"instance_idx={idx}, indicator={iid}: expected {T_R_FIXTURE} rows, got {len(grp)}"
        )


# ---------------------------------------------------------------------------
# Test 2 — BASELINE_TOO_SHORT drops the short-baseline country
# ---------------------------------------------------------------------------


def test_baseline_too_short_drops_country(tmp_path, monkeypatch):
    """Country 'bravo' has < 20 pre-window years on IND_A → dropped with
    BASELINE_TOO_SHORT; country 'alpha' (full baseline) survives."""
    recipe_id = "test_recipe"
    country_pairs = [("alpha", EVENT_YEAR), ("bravo", EVENT_YEAR)]
    events_dir, audit_path, output_dir, panel = _make_env(
        tmp_path,
        recipe_id=recipe_id,
        country_pairs=country_pairs,
        indicators=[INDICATOR_A],
        short_baseline=("bravo", INDICATOR_A),
    )

    import prepare_shape_input_panels as prep

    monkeypatch.setattr(prep, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(prep, "SUBSTRATE_AUDIT_PATH", audit_path)

    result = prepare_recipe(
        recipe_id,
        output_dir=output_dir,
        canonical_length_T=T_R_FIXTURE,
        key_indicators_path=audit_path,
        panel=panel,
    )

    assert result["n_baseline_too_short"] >= 1, (
        "Expected at least one BASELINE_TOO_SHORT dropout"
    )
    # 'alpha' should survive.
    aligned_df = pd.read_parquet(output_dir / recipe_id / "positives_aligned.parquet")
    surviving_countries = set(aligned_df["country_id"].unique())
    assert "bravo" not in surviving_countries, "'bravo' should have been dropped"
    assert "alpha" in surviving_countries, "'alpha' should survive"

    # Manifest check.
    manifest = json.loads((output_dir / recipe_id / "prep_manifest.json").read_text())
    assert manifest["counts"]["n_baseline_too_short"] >= 1


# ---------------------------------------------------------------------------
# Test 3 — End-alignment correctly excludes the event year
# ---------------------------------------------------------------------------


def test_end_alignment_excludes_event_year(tmp_path, monkeypatch):
    """t_offset == 0 (event year itself) must NOT appear in the output.

    §3.2.1: trajectory window is t in {-T_r, ..., -1}; event year excluded.
    """
    recipe_id = "test_recipe"
    country_pairs = [("alpha", EVENT_YEAR)]
    events_dir, audit_path, output_dir, panel = _make_env(
        tmp_path,
        recipe_id=recipe_id,
        country_pairs=country_pairs,
        indicators=[INDICATOR_A],
    )

    import prepare_shape_input_panels as prep

    monkeypatch.setattr(prep, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(prep, "SUBSTRATE_AUDIT_PATH", audit_path)

    prepare_recipe(
        recipe_id,
        output_dir=output_dir,
        canonical_length_T=T_R_FIXTURE,
        key_indicators_path=audit_path,
        panel=panel,
    )

    df = pd.read_parquet(output_dir / recipe_id / "positives_aligned.parquet")
    assert 0 not in df["t_offset"].values, (
        "t_offset=0 (event year) found in aligned output — §3.2.1 violation"
    )
    assert df["t_offset"].max() == -1, (
        f"Max t_offset should be -1, got {df['t_offset'].max()}"
    )
    assert df["t_offset"].min() == -T_R_FIXTURE, (
        f"Min t_offset should be -{T_R_FIXTURE}, got {df['t_offset'].min()}"
    )


# ---------------------------------------------------------------------------
# Test 4 — z-score normalization recovers expected values
# ---------------------------------------------------------------------------


def test_zscore_normalization_known_panel(tmp_path, monkeypatch):
    """Build a panel where mu_c and sigma_c are exactly known, then verify
    that y_normalized == (x - mu_c) / sigma_c for the alignment window."""
    recipe_id = "test_recipe"
    event_year = 2000
    T_r = T_R_FIXTURE

    # Build a deterministic panel for country "exact".
    # Baseline years: [event_year - T_r - 20, event_year - T_r - 1]
    # = [1975, 1994]  (20 years).
    # Alignment window: [event_year - T_r, event_year - 1] = [1995, 1999].
    baseline_values = np.arange(1.0, 21.0, dtype=float)  # 1..20, mu=10.5, sd known
    align_values = np.array([50.0, 60.0, 70.0, 80.0, 90.0], dtype=float)  # 5 years

    baseline_start = event_year - T_r - BASELINE_YEARS  # 1975
    baseline_end = event_year - T_r - 1  # 1994
    align_start = event_year - T_r  # 1995
    align_end = event_year - 1  # 1999

    all_years = list(range(baseline_start, event_year))  # 1975..1999
    all_values = np.concatenate([baseline_values, align_values])

    panel_df = pd.DataFrame(
        {
            "country_id": "exact",
            "year": all_years,
            "indicator_id": INDICATOR_A,
            "value": all_values,
        }
    )

    mu_c = float(np.mean(baseline_values))
    sigma_c = float(np.std(baseline_values, ddof=1))
    # sigma_min = 1e-3 * median([sigma_c]) = 1e-3 * sigma_c (one country)
    sigma_min = SIGMA_MIN_MULTIPLIER * sigma_c  # smaller than sigma_c -> not binding

    expected_y = (align_values - mu_c) / max(sigma_c, sigma_min)

    events_dir = _make_synthetic_events_dir(
        tmp_path, [("exact", event_year)], recipe_id
    )
    audit_path = _make_synthetic_audit(
        tmp_path, recipe_id, [INDICATOR_A], canonical_length_T=T_r
    )
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)

    import prepare_shape_input_panels as prep

    monkeypatch.setattr(prep, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(prep, "SUBSTRATE_AUDIT_PATH", audit_path)

    prepare_recipe(
        recipe_id,
        output_dir=output_dir,
        canonical_length_T=T_r,
        key_indicators_path=audit_path,
        panel=panel_df,
    )

    df = pd.read_parquet(output_dir / recipe_id / "positives_aligned.parquet")
    assert not df.empty
    # Extract alignment trajectory for the only instance.
    traj = df.sort_values("t_offset")["y_normalized"].values
    np.testing.assert_allclose(
        traj, expected_y, rtol=1e-5,
        err_msg="y_normalized does not match (x - mu_c) / sigma_c"
    )


# ---------------------------------------------------------------------------
# Test 5 — sigma_min floor fires on near-constant series
# ---------------------------------------------------------------------------


def test_sigma_min_floor_on_near_constant_series(tmp_path, monkeypatch):
    """When the baseline is near-constant (sigma_c ~ 0), sigma_min prevents
    division by zero and the normalized values are finite (not inf/nan)."""
    recipe_id = "test_recipe"
    event_year = 2000
    T_r = T_R_FIXTURE

    # Near-constant baseline: all values identical → sigma_c = 0.
    const_val = 42.0
    baseline_years = list(range(event_year - T_r - BASELINE_YEARS, event_year - T_r))
    align_years = list(range(event_year - T_r, event_year))
    all_years = baseline_years + align_years

    # Baseline: constant. Alignment: small variation.
    baseline_vals = np.full(len(baseline_years), const_val)
    align_vals = np.array([42.1, 42.2, 42.3, 42.4, 42.5])
    all_vals = np.concatenate([baseline_vals, align_vals])

    panel_df = pd.DataFrame(
        {
            "country_id": "constant_country",
            "year": all_years,
            "indicator_id": INDICATOR_A,
            "value": all_vals,
        }
    )

    events_dir = _make_synthetic_events_dir(
        tmp_path, [("constant_country", event_year)], recipe_id
    )
    audit_path = _make_synthetic_audit(
        tmp_path, recipe_id, [INDICATOR_A], canonical_length_T=T_r
    )
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)

    import prepare_shape_input_panels as prep

    monkeypatch.setattr(prep, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(prep, "SUBSTRATE_AUDIT_PATH", audit_path)

    prepare_recipe(
        recipe_id,
        output_dir=output_dir,
        canonical_length_T=T_r,
        key_indicators_path=audit_path,
        panel=panel_df,
    )

    df = pd.read_parquet(output_dir / recipe_id / "positives_aligned.parquet")
    assert not df.empty, "Near-constant series should still produce output"
    y_vals = df["y_normalized"].dropna().values
    assert np.all(np.isfinite(y_vals)), (
        f"sigma_min floor failed: y_normalized contains non-finite values: {y_vals}"
    )


# ---------------------------------------------------------------------------
# Test 6 — Idempotency: re-running produces same output bytes
# ---------------------------------------------------------------------------


def test_idempotent_rerun(tmp_path, monkeypatch):
    """Running prepare_recipe twice on the same inputs produces bitwise-identical
    parquet output (same SHA-256 hash)."""
    recipe_id = "test_recipe"
    country_pairs = [("alpha", EVENT_YEAR), ("charlie", EVENT_YEAR + 3)]
    events_dir, audit_path, output_dir, panel = _make_env(
        tmp_path,
        recipe_id=recipe_id,
        country_pairs=country_pairs,
        indicators=[INDICATOR_A],
    )

    import prepare_shape_input_panels as prep

    monkeypatch.setattr(prep, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(prep, "SUBSTRATE_AUDIT_PATH", audit_path)

    def _run():
        prepare_recipe(
            recipe_id,
            output_dir=output_dir,
            canonical_length_T=T_R_FIXTURE,
            key_indicators_path=audit_path,
            panel=panel.copy(),  # fresh copy each time
        )
        aligned_path = output_dir / recipe_id / "positives_aligned.parquet"
        return hashlib.sha256(aligned_path.read_bytes()).hexdigest()

    hash1 = _run()
    hash2 = _run()

    assert hash1 == hash2, (
        f"Idempotency check failed: hash1={hash1}, hash2={hash2}"
    )


# ---------------------------------------------------------------------------
# Test 7 — Determinism: same inputs → same output parquet hash
# ---------------------------------------------------------------------------


def test_determinism_same_inputs_same_hash(tmp_path, monkeypatch):
    """Two separate output directories with identical inputs produce the same
    positives_aligned.parquet content (ignoring file-system metadata)."""
    recipe_id = "test_recipe"
    country_pairs = [("alpha", EVENT_YEAR)]

    events_dir, audit_path, _, panel = _make_env(
        tmp_path,
        recipe_id=recipe_id,
        country_pairs=country_pairs,
        indicators=[INDICATOR_A, INDICATOR_B],
    )

    import prepare_shape_input_panels as prep

    monkeypatch.setattr(prep, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(prep, "SUBSTRATE_AUDIT_PATH", audit_path)

    def _run_to_dir(suffix: str) -> str:
        out = tmp_path / f"out_{suffix}"
        out.mkdir(parents=True, exist_ok=True)
        prepare_recipe(
            recipe_id,
            output_dir=out,
            canonical_length_T=T_R_FIXTURE,
            key_indicators_path=audit_path,
            panel=panel.copy(),
        )
        p = out / recipe_id / "positives_aligned.parquet"
        # Read back as DataFrame and hash its canonical bytes.
        df = pd.read_parquet(p).sort_values(
            ["country_id", "instance_idx", "indicator_id", "t_offset"]
        ).reset_index(drop=True)
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return hashlib.sha256(buf.getvalue()).hexdigest()

    hash_a = _run_to_dir("A")
    hash_b = _run_to_dir("B")
    assert hash_a == hash_b, (
        f"Determinism check failed: hash_A={hash_a}, hash_B={hash_b}"
    )


# ---------------------------------------------------------------------------
# Unit tests for internal helpers (not depending on file I/O)
# ---------------------------------------------------------------------------


def test_normalize_trajectory_basic():
    """_normalize_trajectory returns (x - mu) / sigma when sigma > sigma_min."""
    x = np.array([3.0, 5.0, 7.0])
    mu = 2.0
    sigma = 1.0
    sigma_min = 0.001  # << sigma, not binding
    result = _normalize_trajectory(x, mu, sigma, sigma_min)
    expected = (x - mu) / sigma
    np.testing.assert_allclose(result, expected)


def test_normalize_trajectory_sigma_min_floor():
    """_normalize_trajectory uses sigma_min when sigma_c < sigma_min."""
    x = np.array([1.0, 1.0001, 0.9999])
    mu = 1.0
    sigma_c = 0.0  # exactly zero
    sigma_min = 0.5  # > sigma_c
    result = _normalize_trajectory(x, mu, sigma_c, sigma_min)
    expected = (x - mu) / sigma_min
    np.testing.assert_allclose(result, expected)


def test_compute_sigma_min_empty():
    """_compute_sigma_min on an empty list returns a small positive value."""
    val = _compute_sigma_min([])
    assert val > 0
    assert val == pytest.approx(SIGMA_MIN_MULTIPLIER)


def test_compute_sigma_min_known():
    """_compute_sigma_min([2.0, 4.0]) = 1e-3 * median([2.0, 4.0]) = 1e-3 * 3.0."""
    val = _compute_sigma_min([2.0, 4.0])
    assert val == pytest.approx(SIGMA_MIN_MULTIPLIER * 3.0)


def test_check_baseline_too_short_pass():
    """_check_baseline_too_short returns None when all indicators have >= 20 years."""
    event_year = 2000
    T_r = 5
    indicators = ["IND_X"]
    country_id = "country_ok"

    baseline_start = event_year - T_r - BASELINE_YEARS  # 1975
    baseline_end = event_year - T_r - 1  # 1994

    rows = pd.DataFrame(
        {
            "country_id": country_id,
            "year": list(range(baseline_start, event_year)),
            "indicator_id": "IND_X",
            "value": 1.0,
        }
    )
    indexed = rows.set_index(["country_id", "year", "indicator_id"])
    result = _check_baseline_too_short(indexed, country_id, event_year, T_r, indicators)
    assert result is None


def test_check_baseline_too_short_fail():
    """_check_baseline_too_short returns the dropout string when < 20 baseline years."""
    event_year = 2000
    T_r = 5
    indicators = ["IND_X"]
    country_id = "country_short"

    # Only 10 baseline years.
    baseline_start = event_year - T_r - 10  # 1985
    rows = pd.DataFrame(
        {
            "country_id": country_id,
            "year": list(range(baseline_start, event_year)),
            "indicator_id": "IND_X",
            "value": 1.0,
        }
    )
    indexed = rows.set_index(["country_id", "year", "indicator_id"])
    result = _check_baseline_too_short(indexed, country_id, event_year, T_r, indicators)
    assert result is not None
    assert "BASELINE_TOO_SHORT" in result


def test_panel_country_to_id_normalization():
    """_panel_country_to_id correctly maps known WB country name variants."""
    assert _panel_country_to_id("Turkiye") == "turkiye"
    assert _panel_country_to_id("Cabo Verde") == "cabo_verde"
    # Direct slugification for a normal country.
    assert _panel_country_to_id("Afghanistan") == "afghanistan"
    assert _panel_country_to_id("Bosnia and Herzegovina") == "bosnia_and_herzegovina"
