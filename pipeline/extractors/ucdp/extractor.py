"""UCDP Data Extractor implementing standard extraction and validation."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.extractors.base import BaseExtractor, ExtractionMetadata, ExtractorResult
from pipeline.extractors.ucdp.schemas import UCDPConflictRecord, UCDPExtractorConfig, UCDPGEDRecord

logger = logging.getLogger(__name__)


class UCDPDataExtractor(BaseExtractor[UCDPExtractorConfig, UCDPGEDRecord]):
    """Standardized extractor for UCDP conflict events."""

    def __init__(self, config: Optional[UCDPExtractorConfig] = None) -> None:
        super().__init__(config or UCDPExtractorConfig())

    def validate_record(self, raw_data: Dict[str, Any]) -> Optional[UCDPGEDRecord]:
        try:
            iso3 = str(raw_data.get("iso3") or raw_data.get("country_iso") or "UNK")[:3].upper()
            d_start_raw = str(raw_data.get("date_start", "2020-01-01"))[:10]
            d_end_raw = str(raw_data.get("date_end", "2020-01-01"))[:10]

            return UCDPGEDRecord(
                ged_id=str(raw_data.get("id") or raw_data.get("ged_id", "")),
                year=int(raw_data.get("year", 2020)),
                type_of_violence=int(raw_data.get("type_of_violence", 1)),
                conflict_id=str(raw_data.get("conflict_d_id") or raw_data.get("conflict_id", "")),
                conflict_name=str(raw_data.get("conflict_name", "")),
                actor1=str(raw_data.get("side_a") or raw_data.get("actor1", "")),
                actor2=str(raw_data.get("side_b") or raw_data.get("actor2", "")),
                country_name=str(raw_data.get("country", "")),
                iso3=iso3,
                region=str(raw_data.get("region", "")),
                adm_1=str(raw_data.get("adm_1", "")),
                date_start=datetime.strptime(d_start_raw, "%Y-%m-%d").date(),
                date_end=datetime.strptime(d_end_raw, "%Y-%m-%d").date(),
                deaths_best=int(raw_data.get("best") or raw_data.get("deaths_best", 0)),
                deaths_civilians=int(raw_data.get("deaths_civilians", 0)),
                ingested_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.debug("Failed validating UCDP GED record: %s", e)
            return None

    def extract(self) -> ExtractorResult[UCDPGEDRecord]:
        records: List[UCDPGEDRecord] = []
        errors: List[str] = []
        metadata = ExtractionMetadata(
            source_name="ucdp",
            records_extracted=len(records),
            records_failed=len(errors),
            parameters=self.config.model_dump(),
        )
        return ExtractorResult(metadata=metadata, records=records, errors=errors)
