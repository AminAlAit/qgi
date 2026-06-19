"""Gold Lakehouse Layer — Curated Analytical Models & PyArrow Schemas."""

from __future__ import annotations

from pipeline.lake.gold.schemas import (
    GOLD_CONFLICT_TRAJECTORY_SCHEMA,
    GOLD_COUNTRY_RISK_SCHEMA,
    GOLD_EVENT_STREAM_SCHEMA,
    GOLD_MACRO_INDICATORS_SCHEMA,
    GoldConflictTrajectoryRecord,
    GoldCountryRiskRecord,
    GoldEventStreamRecord,
    GoldMacroIndicatorRecord,
)

__all__ = [
    "GOLD_CONFLICT_TRAJECTORY_SCHEMA",
    "GOLD_COUNTRY_RISK_SCHEMA",
    "GOLD_EVENT_STREAM_SCHEMA",
    "GOLD_MACRO_INDICATORS_SCHEMA",
    "GoldConflictTrajectoryRecord",
    "GoldCountryRiskRecord",
    "GoldEventStreamRecord",
    "GoldMacroIndicatorRecord",
]
