import Link from "next/link";
import type { Route } from "next";
import { type TrackerRecipe } from "@/lib/te-mock/recipes";
import { STATUS_META } from "./StatusChip";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { statusLabel } from "@/lib/te-mock/country-families";

/**
 * In v4.1 strategy, map the StatusTone to a chip color that avoids banned
 * internal palette labels. V4.1 §4: validated=green / in-play=calm blue /
 * coming-soon=slate-dim / prior-version=slate-dim.
 */
function toneColor(tone: "deployed" | "neutral" | "failed"): string {
  if (tone === "deployed") return "#3FBF8F";
  if (tone === "failed") return "#5B7E99"; // legacy fallback (no longer used for in-play)
  return "#7A8FA0";
}

// Round-3.6 (2026-05-29) — color-lerp + glow helpers extracted to
// lib/color-lerp.ts so the Risk Board cells use the SAME color math.
// Round-3.6.4 (2026-05-30) — recipe gallery cards use the BOLD glow
// variant; the calm slate panel background has the room for it. The
// Risk Board cells and the Dashboard TopPairsStrip keep the soft
// `confidenceGlow` since they sit on busier surfaces.
import {
  MUTED_GRAY,
  confidenceT,
  lerpHexToRgb,
  confidenceGlowBold,
} from "@/lib/color-lerp";

/**
 * RecipeCard
 *
 * `basePath` defaults to /trends (V4 gallery). The V4.1 gallery
 * passes "/trends" so card clicks land on V4.1 detail pages.
 *
 * `labelStrategy` defaults to "legacy" (byte-identical V4 behavior). Pass
 * "v4.1" for the polished gallery to emit the V4.1 vocabulary
 * ("Validated" / "In play" / "Coming soon" / "Prior version") and
 * suppress every banned chip (HARD-FAIL, Legacy ML-1, LOCO, Walk in flight).
 *
 * V4.1 polish 2026-05-29:
 *   - Per-card vintage line removed (§2: one stamp per session, in the
 *     global header, not per-card).
 *   - "Tested, did not hold up" chip text scrubbed; replaced with "In play"
 *     status chip in the footer (§4).
 *   - Construction-color tier ribbon removed for v4.1 cards (§12 —
 *     redundant with the family-color left border the icon already
 *     carries; an "in-play" recipe doesn't deserve a striped warning
 *     stripe — that's exposure, not confidence).
 */
export function RecipeCard({
  recipe,
  basePath = "/trends",
  labelStrategy = "legacy",
}: {
  recipe: TrackerRecipe;
  basePath?: string;
  labelStrategy?: "legacy" | "v4.1";
}) {
  const statusMeta = STATUS_META[recipe.status];
  const isQueued = recipe.status === "queued";
  const isWalked = recipe.status === "walked_no_graduation";
  const isLegacy = recipe.status === "live_legacy";
  const isFmlFail = recipe.recipe_id === "civil_war_and_insurgency";

  // V4.1 derivations (only computed when strategy === "v4.1", harmless otherwise)
  const v41Label = statusLabel(recipe.status);
  const v41Color = toneColor(v41Label.tone);

  // V4.1 §2: per-card vintage line is dropped. The single session-level
  // vintage stamp lives in the global header. Legacy strategy keeps it.
  const legacyVintage = isQueued
    ? "Release: awaiting first walk"
    : isLegacy
      ? "Release: legacy (pre-TE)"
      : "Release logged in header";

  // V4.1 follow-up 2026-05-29: "Coming soon" recipes are not yet shipped —
  // they should not be clickable. We render the same <article> chrome but
  // without the wrapping <Link>, and we drop cursor:pointer so the card
  // reads as inert.
  const linkable = !isQueued;

  // V4.1 round-3.1 (2026-05-29): L2 subtitle line removed entirely.
  // Founder ratified — the rephrase didn't earn its real estate. Title
  // alone, family chip, and the bottom metric row carry the card.

  const cardChrome = (
    <article
      className={`recipe-card status-${recipe.status}`}
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        padding: "14px",
        minHeight: "200px",
        display: "flex",
        flexDirection: "column",
        transition: "border-color 0.15s, transform 0.15s",
        cursor: linkable ? "pointer" : "default",
        opacity: isQueued ? 0.62 : 1,
      }}
    >
      {/* Top: crest + L1 chip */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: "12px",
        }}
      >
        <div
          style={{
            width: "56px",
            height: "56px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: recipe.l1_color,
            opacity: isQueued ? 0.55 : 0.95,
            border: isQueued ? `1px dashed ${recipe.l1_color}` : "none",
            borderRadius: "4px",
          }}
        >
          <RecipeIcon recipeId={recipe.recipe_id} size={32} strokeWidth={1.5} />
        </div>
        {/* Top-right chip — V4.1 follow-up 2026-05-29: now carries the
              STATUS label (Validated / In play / Coming soon / Prior version)
              in family color. The colored dot preserves the categorical hue
              so the family identity stays legible at a glance. For "In play"
              recipes the dot pulses to signal active rotation; other statuses
              render a static dot. The bottom-right status chip is removed
              with this change (no duplication). */}
        {labelStrategy === "v4.1" ? (
          // V4.1 round-3 amendment (2026-05-29) — 2-bucket vocabulary:
          // "in play" gets a family-color pulsing dot (active rotation).
          // "Coming soon" renders text only — no dot. Founder ratified.
          <span
            style={{
              fontSize: "10px",
              padding: "3px 8px",
              border: `1px solid ${recipe.l1_color}`,
              color: recipe.l1_color,
              borderRadius: "4px",
              letterSpacing: "0.5px",
              fontFamily: "ui-monospace, monospace",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
            }}
            title={recipe.l1_label}
          >
            {!isQueued && (
              <span
                className="qgi-pulse-dot"
                style={{
                  width: "6px",
                  height: "6px",
                  borderRadius: "50%",
                  background: recipe.l1_color,
                  boxShadow: `0 0 0 0 ${recipe.l1_color}`,
                }}
              />
            )}
            {v41Label.label}
          </span>
        ) : (
          // Legacy strategy unchanged — family chip with name + non-pulsing dot.
          <span
            style={{
              fontSize: "10px",
              padding: "3px 8px",
              border: `1px solid ${recipe.l1_color}`,
              color: recipe.l1_color,
              borderRadius: "4px",
              letterSpacing: "0.5px",
              fontFamily: "ui-monospace, monospace",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: recipe.l1_color,
              }}
            />
            {recipe.l1_label}
          </span>
        )}
      </div>

      {/* Title only — V4.1 round-3.1 (2026-05-29): L2 subtitle line dropped
            entirely across every card. The L2 distinction matters only to
            curators, not to the audience; the title + family chip + bottom-
            row metrics carry the whole information story. The legacy strategy
            keeps the same one-line title behavior (it never rendered L2). */}
      <div style={{ flex: 1, marginBottom: "8px" }}>
        <div
          style={{
            fontSize: "14px",
            fontWeight: 600,
            lineHeight: 1.25,
            color: isQueued ? "rgba(255,255,255,0.7)" : "var(--qgi-text)",
          }}
        >
          {recipe.label}
        </div>
      </div>

      {/* V4.1 §12: construction-color tier ribbon removed for v4.1 cards.
            Legacy strategy retains it for backward compat. */}
      {labelStrategy === "legacy" && (
        <div
          style={{
            height: "4px",
            margin: "8px -14px 10px",
            background:
              recipe.status === "graduated"
                ? "#3FBF8F"
                : recipe.status === "walked_no_graduation"
                  ? "repeating-linear-gradient(45deg, #E68F29, #E68F29 4px, transparent 4px, transparent 8px)"
                  : recipe.status === "in_progress"
                    ? "#a78bfa"
                    : recipe.status === "live_legacy"
                      ? "#7A8FA0"
                      : "none",
            borderTop: isQueued ? `1px dashed ${recipe.l1_color}` : "none",
            opacity: isQueued ? 0.3 : 1,
            marginTop: isQueued ? "12px" : "8px",
          }}
        />
      )}

      {/* Bottom row — V4.1 round-3.1 (2026-05-29):
            window/signals badge bottom-LEFT, Confidence number bottom-RIGHT.
            Confidence color gradient interpolates from the muted-text gray
            (#9ab0c4, matching the window/signals chip) at AUC 50% up to
            the recipe's family color at AUC 100%. The visual gradient is
            the meaning: low-confidence recipes look muted, high-confidence
            recipes are visually loud in the family hue. */}
      {labelStrategy === "v4.1" ? (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-end",
            marginTop: "auto",
            paddingTop: "10px",
            gap: "8px",
            minHeight: "44px",
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
            {isWalked && recipe.stats?.window_y && (
              <span style={chipStyle("muted")}>
                {recipe.stats?.window_y}y window · {recipe.stats?.n_indicators ?? "?"}{" "}
                {recipe.stats?.n_indicators === 1 ? "signal" : "signals"}
              </span>
            )}
          </div>
          {typeof recipe.stats?.loco_auc === "number" &&
            (() => {
              const auc = recipe.stats.loco_auc;
              const t = confidenceT(auc * 100);
              const color = lerpHexToRgb(MUTED_GRAY, recipe.l1_color, t);
              // Glow blooms from ~62% upward, full halo at 100%.
              const glow = confidenceGlowBold(recipe.l1_color, t);
              return (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "flex-end",
                    lineHeight: 1,
                  }}
                  title={`${Math.round(auc * 100)}% confidence: how closely this country-trajectory has matched the trend's canonical movement shape. 50% is coin-flip resemblance; higher is closer.`}
                >
                  <div
                    style={{
                      fontSize: "26px",
                      fontWeight: 700,
                      fontFamily: "ui-monospace, monospace",
                      letterSpacing: "-0.5px",
                      color,
                      lineHeight: 1,
                      textShadow: glow || undefined,
                      transition: "text-shadow 180ms ease-out",
                    }}
                  >
                    {Math.round(auc * 100)}%
                  </div>
                  <div
                    style={{
                      fontSize: "9px",
                      letterSpacing: "1.2px",
                      textTransform: "uppercase",
                      color: "var(--qgi-text-dim)",
                      fontFamily: "ui-monospace, monospace",
                      marginTop: "3px",
                    }}
                  >
                    confidence
                  </div>
                </div>
              );
            })()}
        </div>
      ) : (
        // Legacy strategy: byte-identical to the original behavior
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "4px",
            marginBottom: "8px",
            minHeight: "22px",
          }}
        >
          {isQueued && <span style={chipStyle("grey")}>Awaiting curated events</span>}
          {isWalked && (
            <>
              <span style={chipStyle("muted")}>
                LOCO {recipe.stats?.loco_auc?.toFixed(2) ?? "—"}
              </span>
              <span style={chipStyle("fail")}>HARD-FAIL</span>
              <span style={chipStyle("muted")}>
                {recipe.stats?.window_y ?? "?"}y · {recipe.stats?.n_indicators ?? "?"} ind
              </span>
            </>
          )}
          {isLegacy && (
            <>
              <span style={chipStyle("legacy")}>Legacy ML-1</span>
              {isFmlFail && <span style={chipStyle("fail")}>F-ML-1 HARD_FAIL</span>}
            </>
          )}
          {recipe.status === "in_progress" && (
            <span style={chipStyle("purple")}>Walk in flight</span>
          )}
        </div>
      )}

      {/* Trajectory dots — legacy only */}
      {labelStrategy === "legacy" && (
        <div style={{ display: "flex", gap: "4px", marginBottom: "10px", height: "6px" }}>
          {isWalked && <span style={dotStyle("#E68F29")} />}
          {isLegacy && [0, 1, 2].map((i) => <span key={i} style={dotStyle("#7A8FA0")} />)}
        </div>
      )}

      {/* Foot — V4.1 follow-up 2026-05-29: status chip moved up into the
            top-right family badge. Footer kept ONLY for the legacy strategy
            (vintage line + status pill); v4.1 strategy emits no footer to
            avoid the duplicated-status reading the user flagged. */}
      {labelStrategy === "legacy" && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: "auto",
            paddingTop: "8px",
            borderTop: "1px solid rgba(255,255,255,0.04)",
          }}
        >
          <span
            style={{
              fontSize: "9.5px",
              color: "var(--qgi-text-dim)",
              letterSpacing: "0.3px",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {legacyVintage}
          </span>
          <span
            style={{
              fontSize: "9.5px",
              padding: "2px 7px",
              borderRadius: "10px",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
              background: statusMeta.bgAlpha,
              color: statusMeta.color,
              border: `1px solid ${statusMeta.color}`,
            }}
          >
            {statusMeta.label}
          </span>
        </div>
      )}
    </article>
  );

  // V4.1 follow-up 2026-05-29: "Coming soon" cards render the same chrome
  // wrapped in a plain <div>, not a Link — they're not yet shipped, so
  // there's no destination page worth navigating to.
  if (!linkable) {
    return (
      <div
        aria-disabled="true"
        title="This trend is not yet available"
        style={{ textDecoration: "none", color: "inherit", display: "block" }}
      >
        {cardChrome}
      </div>
    );
  }

  return (
    <Link
      href={`${basePath}/${recipe.recipe_id}` as Route}
      style={{
        textDecoration: "none",
        color: "inherit",
        display: "block",
      }}
    >
      {cardChrome}
    </Link>
  );
}

function chipStyle(
  kind: "num" | "fail" | "muted" | "legacy" | "purple" | "grey"
): React.CSSProperties {
  const base: React.CSSProperties = {
    fontSize: "10px",
    padding: "3px 7px",
    borderRadius: "3px",
    border: "1px solid var(--qgi-border)",
    background: "rgba(255,255,255,0.03)",
    color: "var(--qgi-text-muted)",
    fontFamily: "ui-monospace, monospace",
    letterSpacing: "0.3px",
  };
  if (kind === "num") return { ...base, color: "var(--qgi-text)" };
  if (kind === "fail")
    return {
      ...base,
      background: "rgba(230,69,69,0.15)",
      borderColor: "rgba(230,69,69,0.4)",
      color: "#E64545",
    };
  if (kind === "muted") return { ...base, opacity: 0.7 };
  if (kind === "legacy") return { ...base, borderColor: "#7A8FA0", color: "#7A8FA0" };
  if (kind === "purple")
    return { ...base, borderColor: "var(--qgi-accent)", color: "var(--qgi-accent)" };
  if (kind === "grey") return { ...base, color: "var(--qgi-text-dim)" };
  return base;
}

function dotStyle(color: string): React.CSSProperties {
  return {
    width: "7px",
    height: "7px",
    borderRadius: "50%",
    background: color,
    display: "inline-block",
  };
}
