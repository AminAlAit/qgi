"""Standardized Source Extractors for QGI Data Pipeline (Directive D34).

Provides Pydantic-validated extraction schemas and adapters for geopolitical,
macroeconomic, and armed conflict telemetry feeds:
- ACLED (Armed Conflict Location & Event Data)
- SIPRI (Stockholm International Peace Research Institute)
- World Bank (World Development Indicators & Governance)
- GDELT (Global Database of Events, Language, and Tone)
- UCDP (Uppsala Conflict Data Program)
"""

from __future__ import annotations

from pipeline.extractors.base import BaseExtractor, ExtractionMetadata, ExtractorResult

__all__ = [
    "BaseExtractor",
    "ExtractionMetadata",
    "ExtractorResult",
]
