"""Pydantic schemas for Uppsala Conflict Data Program (UCDP) dataset extraction."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class UCDPExtractorConfig(BaseModel):
    """Configuration for UCDP extraction from open bulk releases or API."""

    dataset_version: str = Field(default="25.1", description="UCDP release version tag (e.g. 25.1, 24.1)")
    dataset_types: List[str] = Field(
        default_factory=lambda: ["ged", "onesided", "acd", "onset"],
        description="Dataset families: ged (Georeferenced Event Dataset), onesided, acd (Armed Conflict), onset",
    )
    start_year: int = Field(default=1989, ge=1946, le=2100)
    end_year: int = Field(default=2026, ge=1946, le=2100)
    bulk_url_ged: Optional[str] = Field(default=None)


class UCDPGEDRecord(BaseModel):
    """Normalized UCDP Georeferenced Event Dataset record."""

    ged_id: str = Field(..., description="Unique UCDP GED event ID")
    year: int = Field(..., ge=1946, le=2100)
    type_of_violence: int = Field(..., ge=1, le=3, description="1=State-based, 2=Non-state, 3=One-sided")
    conflict_id: str
    conflict_name: str
    actor1: str
    actor2: str
    country_name: str
    iso3: str = Field(..., min_length=3, max_length=3)
    region: str = Field(default="")
    adm_1: str = Field(default="", description="First-order administrative division")
    date_start: date
    date_end: date
    deaths_best: int = Field(default=0, ge=0, description="Best fatality estimate")
    deaths_civilians: int = Field(default=0, ge=0, description="Civilian fatalities count")
    ingested_at: datetime

    @field_validator("iso3")
    @classmethod
    def normalize_iso3(cls, v: str) -> str:
        return v.strip().upper()


class UCDPConflictRecord(BaseModel):
    """Aggregated annual conflict summary per dyad/country."""

    conflict_id: str
    country_name: str
    iso3: str = Field(..., min_length=3, max_length=3)
    year: int = Field(..., ge=1946, le=2100)
    intensity_level: int = Field(
        ..., ge=1, le=2, description="1=Minor (25-999 battle deaths), 2=War (1000+ battle deaths)"
    )
    cumulative_intensity: int = Field(default=0)
    type_of_conflict: int = Field(
        ..., ge=1, le=4, description="1=Extrasystemic, 2=Interstate, 3=Internal, 4=Internationalized internal"
    )
    onset_binary: int = Field(default=0, ge=0, le=1)
    ingested_at: datetime
