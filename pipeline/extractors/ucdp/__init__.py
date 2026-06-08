"""UCDP Extractor Module."""

from __future__ import annotations

from pipeline.extractors.ucdp.extractor import UCDPDataExtractor
from pipeline.extractors.ucdp.schemas import UCDPConflictRecord, UCDPExtractorConfig, UCDPGEDRecord

__all__ = [
    "UCDPConflictRecord",
    "UCDPDataExtractor",
    "UCDPExtractorConfig",
    "UCDPGEDRecord",
]
