"""World Bank Extractor Module."""

from __future__ import annotations

from pipeline.extractors.worldbank.extractor import WorldBankDataExtractor
from pipeline.extractors.worldbank.schemas import WorldBankIndicatorRecord, WorldBankQueryConfig

__all__ = [
    "WorldBankDataExtractor",
    "WorldBankIndicatorRecord",
    "WorldBankQueryConfig",
]
