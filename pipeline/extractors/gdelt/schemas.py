"""Pydantic schemas for GDELT 2.0 Event and Global Knowledge Graph (GKG) extraction."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class GDELTQueryConfig(BaseModel):
    """Parameters for GDELT event stream queries."""

    target_date: Optional[date] = Field(default=None, description="Date of GDELT event feed (YYYY-MM-DD)")
    quad_classes: List[int] = Field(
        default_factory=lambda: [1, 2, 3, 4],
        description="CAMEO QuadClass filters: 1=Verbal Coop, 2=Material Coop, 3=Verbal Conflict, 4=Material Conflict",
    )
    min_goldstein: Optional[float] = Field(default=-10.0, ge=-10.0, le=10.0)
    max_goldstein: Optional[float] = Field(default=10.0, ge=-10.0, le=10.0)
    country_filter: List[str] = Field(default_factory=list, description="FIPS/ISO country codes")


class GDELTEventRecord(BaseModel):
    """Normalized GDELT 2.0 event record."""

    global_event_id: str = Field(..., description="Unique GDELT GlobalEventID")
    day: int = Field(..., description="Date integer YYYYMMDD")
    actor1_code: str = Field(default="", description="CAMEO Actor1 code")
    actor1_name: str = Field(default="", description="Actor1 entity label")
    actor1_country_code: str = Field(default="", description="Actor1 3-char code")
    actor2_code: str = Field(default="", description="CAMEO Actor2 code")
    actor2_name: str = Field(default="", description="Actor2 entity label")
    actor2_country_code: str = Field(default="", description="Actor2 3-char code")
    event_code: str = Field(..., description="CAMEO EventCode root or sub-code")
    event_base_code: str = Field(default="")
    quad_class: int = Field(
        ..., ge=1, le=4, description="1=Verbal Coop, 2=Material Coop, 3=Verbal Conf, 4=Material Conf"
    )
    goldstein_scale: float = Field(..., ge=-10.0, le=10.0, description="Goldstein conflict-cooperation score")
    num_mentions: int = Field(default=1, ge=1)
    num_sources: int = Field(default=1, ge=1)
    num_articles: int = Field(default=1, ge=1)
    avg_tone: float = Field(default=0.0, description="Average document tone (-100 to +100)")
    actor1_geo_country_code: str = Field(default="", description="FIPS country code for actor1 location")
    actor2_geo_country_code: str = Field(default="", description="FIPS country code for actor2 location")
    action_geo_country_code: str = Field(default="", description="FIPS country code for event action")
    source_url: str = Field(default="")
    ingested_at: datetime


class GDELTGKGRecord(BaseModel):
    """Normalized GDELT Global Knowledge Graph tone and theme record."""

    gkg_record_id: str
    date: datetime
    source_name: str
    document_identifier: str
    themes: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    tone: float = Field(default=0.0)
    positive_score: float = Field(default=0.0)
    negative_score: float = Field(default=0.0)
    polarity: float = Field(default=0.0)
    ingested_at: datetime
