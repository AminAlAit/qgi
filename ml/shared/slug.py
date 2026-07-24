"""Country-name → filesystem-safe slug.

One canonical implementation shared across qgi-ml scripts (#422 Bug 6).

## Callers (2026-04-24)

- `qgi-ml/scripts/generate_pair_windows.py::_slug` — delegates here
- `qgi-ml/scripts/generate_frontend_data.py::name_to_slug` — NOT yet
  consolidated. It applies extra rules (strip leading "the ", collapse
  "of the" → "of") that downstream callers depend on; converting it to
  delegate here requires auditing every curated-events match site. Left
  for a follow-up pass — tracked as a TODO in that file.
- `qgi-frontend/lib/country-risks.ts` — TypeScript mirror. Kept in sync
  manually for now; the shared JSON test fixture in
  `tests/fixtures/canonical_slugs.json` should be the single source of
  truth once the TS side adopts it.

## Semantics

Treats apostrophes, periods, commas, hyphens, and whitespace as token
separators. Converts `&` to `and`. Lowercases. Collapses runs of
underscores. Strips leading/trailing underscores.

Verified against curated country file names: china, north_korea,
democratic_republic_of_congo, sao_tome_and_principe — all round-trip
correctly.
"""
from __future__ import annotations

import re


def country_slug(name: str | None) -> str | None:
    """Normalize a country name to a lowercase, underscore-delimited slug.

    Returns None for None or empty input.

    Examples:
        country_slug("France") == "france"
        country_slug("United States") == "united_states"
        country_slug("Cote d'Ivoire") == "cote_d_ivoire"
        country_slug("Bosnia & Herzegovina") == "bosnia_and_herzegovina"
        country_slug("Korea, South") == "korea_south"
        country_slug("U.S.A.") == "u_s_a"
    """
    if not name:
        return None
    # #422 Bug 4: apostrophes + periods are token separators, not
    # delete-chars. Commas stay as delete-chars so "Korea, South"
    # collapses to "korea_south" not "korea__south".
    s = name.lower().replace("'", " ").replace(",", "").replace(".", " ").replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s
