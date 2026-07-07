"""Cross-checks pipeline Gold schemas against frontend TypeScript interfaces."""
from __future__ import annotations

REQUIRED_COUNTRY_RISK_KEYS = ("countryId", "countryName", "overallRiskScore", "overallRiskTier")

def lint_country_risk_record(record: dict[str, object]) -> bool:
    return all(k in record for k in REQUIRED_COUNTRY_RISK_KEYS)
