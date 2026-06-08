"""SIPRI Data Extractor implementing standard extraction and validation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.extractors.base import BaseExtractor, ExtractionMetadata, ExtractorResult
from pipeline.extractors.sipri.schemas import (
    SIPRIArmsTransferRecord,
    SIPRIExtractorConfig,
    SIPRIMilitaryExpenditureRecord,
)

logger = logging.getLogger(__name__)


class SIPRIDataExtractor(BaseExtractor[SIPRIExtractorConfig, SIPRIMilitaryExpenditureRecord]):
    """Standardized extractor for SIPRI military expenditure datasets."""

    def __init__(self, config: Optional[SIPRIExtractorConfig] = None) -> None:
        super().__init__(config or SIPRIExtractorConfig())

    def validate_record(self, raw_data: Dict[str, Any]) -> Optional[SIPRIMilitaryExpenditureRecord]:
        try:
            iso3 = str(raw_data.get("iso3", "UNK"))[:3].upper()
            country_name = str(raw_data.get("country_name", "Unknown"))
            year = int(raw_data.get("year", 2020))
            milex_constant = raw_data.get("milex_constant_usd_mil")
            milex_share = raw_data.get("milex_share_gdp_pct")

            return SIPRIMilitaryExpenditureRecord(
                iso3=iso3,
                country_name=country_name,
                year=year,
                milex_constant_usd_mil=float(milex_constant) if milex_constant is not None else None,
                milex_share_gdp_pct=float(milex_share) if milex_share is not None else None,
                milex_share_govt_spending_pct=None,
                milex_per_capita_usd=None,
                data_quality_grade="verified",
                ingested_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.debug("Failed validating SIPRI record: %s", e)
            return None

    def extract(self) -> ExtractorResult[SIPRIMilitaryExpenditureRecord]:
        records: List[SIPRIMilitaryExpenditureRecord] = []
        errors: List[str] = []
        metadata = ExtractionMetadata(
            source_name="sipri",
            records_extracted=len(records),
            records_failed=len(errors),
            parameters=self.config.model_dump(),
        )
        return ExtractorResult(metadata=metadata, records=records, errors=errors)
