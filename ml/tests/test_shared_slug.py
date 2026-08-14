"""Tests for qgi-ml/shared/slug.py — the canonical country_slug() function
consolidating what was previously duplicated across generate_pair_windows
and generate_frontend_data (#422 Bug 6).

These tests are the single-source-of-truth for slug semantics. If the
TypeScript version in qgi-frontend/lib/country-risks.ts ever adopts the
same canonical cases, a shared JSON fixture exported from these tests
would let both languages validate against the same expectations.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.slug import country_slug  # noqa: E402


class TestCountrySlug:

    def test_basic_lowercase(self):
        assert country_slug("France") == "france"

    def test_spaces_become_underscores(self):
        assert country_slug("United States") == "united_states"

    def test_apostrophe_as_separator(self):
        """Bug 4 behavior: apostrophes split tokens."""
        assert country_slug("Cote d'Ivoire") == "cote_d_ivoire"

    def test_period_as_separator(self):
        assert country_slug("U.S.A.") == "u_s_a"

    def test_comma_deleted(self):
        """Commas delete-only so 'Korea, South' stays one underscore."""
        assert country_slug("Korea, South") == "korea_south"

    def test_ampersand_becomes_and(self):
        assert country_slug("Bosnia & Herzegovina") == "bosnia_and_herzegovina"

    def test_none_returns_none(self):
        assert country_slug(None) is None

    def test_empty_returns_none(self):
        # Empty string is falsy → treated like None.
        assert country_slug("") is None

    def test_leading_trailing_underscores_stripped(self):
        result = country_slug("-Libya-")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_multi_space_collapses(self):
        assert "__" not in country_slug("Democratic  Republic")

    def test_non_ascii_as_separator(self):
        """Non-ASCII chars outside [a-z0-9] become underscores."""
        assert country_slug("Côte") == "c_te"

    def test_real_curated_files_round_trip(self):
        """Verify the canonical curated-file names slug to themselves."""
        # These are the exact file names in qgi-data/events/curated/.
        # The slug function must produce the same string so lookups work.
        assert country_slug("china") == "china"
        assert country_slug("north_korea") == "north_korea"
        assert country_slug("South Korea") == "south_korea"
        assert country_slug("Sao Tome and Principe") == "sao_tome_and_principe"


# ─── Regression guard — delegation from pair_windows ──────────────────────

class TestPairWindowsDelegation:
    """Ensure generate_pair_windows._slug still returns identical results
    to the shared implementation. If someone reverts the delegation, these
    catch it."""

    def test_pair_windows_slug_matches_shared(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import generate_pair_windows as gpw
        test_cases = [
            "France", "United States", "Cote d'Ivoire", "U.S.A.",
            "Korea, South", "Bosnia & Herzegovina", None, "",
            "-Libya-", "Democratic  Republic", "Côte",
        ]
        for case in test_cases:
            assert gpw._slug(case) == country_slug(case), (
                f"Drift detected for input {case!r}: "
                f"pair_windows._slug={gpw._slug(case)!r} vs "
                f"shared.country_slug={country_slug(case)!r}"
            )
