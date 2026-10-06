/**
 * AnalogSpotlight — server component.
 *
 * Finds the most striking non-weak analog pair that has a verified
 * "what happened next" narrative, and surfaces it as a full-width callout.
 *
 * Resolution order:
 *   1. buildTopPairTeasers() — top non-weak pairs by match score
 *   2. Cross-reference country_b_iso2 + country_b_year against what-happened-next.json
 *   3. First hit wins; fallback = hardcoded UK→UK 1992 pair (real data)
 *
 * The what-happened-next JSON is resolved at build time by Next.js
 * (resolveJsonModule: true in tsconfig). This is a server component only —
 * do NOT add "use client".
 */
import Link from "next/link";
import type { Route } from "next";
import { buildTopPairTeasers } from "@/lib/te-mock/dashboard-v4-1-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

// Build-time JSON import — valid in server components only.

import whatHappenedNext from "@/data/curation/what-happened-next.json";

type WhnMap = Record<string, { blurb: string; confidence: string }>;
const WHN: WhnMap = whatHappenedNext as unknown as WhnMap;

interface SpotlightData {
  countryA: string;
  countryAIso2: string | null;
  countryB: string;
  countryBYear: number;
  countryBIso2: string | null;
  matchPct: number;
  recipeId: string;
  blurb: string;
}

function buildSpotlightData(): SpotlightData | null {
  try {
    const pairs = buildTopPairTeasers(50); // get enough to find a WHN hit
    for (const pair of pairs) {
      const key = `${pair.country_b_iso2 ?? ""}-${pair.country_b_year}`;
      const entry = WHN[key];
      if (entry?.blurb) {
        return {
          countryA: pair.country_a,
          countryAIso2: pair.country_a_iso2,
          countryB: pair.country_b,
          countryBYear: pair.country_b_year,
          countryBIso2: pair.country_b_iso2,
          matchPct: Math.round(pair.match_pct),
          recipeId: pair.recipe_id,
          blurb: entry.blurb,
        };
      }
    }
  } catch {
    /* fall through to hardcoded fallback */
  }
  return null;
}

// Hardcoded fallback: the UK/1992 pair is the flagship report's anchor analog.
// This is real data from the te-fleet-run-2 scores file.
const FALLBACK: SpotlightData = {
  countryA: "United Kingdom",
  countryAIso2: "gb",
  countryB: "United Kingdom",
  countryBYear: 1992,
  countryBIso2: "gb",
  matchPct: 98, // 0.975 cosine ≈ 98% rounded
  recipeId: "currency_crisis",
  blurb:
    "In September 1992 the UK was forced to withdraw from the European Exchange Rate Mechanism " +
    "after the pound fell below its agreed floor. The episode — Black Wednesday — cost the " +
    "Treasury an estimated £3.4 billion. Interest rates were raised to 15% in a single day " +
    "before the government abandoned the ERM entirely.",
};

export function AnalogSpotlight() {
  const data = buildSpotlightData() ?? FALLBACK;

  const flagEmojiA = flagFor(data.countryA);
  const flagEmojiB = flagFor(data.countryB);

  // Truncate blurb to ~3 lines worth (~300 chars) for the homepage card.
  const blurb = data.blurb.length > 300 ? data.blurb.slice(0, 297) + "…" : data.blurb;

  return (
    <div className="flex flex-col md:flex-row gap-8 md:gap-12 items-start">
      {/* Left: the pairing */}
      <div
        className="flex-shrink-0 flex flex-col gap-4"
        style={{ minWidth: "220px", maxWidth: "280px" }}
      >
        <p
          className="text-[10px] tracking-widest uppercase"
          style={{
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          Historical Analogue
        </p>

        <div className="flex flex-col gap-3">
          {/* Country A — present */}
          <div className="flex items-center gap-3">
            <FlagImg emoji={flagEmojiA} name={data.countryA} width={28} radius={3} />
            <div>
              <div
                className="text-[13px] font-semibold"
                style={{ color: "var(--qgi-text)" }}
              >
                {data.countryA}{" "}
                <span style={{ color: "var(--qgi-text-dim)" }}>today</span>
              </div>
            </div>
          </div>

          {/* Connector */}
          <div className="flex items-center gap-2 pl-1">
            <div
              className="text-[10px] tracking-widest"
              style={{
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              &darr; {data.matchPct}% structural match
            </div>
          </div>

          {/* Country B — historical */}
          <div className="flex items-center gap-3">
            <FlagImg emoji={flagEmojiB} name={data.countryB} width={28} radius={3} />
            <div>
              <div
                className="text-[13px] font-semibold"
                style={{ color: "var(--qgi-text)" }}
              >
                {data.countryB}{" "}
                <span style={{ color: "var(--qgi-accent)" }}>{data.countryBYear}</span>
              </div>
              <div className="text-[10px]" style={{ color: "var(--qgi-text-dim)" }}>
                historical reference
              </div>
            </div>
          </div>
        </div>

        <Link
          href={`/trends/${data.recipeId}` as Route}
          className="text-[12px] border-b pb-0.5 w-fit transition-colors hover:text-[var(--qgi-accent)] hover:border-[var(--qgi-accent)]"
          style={{ color: "var(--qgi-text-muted)", borderColor: "var(--qgi-border)" }}
        >
          Explore this trend &rarr;
        </Link>
      </div>

      {/* Right: what happened next */}
      <div className="flex-1 min-w-0">
        <p
          className="text-[10px] tracking-widest uppercase mb-3"
          style={{
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          What happened next
        </p>
        <p
          className="text-sm leading-relaxed"
          style={{ color: "var(--qgi-text-muted)", maxWidth: "56ch" }}
        >
          {blurb}
        </p>
        <p
          className="mt-4 text-[11px] leading-relaxed"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          The analogue is a structural resemblance drawn from indicator trajectories, not
          a repetition of events.
        </p>
      </div>
    </div>
  );
}
