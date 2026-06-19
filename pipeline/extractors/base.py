"""Base abstractions and Pydantic protocols for all QGI data source extractors."""

from __future__ import annotations

import abc
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field


class ExtractionMetadata(BaseModel):
    """Provenance and audit metadata for an extraction batch."""

    source_name: str = Field(..., description="Canonical source identifier (e.g. acled, sipri)")
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of extraction"
    )
    records_extracted: int = Field(default=0, ge=0, description="Total valid records parsed")
    records_failed: int = Field(default=0, ge=0, description="Total malformed records rejected")
    execution_id: Optional[str] = Field(default=None, description="Step Functions or Batch job execution ID")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Query/filter parameters utilized")


RecordT = TypeVar("RecordT", bound=BaseModel)
ConfigT = TypeVar("ConfigT", bound=BaseModel)


class ExtractorResult(BaseModel, Generic[RecordT]):
    """Standardized envelope returned by all extractor runs."""

    metadata: ExtractionMetadata
    records: List[RecordT] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class BaseExtractor(abc.ABC, Generic[ConfigT, RecordT]):
    """Abstract base class establishing the extractor contract."""

    def __init__(self, config: ConfigT) -> None:
        self.config = config

    @abc.abstractmethod
    def extract(self) -> ExtractorResult[RecordT]:
        """Execute data extraction from upstream provider or local cache."""
        raise NotImplementedError

    @abc.abstractmethod
    def validate_record(self, raw_data: Dict[str, Any]) -> Optional[RecordT]:
        """Validate and transform a single raw provider dict into the typed RecordT model."""
        raise NotImplementedError
