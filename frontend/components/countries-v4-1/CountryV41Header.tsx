/**
 * CountryV41Header — header strip for /countries/[iso].
 *
 * Neutral page chrome (Talia): a country is not one family, so the header
 * does not flood with a single hue. The flag tile carries a thin
 * dominant-family border; family identity lives in the chip row (each chip
 * = letter glyph + label), with the dominant family emphasized. The lede
 * states the honest frame (resemblance not forecast; none deployed) in
 * plain language.
 */
import { Sparkles } from "lucide-react";
import { ExplainTip } from "@/components/design/ExplainTip";
import { FlagImg } from "./FlagImg";
import { FamilyChip } from "./FamilyChip";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import { familiesByBestScore } from "@/lib/te-mock/country-families";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";

function fmtPop(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

export function CountryV41Header({ country }: { country: CountryV4 }) {
  const fams = familiesByBestScore(country);
  const dominant = fams[0];
  const accent = dominant?.color ?? NEUTRAL_SLATE;
  const famCount = fams.length;

  const lede =
    `${country.name} currently matches ${country.recipes_lit_count} of our risk ` +
    `trends across ${famCount} threat famil${famCount === 1 ? "y" : "ies"}. The scores ` +
    `below rank how closely ${country.name}'s recent signals resemble the conditions ` +
    `that preceded similar events elsewhere. They are a measure of resemblance, not a ` +
    `forecast.`;

  return (
    <div
      style={{ display: "flex", gap: "20px", alignItems: "flex-start", flexWrap: "wrap" }}
    >
      <div
        style={{
          width: "88px",
          height: "88px",
          background: "var(--qgi-bg)",
          border: `1px solid ${accent}`,
          borderRadius: "10px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          overflow: "hidden",
        }}
      >
        <FlagImg emoji={country.flag_emoji} name={country.name} width={64} radius={4} />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Status chip row + Generate Country Report CTA — quiet not alarming.
            CTA is intentionally disabled: an upcoming feature where a thinking
            AI model reads everything QGI knows about this country and writes
            a full intelligence report via API. */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            marginBottom: "10px",
            flexWrap: "wrap",
            justifyContent: "space-between",
            /* Constrain so children cannot push past the available column
               width (which on phones is the viewport minus sidebar margins).
               Without this, the flex row can try to fit both children on one
               line even when there is no room, causing overflow. */
            maxWidth: "100%",
            minWidth: 0,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              flexWrap: "wrap",
            }}
          >
            {/* "In active rotation" chip removed 2026-06-11 (founder): it was
                static decoration shown identically for every country, and its
                grammar read as if the COUNTRY were in rotation. The per-trend
                "in play" labels carry that status where it belongs. */}
            {/* Real tooltip, not a title attr: three of five usability
                personas (2026-06-11) hit this pill as a definition dead-end
                and one called it a blocker for citing the number. */}
            <ExplainTip
              text="Compound Risk blends this country's elevated trend matches (50 and above) into one bounded 0-100 reading, dampened when few trends are elevated. It is a breadth-times-intensity summary, not a probability."
              style={{
                fontSize: "11px",
                padding: "3px 9px",
                border: "1px solid var(--qgi-border)",
                color: "var(--qgi-text)",
                borderRadius: "4px",
                letterSpacing: "0.3px",
                fontFamily: "ui-monospace, monospace",
                fontWeight: 600,
                display: "inline-block",
              }}
            >
              Compound Risk {country.compound_score.toFixed(0)}
            </ExplainTip>
          </div>
          <button
            data-tour="generate-report-button"
            type="button"
            disabled
            aria-disabled="true"
            aria-label={`Generate Country Report for ${country.name} (coming soon)`}
            title={`Coming soon: a thinking AI model reads everything QGI knows about ${country.name} (every trend in play, its drivers, its analogues, its movement) and writes you a full intelligence report via API. Disabled today; live in a future release.`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "7px 12px",
              background:
                "linear-gradient(135deg, rgba(56,189,248,0.18) 0%, rgba(56,189,248,0.05) 100%)",
              border: "1px solid rgba(56,189,248,0.55)",
              borderRadius: "5px",
              color: "var(--qgi-text)",
              fontSize: "11.5px",
              fontWeight: 600,
              letterSpacing: "0.3px",
              cursor: "not-allowed",
              opacity: 0.85,
              /* Allow the label to wrap on very narrow viewports so the
                 button never bleeds past the container edge.
                 whiteSpace: "nowrap" removed — the Soon badge is a separate
                 inline element so it naturally wraps below on phones. */
              maxWidth: "100%",
              flexShrink: 1,
              minWidth: 0,
            }}
          >
            <Sparkles
              size={13}
              strokeWidth={1.8}
              aria-hidden="true"
              color="var(--qgi-accent)"
              style={{ flexShrink: 0 }}
            />
            {/* On phones (<420px) shorten label to "Report"; on wider
                viewports show the full "Generate Country Report" string.
                Done with two sibling spans toggled via CSS classes that
                reference a container-query-free breakpoint using the
                Tailwind responsive prefix on the className. */}
            <span
              className="hidden min-[420px]:inline"
              style={{ fontFamily: "var(--font-qg-brand)", whiteSpace: "nowrap" }}
            >
              Generate Country Report
            </span>
            <span
              className="inline min-[420px]:hidden"
              style={{ fontFamily: "var(--font-qg-brand)", whiteSpace: "nowrap" }}
            >
              Report
            </span>
            <span
              style={{
                fontSize: "9px",
                padding: "1px 6px",
                background: "rgba(56,189,248,0.25)",
                border: "1px solid rgba(56,189,248,0.55)",
                color: "var(--qgi-accent)",
                borderRadius: "3px",
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                fontWeight: 700,
                fontFamily: "var(--font-qg-brand)",
                whiteSpace: "nowrap",
                flexShrink: 0,
              }}
            >
              Soon
            </span>
          </button>
        </div>

        <h1
          style={{
            fontSize: "30px",
            fontWeight: 600,
            lineHeight: 1.15,
            margin: "0 0 6px",
          }}
        >
          {country.name}
        </h1>
        <p
          style={{
            color: "var(--qgi-text-muted)",
            fontSize: "13px",
            margin: "0 0 14px",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          {country.iso} · {country.region} · pop. {fmtPop(country.population)}
        </p>

        <p
          style={{
            maxWidth: "720px",
            fontSize: "15px",
            lineHeight: 1.65,
            color: "var(--qgi-text)",
            margin: "0 0 14px",
          }}
        >
          {lede}
        </p>

        {/* Family chip row — dominant emphasized.
            Rule 2: country-scoped surface. Each chip represents a family but
            uses the top recipe in that family as the glyph icon (iconNode
            prop), making the chip iconographic without becoming a per-recipe
            chip. Label is preserved after the icon. */}
        {fams.length > 0 && (
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            {fams.map((f, i) => {
              // Find the top-scoring recipe in this family for the country.
              const topRecipeInFamily = country.top_recipes.find((r) => r.l1_id === f.id);
              const iconNode = topRecipeInFamily ? (
                <RecipeIcon
                  recipeId={topRecipeInFamily.recipe_id}
                  size={12}
                  strokeWidth={1.8}
                  aria-hidden="true"
                />
              ) : undefined;
              return (
                <FamilyChip
                  key={f.id}
                  id={f.id}
                  label={f.label}
                  color={f.color}
                  emphasis={i === 0}
                  iconNode={iconNode}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
