"""Pydantic schemas for SIPRI military expenditure and arms transfer data extraction."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SIPRIExtractorConfig(BaseModel):
    """Configuration for SIPRI dataset extraction and harmonization."""

    start_year: int = Field(default=1950, ge=1900, le=2100)
    end_year: int = Field(default=2026, ge=1900, le=2100)
    currency: str = Field(default="USD_CONSTANT", description="Currency unit: USD_CONSTANT or SHARE_GDP")
    excel_path: Optional[str] = Field(default=None, description="Local path or S3 key to SIPRI Milex Excel")


class SIPRIMilitaryExpenditureRecord(BaseModel):
    """Normalized SIPRI military expenditure record per country and year."""

    iso3: str = Field(..., min_length=3, max_length=3)
    country_name: str
    year: int = Field(..., ge=1900, le=2100)
    milex_constant_usd_mil: Optional[float] = Field(default=None, description="Expenditure in constant USD millions")
    milex_share_gdp_pct: Optional[float] = Field(default=None, description="Expenditure as percentage of GDP")
    milex_share_govt_spending_pct: Optional[float] = Field(
        default=None, description="Expenditure as % of general government expenditure"
    )
    milex_per_capita_usd: Optional[float] = Field(default=None, description="Expenditure per capita in current USD")
    data_quality_grade: str = Field(
        default="verified", description="SIPRI estimate confidence (e.g. verified, estimate, uncertain)"
    )
    ingested_at: datetime

    @field_validator("iso3")
    @classmethod
    def normalize_iso3(cls, v: str) -> str:
        return v.strip().upper()


class SIPRIArmsTransferRecord(BaseModel):
    """Normalized SIPRI trend-indicator values (TIV) arms transfer record."""

    supplier_iso3: str = Field(..., min_length=3, max_length=3)
    recipient_iso3: str = Field(..., min_length=3, max_length=3)
    year: int = Field(..., ge=1900, le=2100)
    weapon_category: str
    weapon_description: str
    tiv_delivered: float = Field(default=0.0, ge=0.0, description="SIPRI Trend-Indicator Value delivered")
    order_year: Optional[int] = None
    delivery_year: Optional[int] = None
    ingested_at: datetime
