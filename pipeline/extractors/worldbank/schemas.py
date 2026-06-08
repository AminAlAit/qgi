"""Pydantic schemas for World Bank World Development Indicators (WDI) and WGI extraction."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class WorldBankQueryConfig(BaseModel):
    """Parameters for World Bank API / bulk data extraction."""

    indicator_codes: List[str] = Field(
        default_factory=lambda: ["NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "MS.MIL.XPND.GD.ZS"],
        description="World Bank indicator series IDs",
    )
    country_codes: List[str] = Field(default_factory=list, description="ISO3 country filters (empty for all)")
    start_year: int = Field(default=1960, ge=1900, le=2100)
    end_year: int = Field(default=2026, ge=1900, le=2100)
    page_size: int = Field(default=1000, ge=10, le=10000)


class WorldBankIndicatorRecord(BaseModel):
    """Normalized World Bank metric observation for a given country-year."""

    iso3: str = Field(..., min_length=3, max_length=3)
    country_name: str
    indicator_code: str = Field(..., description="WDI/WGI Series ID")
    indicator_name: str
    year: int = Field(..., ge=1900, le=2100)
    value: Optional[float] = Field(default=None, description="Observed numeric value")
    unit: str = Field(default="", description="Measurement unit (e.g. %, USD, index)")
    source_organization: str = Field(default="World Bank Group")
    ingested_at: datetime

    @field_validator("iso3")
    @classmethod
    def normalize_iso3(cls, v: str) -> str:
        return v.strip().upper()
