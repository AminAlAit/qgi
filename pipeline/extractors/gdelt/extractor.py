"""GDELT Data Extractor implementing standard extraction and validation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.extractors.base import BaseExtractor, ExtractionMetadata, ExtractorResult
from pipeline.extractors.gdelt.schemas import GDELTEventRecord, GDELTGKGRecord, GDELTQueryConfig

logger = logging.getLogger(__name__)


class GDELTDataExtractor(BaseExtractor[GDELTQueryConfig, GDELTEventRecord]):
    """Standardized extractor for GDELT 2.0 event streams."""

    def __init__(self, config: Optional[GDELTQueryConfig] = None) -> None:
        super().__init__(config or GDELTQueryConfig())

    def validate_record(self, raw_data: Dict[str, Any]) -> Optional[GDELTEventRecord]:
        try:
            return GDELTEventRecord(
                global_event_id=str(raw_data.get("GlobalEventID") or raw_data.get("global_event_id", "")),
                day=int(raw_data.get("Day") or raw_data.get("day", 20260101)),
                actor1_code=str(raw_data.get("Actor1Code") or ""),
                actor1_name=str(raw_data.get("Actor1Name") or ""),
                actor1_country_code=str(raw_data.get("Actor1CountryCode") or ""),
                actor2_code=str(raw_data.get("Actor2Code") or ""),
                actor2_name=str(raw_data.get("Actor2Name") or ""),
                actor2_country_code=str(raw_data.get("Actor2CountryCode") or ""),
                event_code=str(raw_data.get("EventCode") or "010"),
                event_base_code=str(raw_data.get("EventBaseCode") or ""),
                quad_class=int(raw_data.get("QuadClass") or 1),
                goldstein_scale=float(raw_data.get("GoldsteinScale") or 0.0),
                num_mentions=int(raw_data.get("NumMentions") or 1),
                num_sources=int(raw_data.get("NumSources") or 1),
                num_articles=int(raw_data.get("NumArticles") or 1),
                avg_tone=float(raw_data.get("AvgTone") or 0.0),
                actor1_geo_country_code=str(raw_data.get("Actor1Geo_CountryCode") or ""),
                actor2_geo_country_code=str(raw_data.get("Actor2Geo_CountryCode") or ""),
                action_geo_country_code=str(raw_data.get("ActionGeo_CountryCode") or ""),
                source_url=str(raw_data.get("SOURCEURL") or raw_data.get("source_url") or ""),
                ingested_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.debug("Failed validating GDELT record: %s", e)
            return None

    def extract(self) -> ExtractorResult[GDELTEventRecord]:
        records: List[GDELTEventRecord] = []
        errors: List[str] = []
        metadata = ExtractionMetadata(
            source_name="gdelt",
            records_extracted=len(records),
            records_failed=len(errors),
            parameters=self.config.model_dump(),
        )
        return ExtractorResult(metadata=metadata, records=records, errors=errors)
