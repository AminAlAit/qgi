"""Pydantic schemas for ACLED armed conflict event data extraction."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ACLEDQueryConfig(BaseModel):
    """Parameters for ACLED extraction API request or bulk ingest."""

    start_date: Optional[date] = Field(default=None, description="Start date filter")
    end_date: Optional[date] = Field(default=None, description="End date filter")
    iso_codes: List[str] = Field(default_factory=list, description="ISO3 country codes to filter")
    limit: int = Field(default=5000, ge=1, le=50000, description="Page limit for pagination")
    api_key: Optional[str] = Field(default=None, description="ACLED API key (optional/injected via env)")
    email: Optional[str] = Field(default=None, description="ACLED registered email (optional/injected via env)")


class ACLEDEventInput(BaseModel):
    """Raw input payload representation from ACLED API/CSV."""

    data_id: str = Field(..., description="Unique event identifier from ACLED")
    event_date: str = Field(..., description="Raw date string")
    year: int = Field(..., ge=1900, le=2100)
    event_type: str = Field(..., description="Category: Battles, Violence against civilians, etc.")
    sub_event_type: Optional[str] = Field(default=None)
    actor1: str = Field(..., description="Primary actor name")
    actor2: Optional[str] = Field(default=None, description="Secondary actor name")
    country: str = Field(..., description="Country name")
    iso: Optional[str] = Field(default=None, description="ISO numeric or ISO3 code")
    region: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)
    fatalities: int = Field(default=0, ge=0)
    notes: Optional[str] = Field(default=None)


class ACLEDEventRecord(BaseModel):
    """Cleaned, validated, and normalized ACLED event record for Bronze/Silver storage."""

    event_id: str
    event_date: date
    year: int
    event_type: str
    sub_event_type: str
    actor1: str
    actor2: str
    country_name: str
    iso3: str = Field(..., min_length=3, max_length=3, description="Canonical ISO 3166-1 alpha-3 code")
    region: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    fatalities: int = Field(ge=0)
    notes: str = ""
    ingested_at: datetime

    @field_validator("iso3")
    @classmethod
    def normalize_iso3(cls, v: str) -> str:
        return v.strip().upper()
