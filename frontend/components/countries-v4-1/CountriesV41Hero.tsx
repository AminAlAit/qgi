/**
 * CountriesV41Hero — headline + lede for /countries.
 *
 * 2026-05-29 (V4.1 round 2): the 4 stat tiles and the inline Vintage chip
 * are removed per rule §2 (one vintage stamp at top of session) and the
 * founder's task #34 ("Reclaim the vertical real estate for the country
 * grid"). The h1 goes plural per rule §6. The lede drops the
 * self-flagellating "none of these recipes is yet deployed for real
 * decisions" per rule §1.4 — the panel is no longer the headline.
 */
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";

export function CountriesV41Hero({
  total,
  litAny,
  compoundHigh,
  countryOfTheWeek,
}: {
  total: number;
  litAny: number;
  compoundHigh: number;
  countryOfTheWeek: CountryV4;
}) {
  // Stats are intentionally NOT rendered as tiles. Counts and country of
  // the week stay in the props signature so callers can pass them without
  // change; they're available for a future inline-treatment redesign.
  void total;
  void litAny;
  void compoundHigh;
  void countryOfTheWeek;

  return (
    <header style={{ marginBottom: "8px" }}>
      <div
        style={{
          color: "var(--qgi-text-dim)",
          fontSize: "10px",
          letterSpacing: "4px",
          textTransform: "uppercase",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "8px",
        }}
      >
        Country Atlas
      </div>
      <div style={{ maxWidth: "860px", marginBottom: "8px" }}>
        <h1
          style={{
            fontSize: "34px",
            fontWeight: 600,
            lineHeight: 1.1,
            margin: "0 0 10px",
          }}
        >
          What does QGI say about these countries, right now?
        </h1>
        <p
          style={{
            color: "var(--qgi-text-muted)",
            fontSize: "14px",
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          Every country we track, with the trends its recent signals resemble, the
          indicators behind each score, how it has moved, and its closest historical
          analogues. Scores measure resemblance to past pre-event conditions, not the
          chance an event will happen. Open any card for the full country view.
        </p>
      </div>
    </header>
  );
}
