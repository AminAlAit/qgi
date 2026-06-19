"""Curated Gold analytical models and PyArrow schemas for high-performance querying."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
import pyarrow as pa
from pydantic import BaseModel, Field, field_validator


# ─── PyArrow Schemas ──────────────────────────────────────────────────────────

GOLD_COUNTRY_RISK_SCHEMA = pa.schema(
    [
        ("iso3", pa.string()),
        ("country_name", pa.string()),
        ("score_date", pa.date32()),
        ("composite_risk_score", pa.float64()),
        ("salience_tier", pa.string()),
        ("global_rank", pa.int32()),
        ("structural_fragility_index", pa.float64()),
        ("conflict_intensity_index", pa.float64()),
        ("economic_pressure_index", pa.float64()),
        ("trajectory_momentum", pa.float64()),
        ("updated_at", pa.timestamp("us", tz="UTC")),
    ]
)

GOLD_EVENT_STREAM_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("event_date", pa.date32()),
        ("iso3", pa.string()),
        ("country_name", pa.string()),
        ("source", pa.string()),
        ("category", pa.string()),
        ("actor_primary", pa.string()),
        ("actor_secondary", pa.string()),
        ("latitude", pa.float64()),
        ("longitude", pa.float64()),
        ("fatalities", pa.int32()),
        ("tone", pa.float64()),
        ("title", pa.string()),
        ("summary", pa.string()),
        ("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

GOLD_MACRO_INDICATORS_SCHEMA = pa.schema(
    [
        ("iso3", pa.string()),
        ("country_name", pa.string()),
        ("year", pa.int32()),
        ("milex_pct_gdp", pa.float64()),
        ("milex_constant_usd", pa.float64()),
        ("gdp_growth_pct", pa.float64()),
        ("inflation_cpi_pct", pa.float64()),
        ("governance_stability_score", pa.float64()),
        ("rule_of_law_score", pa.float64()),
        ("updated_at", pa.timestamp("us", tz="UTC")),
    ]
)

GOLD_CONFLICT_TRAJECTORY_SCHEMA = pa.schema(
    [
        ("iso3", pa.string()),
        ("year", pa.int32()),
        ("conflict_state", pa.string()),
        ("fatalities_total", pa.int32()),
        ("state_based_conflicts", pa.int32()),
        ("non_state_conflicts", pa.int32()),
        ("one_sided_violence_events", pa.int32()),
        ("escalation_velocity", pa.float64()),
        ("updated_at", pa.timestamp("us", tz="UTC")),
    ]
)


# ─── Pydantic Analytical Models ───────────────────────────────────────────────


class GoldCountryRiskRecord(BaseModel):
    """Curated daily country intelligence risk scoring."""

    iso3: str = Field(..., min_length=3, max_length=3)
    country_name: str
    score_date: date
    composite_risk_score: float = Field(..., ge=0.0, le=100.0)
    salience_tier: str = Field(..., description="Regular High, Crisis High, Elevated, Moderate, Low")
    global_rank: int = Field(..., ge=1)
    structural_fragility_index: float
    conflict_intensity_index: float
    economic_pressure_index: float
    trajectory_momentum: float
    updated_at: datetime

    @field_validator("iso3")
    @classmethod
    def normalize_iso3(cls, v: str) -> str:
        return v.strip().upper()


class GoldEventStreamRecord(BaseModel):
    """Curated geospatial event record for interactive map and timeline visualization."""

    event_id: str
    event_date: date
    iso3: str = Field(..., min_length=3, max_length=3)
    country_name: str
    source: str
    category: str
    actor_primary: str
    actor_secondary: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    fatalities: int = Field(default=0, ge=0)
    tone: float = Field(default=0.0)
    title: str = ""
    summary: str = ""
    ingested_at: datetime


class GoldMacroIndicatorRecord(BaseModel):
    """Curated cross-sectional indicators combining SIPRI, World Bank, and institutional indices."""

    iso3: str = Field(..., min_length=3, max_length=3)
    country_name: str
    year: int = Field(..., ge=1900, le=2100)
    milex_pct_gdp: Optional[float] = None
    milex_constant_usd: Optional[float] = None
    gdp_growth_pct: Optional[float] = None
    inflation_cpi_pct: Optional[float] = None
    governance_stability_score: Optional[float] = None
    rule_of_law_score: Optional[float] = None
    updated_at: datetime


class GoldConflictTrajectoryRecord(BaseModel):
    """Curated conflict trajectory state-space model output."""

    iso3: str = Field(..., min_length=3, max_length=3)
    year: int = Field(..., ge=1900, le=2100)
    conflict_state: str
    fatalities_total: int = Field(default=0, ge=0)
    state_based_conflicts: int = Field(default=0, ge=0)
    non_state_conflicts: int = Field(default=0, ge=0)
    one_sided_violence_events: int = Field(default=0, ge=0)
    escalation_velocity: float = Field(default=0.0)
    updated_at: datetime
