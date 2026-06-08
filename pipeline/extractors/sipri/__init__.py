"""SIPRI Extractor Module."""

from __future__ import annotations

from pipeline.extractors.sipri.extractor import SIPRIDataExtractor
from pipeline.extractors.sipri.schemas import (
    SIPRIArmsTransferRecord,
    SIPRIExtractorConfig,
    SIPRIMilitaryExpenditureRecord,
)

__all__ = [
    "SIPRIArmsTransferRecord",
    "SIPRIDataExtractor",
    "SIPRIExtractorConfig",
    "SIPRIMilitaryExpenditureRecord",
]
