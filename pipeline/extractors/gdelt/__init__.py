"""GDELT Extractor Module."""

from __future__ import annotations

from pipeline.extractors.gdelt.extractor import GDELTDataExtractor
from pipeline.extractors.gdelt.schemas import GDELTEventRecord, GDELTGKGRecord, GDELTQueryConfig

__all__ = [
    "GDELTDataExtractor",
    "GDELTEventRecord",
    "GDELTGKGRecord",
    "GDELTQueryConfig",
]
