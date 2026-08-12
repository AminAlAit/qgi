"""Tests for the V2.0 calibration training script (#463 Part B)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from calibrate_recipe_similarity import tier_for_length  # noqa: E402


class TestTierForLength:
    def test_short_tier(self):
        assert tier_for_length(3) == "S"
        assert tier_for_length(5) == "S"
        assert tier_for_length(8) == "S"

    def test_medium_tier(self):
        assert tier_for_length(9) == "M"
        assert tier_for_length(15) == "M"
        assert tier_for_length(20) == "M"

    def test_long_tier(self):
        assert tier_for_length(21) == "L"
        assert tier_for_length(35) == "L"
        assert tier_for_length(40) == "L"

    def test_xl_tier(self):
        assert tier_for_length(41) == "XL"
        assert tier_for_length(60) == "XL"
        assert tier_for_length(100) == "XL"

    def test_overlong_falls_in_xl(self):
        # No length is too long for XL — sentinel behavior.
        assert tier_for_length(9999) == "XL"
