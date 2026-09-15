/**
 * TrajectoryDetail — the per-recipe "Trajectory" deep-dive body, lives at
 * /trends/[slug]/trajectory.
 *
 * "Trajectory" (Sofia naming consult, 2026-05-28) is the V4 name for a
 * recipe's canonical movement shape — the recurring shape its key indicators
 * trace in the years before the event. It replaces the word "Pattern" on the
 * TE/recipe surface; "pattern" returns to its SCDI/Correlation-Cascade
 * meaning at the legacy /patterns route.
 *
 * Built to the V4.1 bar (same class + rules as Countries V4.1): honest plain
 * copy (no M8-R5 / walk / gate jargon, no "Pattern" wording), flagcdn flags,
 * L1-family color as a thin accent only, the anti-causal firewall folded into
 * a calm "How to read" panel, no em-dashes, no rendered persona credit.
 *
 * Reuses the shared V4.1 vocabulary: PanelShell / FlagImg / RecipeIcon.
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import { getMock, type TrackerRecipe } from "@/lib/te-mock/recipes";
import type { PatternEntry } from "@/lib/te-mock/patterns-v4-data";
import { COUNTRIES_V4 } from "@/lib/te-mock/countries-v4-data";
import { familyColor, CALM_SLATE_BLUE } from "@/lib/te-mock/l1-families";
import { flagFor } from "@/lib/te-mock/country-flags";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { PatternShapeSparkline } from "@/components/patterns-v4/PatternShapeSparkline";

// Resolve a country name → its /countries slug, where we have one.
const ISO_BY_NAME = new Map(COUNTRIES_V4.map((c) => [c.name, c.iso.toLowerCase()]));

/**
 * Vowel-aware indefinite article. Returns "an" if noun starts with a vowel
 * sound, "a" otherwise. For plural / noun-phrase labels that don't naturally
 * take a singular article, the call-site should rephrase to avoid the article
 * entirely rather than calling this helper.
 */
function an(noun: string): string {
  return /^[aeiouAEIOU]/.test(noun.trim()) ? "an" : "a";
}

/**
 * Returns true if the label is a noun phrase (contains " and " or starts with
 * a plural-sounding word) that doesn't naturally take a singular article.
 * Used to decide whether to rephrase around the article rather than prepend one.
 */
function isNounPhrase(label: string): boolean {
  // Match both " and " and " & " — recipe labels in the tracker mix the two
  // conventions ("Drought and Famine" vs "Civil War & Insurgency"). Without
  // the ampersand branch, the latter falls through to the article path and
  // renders "a civil war & insurgency event" instead of "conditions of
  // civil war & insurgency".
  return / and | & /i.test(label);
}

function describeArchetype(points: number[]): string {
  const start = points[0];
  const end = points[points.length - 1];
  const mid = points[Math.floor(points.length / 2)];
  const rise = end - start;
  const oscRange = Math.max(...points) - Math.min(...points);
  if (oscRange > 2.4 && Math.abs(rise) < 1.0) return "Oscillating: cyclical rhythm";
  if (rise > 1.8 && mid < (start + end) / 2 - 0.4)
    return "Late tip: slow drift, then a sharp turn";
  if (rise > 1.5) return "Ramp: sustained escalation toward the event";
  if (rise < -0.5 && mid > end) return "U-shape: trough, then recovery";
  if (Math.abs(end - mid) > 1.3 && Math.abs(mid - start) < 0.5)
    return "Step: stable baseline, then a jump";
  return "Mixed shape";
}

export function TrajectoryDetail({
  pattern,
  recipe,
}: {
  pattern: PatternEntry;
  recipe: TrackerRecipe;
}) {
  const mock = getMock(recipe);
  const accent = familyColor(pattern.l1_id, pattern.l1_color);
  const nInd = mock.indicators.length;
  const archetype = describeArchetype(pattern.shape_points);

  return (
    <div style={{ background: "var(--qgi-bg)", color: "var(--qgi-text)" }}>
      {/* Header band */}
      <div
        style={{
          borderBottom: "1px solid var(--qgi-border)",
          background: "var(--qgi-surface)",
        }}
      >
        <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "20px 24px 24px" }}>
          <nav
            aria-label="Breadcrumb"
            style={{
              fontSize: "11px",
              letterSpacing: "0.3px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              marginBottom: "16px",
            }}
          >
            <Link
              href={`/trends/${recipe.recipe_id}` as Route}
              style={{ color: "var(--qgi-text-muted)", textDecoration: "none" }}
            >
              ← {recipe.label}
            </Link>
            <span style={{ margin: "0 8px", opacity: 0.5 }}>/</span>
            <span style={{ color: accent }}>
              {pattern.l1_id} · {pattern.l1_label}
            </span>
            <span style={{ margin: "0 8px", opacity: 0.5 }}>/</span>
            <span>Trajectory</span>
          </nav>

          <div
            style={{
              display: "flex",
              gap: "20px",
              alignItems: "flex-start",
              flexWrap: "wrap",
            }}
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
                color: accent,
                flexShrink: 0,
              }}
            >
              <RecipeIcon recipeId={pattern.recipe_id} size={52} strokeWidth={1.5} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: "10px",
                  letterSpacing: "2px",
                  textTransform: "uppercase",
                  color: accent,
                  fontFamily: "ui-monospace, monospace",
                  marginBottom: "6px",
                }}
              >
                Trajectory · canonical movement shape
              </div>
              <h1
                style={{
                  fontSize: "30px",
                  fontWeight: 600,
                  lineHeight: 1.15,
                  margin: "0 0 8px",
                }}
              >
                {recipe.label}
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
                {nInd} indicators · {pattern.window_y}y window ·{" "}
                {pattern.n_positives || "n/a"} verified cases
              </p>
              <p
                style={{
                  maxWidth: "760px",
                  fontSize: "15px",
                  lineHeight: 1.65,
                  color: "var(--qgi-text)",
                  margin: 0,
                }}
              >
                The {recipe.label.toLowerCase()} trajectory is the recurring shape these{" "}
                {nInd} indicators trace in the {pattern.window_y} years before the event,
                averaged across {pattern.n_positives || "the available"} verified
                historical cases. A country is measured by how closely its recent movement
                resembles this shape. It is a measure of resemblance, not a forecast.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Body */}
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "24px 24px 64px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* The shape */}
          <PanelShell
            title="The shape"
            accent={accent}
            icon={<RecipeIcon recipeId={pattern.recipe_id} size={16} strokeWidth={1.7} />}
            caption={`The canonical movement shape across ${pattern.n_positives || "the available"} verified cases. The horizontal axis is years before the event; the vertical axis is the combined standardized level of the ${nInd} indicators below. Above the line is the danger half; below it the calm half.`}
          >
            <div
              style={{
                background: "var(--qgi-bg)",
                border: "1px solid var(--qgi-border)",
                borderRadius: "8px",
                padding: "16px 18px",
              }}
            >
              <PatternShapeSparkline
                points={pattern.shape_points}
                color={accent}
                windowY={pattern.window_y}
                variant="detail"
              />
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--qgi-text-dim)",
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: "0.4px",
                  marginTop: "10px",
                  paddingTop: "10px",
                  borderTop: "1px solid var(--qgi-border)",
                }}
              >
                Archetype: <span style={{ color: accent }}>{archetype}</span>
              </div>
            </div>
          </PanelShell>

          {/* Indicators */}
          <PanelShell
            title="Indicators composing the shape"
            accent={accent}
            caption={`The ${nInd} indicators whose joint movement forms this trajectory. The trajectory is built from all of them together; no single one carries it alone.`}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                gap: "10px",
              }}
            >
              {mock.indicators.map((ind) => (
                <div
                  key={ind.code}
                  style={{
                    padding: "12px",
                    background: "var(--qgi-bg)",
                    border: "1px solid var(--qgi-border)",
                    borderRadius: "6px",
                  }}
                  title={ind.code}
                >
                  <div
                    style={{
                      fontSize: "9.5px",
                      letterSpacing: "0.8px",
                      color: "var(--qgi-text-dim)",
                      fontFamily: "ui-monospace, monospace",
                      marginBottom: "4px",
                      textTransform: "uppercase",
                    }}
                  >
                    {ind.provider}
                  </div>
                  <div
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--qgi-text)",
                      lineHeight: 1.3,
                    }}
                  >
                    {ind.name}
                  </div>
                </div>
              ))}
            </div>
          </PanelShell>

          {/* Historical cases */}
          <PanelShell
            title={
              pattern.historical_examples_source === "curated"
                ? "Where this trajectory ran to the event"
                : "Illustrative cases (placeholder)"
            }
            accent={accent}
            caption={
              pattern.historical_examples_source === "curated"
                ? isNounPhrase(recipe.label)
                  ? `Past cases from the verified record where this shape ran to conditions of ${recipe.label.toLowerCase()}. Each entry is a historical fact about that country, never a statement about anyone's future.`
                  : `Past cases from the verified record where this shape ran to ${an(recipe.label)} ${recipe.label.toLowerCase()} event. Each entry is a historical fact about that country, never a statement about anyone's future.`
                : "Illustrative cases drawn from the trend's top-country list. These are NOT from a verified-positives corpus; they are placeholders until that trend's historical record is curated. Treat them as design content, not historical evidence."
            }
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {pattern.historical_examples.map((ex, i) => (
                <div
                  key={`${ex.country}-${ex.year}`}
                  style={{
                    display: "flex",
                    gap: "12px",
                    alignItems: "flex-start",
                    padding: "10px 12px",
                    background: "var(--qgi-bg)",
                    border: "1px solid var(--qgi-border)",
                    borderLeft: `2px solid ${accent}`,
                    borderRadius: "5px",
                  }}
                >
                  <FlagImg
                    emoji={flagFor(ex.country)}
                    name={ex.country}
                    width={22}
                    radius={2}
                    style={{ marginTop: "2px" }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "13px",
                        fontWeight: 600,
                        color: "var(--qgi-text)",
                        marginBottom: "2px",
                      }}
                    >
                      {ex.country}{" "}
                      <span
                        style={{
                          color: accent,
                          fontFamily: "ui-monospace, monospace",
                          fontSize: "12px",
                        }}
                      >
                        {ex.year}
                      </span>
                    </div>
                    <p
                      style={{
                        fontSize: "12.5px",
                        color: "var(--qgi-text-muted)",
                        lineHeight: 1.5,
                        margin: 0,
                      }}
                    >
                      {ex.event_summary}
                    </p>
                  </div>
                  <span
                    style={{
                      fontSize: "9px",
                      color: "var(--qgi-text-dim)",
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    #{String(i + 1).padStart(2, "0")}
                  </span>
                </div>
              ))}
            </div>
          </PanelShell>

          {/* Current closest matches */}
          <PanelShell
            title="Closest current matches"
            accent={accent}
            caption={`Countries whose most recent ${pattern.window_y}-year movement most closely resembles this trajectory today. A similarity rank from 0 to 100, not a probability.`}
          >
            <ol
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "2px",
              }}
            >
              {pattern.current_top_matches.slice(0, 10).map((m, i) => {
                const slug = ISO_BY_NAME.get(m.country);
                const row = (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "26px auto minmax(0, 1fr) 90px 44px",
                      alignItems: "center",
                      gap: "12px",
                      padding: "8px 8px",
                      borderBottom: "1px solid rgba(255,255,255,0.04)",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "11px",
                        color: "var(--qgi-text-dim)",
                        fontFamily: "ui-monospace, monospace",
                      }}
                    >
                      #{String(i + 1).padStart(2, "0")}
                    </span>
                    <FlagImg
                      emoji={flagFor(m.country)}
                      name={m.country}
                      width={22}
                      radius={2}
                    />
                    <span
                      style={{
                        fontSize: "13.5px",
                        color: "var(--qgi-text)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {m.country}
                      <span
                        style={{
                          fontSize: "10px",
                          color: "var(--qgi-text-dim)",
                          fontFamily: "ui-monospace, monospace",
                          marginLeft: "8px",
                        }}
                      >
                        {m.region}
                      </span>
                    </span>
                    <span
                      style={{
                        height: "8px",
                        background: "var(--qgi-bg)",
                        border: "1px solid var(--qgi-border)",
                        borderRadius: "2px",
                        overflow: "hidden",
                      }}
                      aria-hidden
                    >
                      <span
                        style={{
                          display: "block",
                          height: "100%",
                          width: `${m.match_score}%`,
                          background: accent,
                          opacity: 0.85,
                        }}
                      />
                    </span>
                    <span
                      style={{
                        fontFamily: "ui-monospace, monospace",
                        fontSize: "13px",
                        color: accent,
                        fontWeight: 600,
                        textAlign: "right",
                      }}
                    >
                      {m.match_score.toFixed(0)}
                    </span>
                  </div>
                );
                return (
                  <li key={m.country}>
                    {slug ? (
                      <Link
                        href={`/countries/${slug}` as Route}
                        style={{
                          textDecoration: "none",
                          color: "inherit",
                          display: "block",
                        }}
                      >
                        {row}
                      </Link>
                    ) : (
                      row
                    )}
                  </li>
                );
              })}
            </ol>
          </PanelShell>

          {/* How to read — the calm anti-causal firewall */}
          <PanelShell title="How to read this trajectory" accent={CALM_SLATE_BLUE}>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "10px",
              }}
            >
              {[
                `This is the shape of the run-up, not a forecast. Each past ${recipe.label.toLowerCase()} case left a similar imprint on these ${nInd} indicators over about ${pattern.window_y} years; we average those to get the shape above.`,
                "A country matches when its own recent movement resembles that shape. A high match means close resemblance, not a high chance the event happens.",
                "The indicators are the shape's ingredients, not levers to pull. This describes structure; it does not prescribe a fix.",
                "Match scores are similarity ranks, not probabilities. No trend here is yet deployed for real decisions.",
              ].map((s, i) => (
                <li
                  key={i}
                  style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}
                >
                  <span
                    style={{
                      color: CALM_SLATE_BLUE,
                      fontFamily: "ui-monospace, monospace",
                      fontSize: "12px",
                      lineHeight: 1.6,
                      flexShrink: 0,
                    }}
                  >
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span
                    style={{
                      fontSize: "13px",
                      lineHeight: 1.6,
                      color: "var(--qgi-text)",
                    }}
                  >
                    {s}
                  </span>
                </li>
              ))}
            </ul>
          </PanelShell>

          {/* Footer links */}
          <div
            style={{
              display: "flex",
              gap: "16px",
              flexWrap: "wrap",
              alignItems: "center",
              paddingTop: "8px",
            }}
          >
            <Link
              href={"/trends/trajectory-ranking" as Route}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                fontSize: "12px",
                fontFamily: "ui-monospace, monospace",
                letterSpacing: "0.3px",
                color: accent,
                textDecoration: "none",
                border: `1px solid ${accent}`,
                borderRadius: "6px",
                padding: "8px 14px",
              }}
            >
              Trajectory strength ranking →
            </Link>
            <Link
              href={`/trends/${recipe.recipe_id}` as Route}
              style={{
                fontSize: "12px",
                color: "var(--qgi-text-muted)",
                textDecoration: "none",
                fontFamily: "ui-monospace, monospace",
                letterSpacing: "0.3px",
              }}
            >
              ← back to the {recipe.label.toLowerCase()} trend
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
