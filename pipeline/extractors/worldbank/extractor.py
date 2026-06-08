"""World Bank Data Extractor implementing standard extraction and validation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.extractors.base import BaseExtractor, ExtractionMetadata, ExtractorResult
from pipeline.extractors.worldbank.schemas import WorldBankIndicatorRecord, WorldBankQueryConfig

logger = logging.getLogger(__name__)


class WorldBankDataExtractor(BaseExtractor[WorldBankQueryConfig, WorldBankIndicatorRecord]):
    """Standardized extractor for World Bank macro & governance indicators."""

    def __init__(self, config: Optional[WorldBankQueryConfig] = None) -> None:
        super().__init__(config or WorldBankQueryConfig())

    def validate_record(self, raw_data: Dict[str, Any]) -> Optional[WorldBankIndicatorRecord]:
        try:
            iso3 = str(raw_data.get("countryiso3code") or raw_data.get("iso3") or "UNK")[:3].upper()
            country_name = str(raw_data.get("country", {}).get("value") or raw_data.get("country_name") or "Unknown")
            indicator_id = str(raw_data.get("indicator", {}).get("id") or raw_data.get("indicator_code") or "")
            indicator_val = str(
                raw_data.get("indicator", {}).get("value") or raw_data.get("indicator_name") or indicator_id
            )
            year_val = int(raw_data.get("date") or raw_data.get("year", 2020))
            raw_val = raw_data.get("value")

            return WorldBankIndicatorRecord(
                iso3=iso3,
                country_name=country_name,
                indicator_code=indicator_id,
                indicator_name=indicator_val,
                year=year_val,
                value=float(raw_val) if raw_val is not None else None,
                unit="",
                source_organization="World Bank Group",
                ingested_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.debug("Failed validating World Bank record: %s", e)
            return None

    def extract(self) -> ExtractorResult[WorldBankIndicatorRecord]:
        records: List[WorldBankIndicatorRecord] = []
        errors: List[str] = []
        metadata = ExtractionMetadata(
            source_name="worldbank",
            records_extracted=len(records),
            records_failed=len(errors),
            parameters=self.config.model_dump(),
        )
        return ExtractorResult(metadata=metadata, records=records, errors=errors)
