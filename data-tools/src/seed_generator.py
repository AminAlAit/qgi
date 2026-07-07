"""Generates deterministic offline mock seed payloads for local testing."""
from __future__ import annotations

def generate_seed_country_risk(country_id: str = "USA") -> dict[str, object]:
    return {
        "countryId": country_id,
        "countryName": "United States",
        "overallRiskScore": 24.5,
        "overallRiskTier": "LOW",
    }
