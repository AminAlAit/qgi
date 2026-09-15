"use client";

import Link from "next/link";
import type { Route } from "next";
import {
  AdvisoryOnlyCallout,
  ConcentrationAlertCallout,
  FRuleAnomalyCallout,
  InterpretationHintBadge,
  NotMeasuredHint,
} from "@/components/ml/Callouts";
import { SectionLabel } from "@/components/v2/SectionLabel";
import { filterDemographic3 } from "@/lib/demographic-3-suppression";
import type { BuyerMlRecipe } from "@/lib/buyer-view";
import type { RecipeAggregated } from "@/lib/recipes-aggregated";
import indexesData from "@/data/indexes.json";
import {
  buildIndicatorNameLookup,
  isBakedUnknown,
} from "@/lib/indicator-numeric-supplement";

/**
 * #748 PR-2 (#750) — Merged precedent dossier (2026-05-17).
 *
 * Per the ratified Majles brief at
 * `docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-17-precedents-revised.md`
 * §3. One template for all four LOCKed ML recipes. Single scroll, no
 * tabs, no toggle, no template-switching.
 *
 * Fuses two prior surfaces:
 *   - V2 detail (PrecedentsV2Detail) — ML adjudication (Tier + OOC AUC
 *     + calibration + anchor)
 *   - V1 detail (PrecedentSlugClient) — statistical substrate
 *     (PPS / instances / OECD / indicator fingerprint)
 *
 * The ML/Stat seam is a LABELLED BOUNDARY, not a visual partition
 * (Tomás synthesizer rule). Adjudication block carries the
 * `[Verified — adjudicated]` label; the substrate block carries the
 * `[Verified — substrate]` label.
 *
 * Section sequence (10 sections; spec §3.1):
 *   1. Header (breadcrumb · tier · architecture · LOCKed chip · H1 +
 *      interpretation hint badge)
 *   2. Critical disclosures (advisory-only / F-rule / concentration —
 *      preserved from V2, banner style)
 *   3. Adjudication block (one framed section, three measurements:
 *      Discrimination + Calibration + Anchor stability — synthesized
 *      under one heading per Marcus + Roshani)
 *   4. Mechanism (Ingrid voice; pre-#683 = buyer-cleaned excerpt with
 *      curation-pending footnote)
 *   5. How to use this (renamed from "Buyer-disclosure recommendation")
 *   6. Statistical substrate — the MERGE (one framed section, four
 *      sub-blocks: PPS band + instances + OECD + indicator fingerprint
 *      top-3 with full-fingerprint details expander)
 *   7. Historical instance sample (deferred — bake pending)
 *   8. Top countries currently scoring on this recipe (cross-family,
 *      wired from the leaderboard component the caller passes in)
 *   9. Open follow-ups (collapsible) + Methodology cross-ref (collapsible)
 *  10. Footer (See related ranked patterns → /patterns?sort=loco_auc;
 *      How we validated this → /methodology; no lineage chip — every
 *      dossier is the same lineage now)
 */

// ---------------------------------------------------------------------------
// Indicator-name lookup (#470 item 2 pattern — once-at-module-load,
// O(1) per render)
// ---------------------------------------------------------------------------

// Base: indexes.json (curated 259-entry catalog).
// Overlay: indicator-numeric-supplement (21 legacy ids the Athena
// recipes_aggregated bake still emits but indexes.json no longer
// covers — see lib/indicator-numeric-supplement.ts for the root-cause
// write-up). The supplement only fills gaps; it never overwrites
// indexes.json entries.
const INDICATOR_NAME_BY_ID = buildIndicatorNameLookup(
  (indexesData as Array<{ numeric_id: number; name: string }>)
    .filter((idx) => typeof idx.numeric_id === "number" && idx.name)
    .map((idx) => [idx.numeric_id, idx.name] as const)
);

// ---------------------------------------------------------------------------
// Tier colors (ML rubric)
// ---------------------------------------------------------------------------

const TIER_COLORS: Record<BuyerMlRecipe["tier"], string> = {
  STRONG: "#22c55e",
  MODERATE: "#fbbf24",
  MARGINAL: "#a3a3a3",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface PrecedentMergedDossierProps {
  /** Buyer-view of the ML recipe (already jargon-cleaned, slug-rewritten). */
  recipe: BuyerMlRecipe;
  /** Statistical aggregate from `recipes-aggregated.json` for the matched event_category. */
  substrate: RecipeAggregated;
  /** Bake generation timestamp (passed to footer). */
  generatedAt: string;
  /** External href to the methodology paper anchor for this recipe. */
  paperHref: string;
  /** Cross-family leaderboard slot — caller passes the rendered component (or null). */
  leaderboardSlot?: React.ReactNode;
}

export function PrecedentMergedDossier({
  recipe,
  substrate,
  generatedAt,
  paperHref,
  leaderboardSlot,
}: PrecedentMergedDossierProps) {
  const tierColor = TIER_COLORS[recipe.tier];

  // M5 phase 1 (Asas Majles 2026-05-01) — Demographic 3 suppression on
  // the substrate's indicator_fingerprint, preserved verbatim from V1.
  const visibleFingerprint = filterDemographic3(substrate.indicator_fingerprint);
  // Spec §3.1 §6.4 — top-3 at-a-glance; full list behind <details>.
  const fingerprintTop3 = visibleFingerprint.slice(0, 3);
  const fingerprintRest = visibleFingerprint.slice(3);

  return (
    <article className="p-8 max-w-3xl mx-auto">
      {/* ─── 1. Header ─────────────────────────────────────────────── */}
      <BreadcrumbNav recipeName={recipe.display_name} />
      <header className="mb-6">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <TierPill tier={recipe.tier} color={tierColor} />
          <span
            className="font-data text-xs"
            style={{ color: "var(--qgi-text-dim)" }}
            title={`Architecture code: ${recipe.architecture_raw}`}
          >
            {recipe.architecture_label} · Assignment confidence{" "}
            {recipe.assignment_confidence}
          </span>
          <span
            className="font-data text-[10px] tracking-wider uppercase rounded px-1.5 py-0.5"
            style={{
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
            title={`Validated under lock rubric on model ${recipe.model_version}`}
          >
            LOCKed {recipe.model_version}
          </span>
        </div>
        <h1 className="text-3xl font-semibold mb-3" style={{ color: "var(--qgi-text)" }}>
          {recipe.display_name}
        </h1>
        <InterpretationHintBadge style="lloyds" hint={recipe.interpretation_hint} />
      </header>

      {/* ─── 2. Critical disclosures ──────────────────────────────── */}
      <section
        className="mb-8"
        data-testid="critical-disclosures"
        aria-label="Critical disclosures"
      >
        {recipe.advisory_only_flag && (
          <AdvisoryOnlyCallout style="lloyds" nPosLoco={recipe.n_pos_loco} />
        )}
        {recipe.f_rule_anomaly_flag && <FRuleAnomalyCallout style="lloyds" />}
        <ConcentrationAlertCallout
          style="lloyds"
          level={recipe.concentration_alert_level}
          country={recipe.top_1_training_country}
          share={recipe.top_1_training_country_share}
        />
      </section>

      {/* ─── 3. Adjudication block (Marcus + Roshani synthesis) ──── */}
      <section
        className="mb-8 rounded-lg p-6"
        style={{
          backgroundColor: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
        }}
        aria-labelledby="adjudication-heading"
      >
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <h2
            id="adjudication-heading"
            className="text-[10px] tracking-widest uppercase font-semibold"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Adjudication
          </h2>
          {/* Sipho's labelled-boundary rule — ML side */}
          <span
            className="text-[9px] tracking-wider uppercase rounded px-1.5 py-0.5"
            style={{
              color: "var(--qgi-accent)",
              backgroundColor: "var(--qgi-accent-glow)",
              border: "1px solid var(--qgi-accent)",
            }}
            title="ML-adjudicated under the lock rubric — out-of-country discrimination, calibration audit, anchor stability check"
          >
            Verified — adjudicated
          </span>
          {/* Tier pill repeats here (Yuki: scroll position must never lose the headline) */}
          <TierPill tier={recipe.tier} color={tierColor} />
        </div>

        {/* 3a. Discrimination */}
        <div className="mb-6">
          <SectionLabel>Discrimination</SectionLabel>
          <div className="grid grid-cols-2 gap-6" data-testid="metrics-grid">
            <Metric
              label="Out-of-country"
              value={recipe.loco_auc.toFixed(4)}
              sub={`${recipe.n_pos_loco} held-out positive${
                recipe.n_pos_loco === 1 ? "" : "s"
              }`}
              tooltip="Discrimination score on countries the model never saw during training (0.5 = chance, 1.0 = perfect). LOCO AUC."
            />
            <Metric
              label="In-sample"
              value={recipe.in_sample_f2_auc.toFixed(4)}
              sub={`95% CI [${recipe.in_sample_f2_ci_lower.toFixed(
                3
              )}, ${recipe.in_sample_f2_ci_upper.toFixed(3)}]`}
              tooltip="Discrimination score on the training partition. F2 AUC weights recall more than precision (5x)."
            />
          </div>
        </div>

        {/* 3b. Calibration */}
        <div className="mb-6">
          <SectionLabel title="Average gap between predicted probability and observed frequency, in-sample. 0 = perfectly calibrated. ECE.">
            Calibration error{" "}
            <span style={{ color: "var(--qgi-text-muted)" }}>
              (target &lt; 0.02; &gt; 0.05 = unreliable)
            </span>
          </SectionLabel>
          <CalibrationTable recipe={recipe} />
          {recipe.zero_positive_cohort_flag && (
            <p className="text-xs mt-3" style={{ color: "var(--qgi-text-dim)" }}>
              Zero-positive cohort: {recipe.zero_positive_cohort_flag}
            </p>
          )}
        </div>

        {/* 3c. Anchor stability */}
        <div>
          <SectionLabel title="Anchor Health Index — robustness of the recipe to held-out anchor events">
            Anchor stability (per-recipe)
          </SectionLabel>
          {recipe.anchor_ahi_value !== null ? (
            <AnchorStabilityValue value={recipe.anchor_ahi_value} />
          ) : (
            <NotMeasuredHint
              style="lloyds"
              status={recipe.anchor_ahi_status}
              reason={recipe.anchor_ahi_reason}
            />
          )}
        </div>
      </section>

      {/* ─── 4. Mechanism ─────────────────────────────────────────── */}
      <section className="mb-8" aria-labelledby="mechanism-heading">
        <SectionLabel>
          <span id="mechanism-heading">Mechanism</span>
        </SectionLabel>
        <p className="text-sm leading-relaxed" style={{ color: "var(--qgi-text)" }}>
          {recipe.mechanism_narrative}
        </p>
        {recipe.mechanism_narrative === recipe.mechanism_narrative_excerpt && (
          <p className="text-[10px] mt-2 italic" style={{ color: "var(--qgi-text-dim)" }}>
            Hand-curation pending (#683). Buyer-cleaned excerpt above.
          </p>
        )}
      </section>

      {/* ─── 5. How to use this ───────────────────────────────────── */}
      <section className="mb-8" aria-labelledby="how-to-use-heading">
        <SectionLabel>
          <span id="how-to-use-heading">How to use this</span>
        </SectionLabel>
        <p className="text-sm leading-relaxed" style={{ color: "var(--qgi-text)" }}>
          <MarkdownBoldText text={recipe.buyer_disclosure_recommendation} />
        </p>
      </section>

      {/* ─── 6. Statistical substrate (THE MERGE) ─────────────────── */}
      <section
        className="mb-8 rounded-lg p-6"
        style={{
          backgroundColor: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
        }}
        aria-labelledby="substrate-heading"
      >
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <h2
            id="substrate-heading"
            className="text-[10px] tracking-widest uppercase font-semibold"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Statistical substrate
          </h2>
          {/* Sipho's labelled-boundary rule — Stat side */}
          <span
            className="text-[9px] tracking-wider uppercase rounded px-1.5 py-0.5"
            style={{
              color: "var(--qgi-text-muted)",
              backgroundColor: "var(--qgi-surface-2)",
              border: "1px solid var(--qgi-border)",
            }}
            title="The statistical fingerprint this recipe was promoted from. Carried forward inside the dossier so adjudication and substrate are not separate pages."
          >
            Verified — substrate
          </span>
        </div>

        {/* 6a. PPS bootstrap CI — Gates Rank 17 (Roberto R5 actuary
            recommendation, closes #782). Renamed from "PPS calibration
            band" to disambiguate from the MODEL calibration (ECE) shown
            in §3b above. Roberto: "the dossier already shows ECE = 0.006
            (excellent); the band below is the PPS sort-key bootstrap CI,
            not a model-calibration claim." */}
        <div className="mb-6">
          <SectionLabel title="Pattern strength — the composite quality metric the screen ranks on. Centerline is the recipe's observed value; band would show the 95% bootstrap CI when available. Distinct from the model calibration error (ECE) shown above.">
            Pattern strength bootstrap CI{" "}
            <span className="font-normal" style={{ color: "var(--qgi-text-dim)" }}>
              (distinct from model ECE above)
            </span>
          </SectionLabel>
          <PpsBand substrate={substrate} />
        </div>

        {/* 6b. Total instances + distinct country pairs */}
        <div className="mb-6">
          <SectionLabel>Historical base</SectionLabel>
          <div className="grid grid-cols-2 gap-6">
            <Metric
              label="Total instances"
              value={substrate.total_instances.toLocaleString()}
            />
            <Metric
              label="Distinct country pairs"
              value={substrate.n_distinct_country_pairs.toLocaleString()}
              sub="(post-dedup)"
            />
          </div>
        </div>

        {/* 6c. OECD coverage diagnostic */}
        <div className="mb-6">
          <SectionLabel title="OECD-vs-rest share in the recipe's instance set. When > 50%, the recipe leans toward OECD generalization patterns; non-OECD applicability is correspondingly weaker.">
            Coverage bias diagnostic
          </SectionLabel>
          <CoverageDiagnostic substrate={substrate} />
        </div>

        {/* 6d. Indicator fingerprint top-3 + full <details> */}
        <div>
          <SectionLabel title="Indicators ranked by TF-IDF — frequency × inverse-recipe-frequency. The substrate's fingerprint, not the model's SHAP importances (those are in the Adjudication block).">
            Indicator fingerprint
          </SectionLabel>
          {visibleFingerprint.length === 0 ? (
            <p className="text-xs" style={{ color: "var(--qgi-text-muted)" }}>
              No fingerprint data on this bake.
            </p>
          ) : (
            <>
              <IndicatorFingerprintRows
                rows={fingerprintTop3}
                totalInstances={substrate.total_instances}
              />
              {fingerprintRest.length > 0 && (
                <details className="mt-3">
                  <summary
                    className="cursor-pointer text-[11px] tracking-wide"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    See the full fingerprint ({visibleFingerprint.length} indicators)
                  </summary>
                  <div className="mt-3">
                    <IndicatorFingerprintRows
                      rows={fingerprintRest}
                      totalInstances={substrate.total_instances}
                      startRank={4}
                    />
                  </div>
                </details>
              )}
            </>
          )}
        </div>
      </section>

      {/* ─── 7. Historical instance sample (QA N-2 fix, 2026-05-17) ──
           Section 7 of the spec is bake-pending — the aggregated bake
           doesn't yet expose instance-level rows. Per Sipho's disclosure
           standard, surface the deferred state explicitly rather than
           silently skipping the numbered section. */}
      <section className="mb-8" aria-labelledby="instance-sample-heading">
        <SectionLabel>
          <span id="instance-sample-heading">Historical instance sample</span>
        </SectionLabel>
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className="text-[9px] tracking-wider uppercase rounded px-1.5 py-0.5"
            style={{
              color: "var(--qgi-text-muted)",
              backgroundColor: "var(--qgi-surface-2)",
              border: "1px solid var(--qgi-border)",
            }}
            title="The bake will populate a 5-row sample (country-pair · year · pattern length · event-in-window flag · 24px sparkline). Ships next bake."
          >
            Verified — pending
          </span>
          <span className="text-xs" style={{ color: "var(--qgi-text-muted)" }}>
            Instance-level table (5-row sample with sparklines) populates on the next
            bake.
          </span>
        </div>
      </section>

      {/* ─── 8. Cross-family leaderboard (passed in by the page) ── */}
      {leaderboardSlot}

      {/* ─── 9. Open follow-ups + Methodology cross-ref ──────────── */}
      {recipe.open_followups.length > 0 && (
        <details className="mb-4">
          <summary
            className="cursor-pointer text-[11px] tracking-wide font-medium"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Open follow-ups ({recipe.open_followups.length})
          </summary>
          <ul className="text-sm space-y-2 mt-3">
            {recipe.open_followups.map((f, i) => (
              <li key={i} style={{ color: "var(--qgi-text)" }}>
                {f}
              </li>
            ))}
          </ul>
        </details>
      )}

      <details className="mb-6" data-testid="methodology-collapsible">
        <summary
          className="cursor-pointer text-[11px] tracking-wide font-medium"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Methodology cross-ref (paper §4)
        </summary>
        <p
          className="text-sm leading-relaxed mt-3"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Full tear-sheet with cohort-stratified calibration table, methodology-locked
          architecture rule, and replication signature lives in the buyer-disclosure
          paper.{" "}
          <a
            href={paperHref}
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
            style={{ color: "var(--qgi-text)" }}
          >
            Open paper §4 (external) →
          </a>
        </p>
      </details>

      {/* ─── 10. Footer ──────────────────────────────────────────── */}
      <footer
        className="pt-6 mt-8 text-xs"
        style={{
          color: "var(--qgi-text-dim)",
          borderTop: "1px solid var(--qgi-border)",
        }}
      >
        <p className="mb-1">
          Model version: <span className="font-data">{recipe.model_version}</span> ·
          Generated <span className="font-data">{generatedAt}</span>
        </p>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
          <Link
            href={"/patterns?sort=loco_auc" as Route}
            className="underline hover:text-[var(--qgi-accent)] transition-colors"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            See related ranked patterns →
          </Link>
          <Link
            href="/methodology"
            className="underline hover:text-[var(--qgi-accent)] transition-colors"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            How we validated this →
          </Link>
        </div>
      </footer>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function BreadcrumbNav({ recipeName }: { recipeName: string }) {
  return (
    <nav
      className="mb-4 text-xs"
      style={{ color: "var(--qgi-text-dim)" }}
      aria-label="Breadcrumb"
    >
      <Link
        href="/"
        className="hover:text-[var(--qgi-accent)] transition-colors"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Home
      </Link>
      <span className="mx-1">/</span>
      <Link
        href="/trends"
        className="hover:text-[var(--qgi-accent)] transition-colors"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Precedents
      </Link>
      <span className="mx-1">/</span>
      <span aria-current="page" style={{ color: "var(--qgi-text-muted)" }}>
        {recipeName}
      </span>
    </nav>
  );
}

function TierPill({ tier, color }: { tier: BuyerMlRecipe["tier"]; color: string }) {
  return (
    <span
      className="inline-flex items-center rounded font-data font-semibold tracking-wider px-2 py-0.5 text-xs"
      style={{
        color,
        backgroundColor: `${color}18`,
        border: `1px solid ${color}40`,
      }}
    >
      {tier}
    </span>
  );
}

function Metric({
  label,
  value,
  sub,
  tooltip,
}: {
  label: string;
  value: string;
  sub?: string;
  tooltip?: string;
}) {
  // QA N-3: tooltip on outer wrapper so hovering the prominent value
  // fires it too (not just the dimmed label).
  return (
    <div title={tooltip}>
      <div
        className="font-data text-3xl font-semibold leading-tight"
        style={{ color: "var(--qgi-text)" }}
      >
        {value}
      </div>
      <div
        className="text-[11px] tracking-wide mt-1"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        {label}
      </div>
      {sub && (
        <div
          className="text-[10px] font-data mt-0.5"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

function MarkdownBoldText({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**")) {
          return <strong key={i}>{p.slice(2, -2)}</strong>;
        }
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

function CalibrationTable({ recipe }: { recipe: BuyerMlRecipe }) {
  const rows: Array<{ tier: string; value: number; note?: string }> = [
    { tier: "Overall", value: recipe.in_sample_f1_ece },
    { tier: "High", value: recipe.ece_high_cohort, note: "fragile-state cohort" },
    { tier: "Mid", value: recipe.ece_mid_cohort },
    { tier: "Low", value: recipe.ece_low_cohort },
  ];
  return (
    <table
      className="w-full text-sm font-data"
      data-testid="calibration-table"
      style={{ borderCollapse: "collapse" }}
    >
      <tbody>
        {rows.map((r) => {
          const status = r.value <= 0.02 ? "good" : r.value <= 0.05 ? "warn" : "bad";
          const valueColor =
            status === "good"
              ? "var(--qgi-text)"
              : status === "warn"
                ? "#a16207"
                : "#b91c1c";
          return (
            <tr key={r.tier} style={{ borderTop: "1px solid var(--qgi-border)" }}>
              <td
                className="py-1.5 pr-4 text-xs"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                {r.tier}
                {r.note && (
                  <>
                    {" "}
                    <span
                      className="text-[10px]"
                      style={{ color: "var(--qgi-text-muted)" }}
                    >
                      {r.note}
                    </span>
                  </>
                )}
              </td>
              <td
                className="py-1.5 text-right tabular-nums"
                style={{ color: valueColor }}
              >
                {r.value.toFixed(4)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function AnchorStabilityValue({ value }: { value: number }) {
  const status: "stable" | "caution" | "unstable" =
    value <= 0.15 ? "stable" : value <= 0.25 ? "caution" : "unstable";
  const statusColor =
    status === "stable" ? "#16a34a" : status === "caution" ? "#a16207" : "#b91c1c";
  const statusLabel =
    status === "stable" ? "stable" : status === "caution" ? "caution" : "unstable";
  return (
    <div className="flex items-baseline gap-3 flex-wrap">
      <span
        className="font-data text-3xl font-semibold leading-tight tabular-nums"
        style={{ color: "var(--qgi-text)" }}
      >
        {value.toFixed(4)}
      </span>
      <span
        className="inline-flex items-center gap-1.5 text-[11px] tracking-wide"
        style={{ color: statusColor }}
        title="Backtest variance across held-out anchor folds. Thresholds: < 0.15 stable; 0.15–0.25 caution; > 0.25 unstable."
      >
        <span
          aria-hidden="true"
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: statusColor }}
        />
        {statusLabel}
      </span>
      <span className="text-[10px] font-data" style={{ color: "var(--qgi-text-muted)" }}>
        threshold 0.15 stable / 0.25 unstable
      </span>
    </div>
  );
}

/**
 * PPS band placeholder. The bake doesn't yet expose a calibration-band
 * field on RecipeAggregated (per the brief §7 risk callout — "If the
 * band field is absent in recipes-aggregated.json for the four LOCKed
 * slugs, render the centerline only with a `[Calibration band: bake
 * pending]` inline label.").
 *
 * Renders a Sipho `[Verified — pending]`-shaped chip plus the substrate's
 * instance count as the centerline context — no canonical_length number.
 * (2026-05-17 founder directive: canonical_length is hidden from the
 * four LOCKed precedents until/unless the bake ships a real calibration
 * band. The numeric still lives on `substrate.canonical_length` for
 * back-end consumers and the bake script.)
 */
function PpsBand({ substrate }: { substrate: RecipeAggregated }) {
  // Dashed-border placeholder block — signals "data ships here in a
  // future bake" with proper visual weight. Per QA PR-94 nit:
  // collapsing the prior `text-2xl` centerline (which used
  // canonical_length, now hidden per founder directive) into two
  // muted elements left the section reading like a placeholder for a
  // placeholder. A dashed-border bake-pending block is the honest
  // semantic — "data ships here in a future bake" — and gives the
  // section the structural anchor it needs.
  return (
    <div
      className="rounded-md px-4 py-4 flex items-center justify-between gap-4 flex-wrap"
      style={{
        backgroundColor: "var(--qgi-surface-2)",
        border: "1px dashed var(--qgi-border)",
      }}
      title="Bootstrap CI on the pattern-strength score will populate when the next bake ships the field. The 95% bootstrap CI replaces this placeholder once available. Distinct from the model ECE (calibration error) shown in the model-calibration section above."
    >
      <div className="flex flex-col gap-0.5">
        <span
          className="text-[9px] tracking-widest uppercase font-semibold"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          PPS bootstrap CI
        </span>
        <span className="text-sm" style={{ color: "var(--qgi-text-muted)" }}>
          Bake pending — populates with a 95% bootstrap CI in the next bake
        </span>
      </div>
      <span
        className="font-data text-[11px] tabular-nums"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        across {substrate.total_instances.toLocaleString()} instances
      </span>
    </div>
  );
}

function CoverageDiagnostic({ substrate }: { substrate: RecipeAggregated }) {
  const oecdShare = substrate.coverage_bias_diagnostic.oecd_share;
  const oecdPct = (oecdShare * 100).toFixed(0);
  const skewsOecd = oecdShare > 0.5;
  return (
    <div>
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <span
          className="font-data text-2xl font-semibold leading-tight tabular-nums"
          style={{ color: "var(--qgi-text)" }}
        >
          {oecdPct}%
        </span>
        <span className="text-xs" style={{ color: "var(--qgi-text-muted)" }}>
          OECD share across {substrate.coverage_bias_diagnostic.n_pairs} pairs
        </span>
      </div>
      {skewsOecd && (
        <p className="text-xs" style={{ color: "var(--qgi-amber)" }}>
          Coverage skews OECD — interpret with caution for non-OECD contexts; non-OECD
          generalization is correspondingly weaker.
        </p>
      )}
      {substrate.coverage_bias_diagnostic.regional_concentration.length > 0 && (
        <div className="mt-3 space-y-1">
          {substrate.coverage_bias_diagnostic.regional_concentration.map((r) => (
            <div key={r.region} className="flex items-center gap-3 text-[11px]">
              <div className="w-32 truncate" style={{ color: "var(--qgi-text-muted)" }}>
                {r.region}
              </div>
              <div
                className="flex-1 h-1.5 rounded-sm"
                style={{ backgroundColor: "var(--qgi-surface-2)" }}
              >
                <div
                  className="h-full rounded-sm"
                  style={{
                    width: `${r.share * 100}%`,
                    backgroundColor: "var(--qgi-accent)",
                    opacity: 0.7,
                  }}
                />
              </div>
              <div
                className="w-10 text-right tabular-nums font-data"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                {(r.share * 100).toFixed(0)}%
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function IndicatorFingerprintRows({
  rows,
  totalInstances,
  startRank = 1,
}: {
  rows: RecipeAggregated["indicator_fingerprint"];
  totalInstances: number;
  startRank?: number;
}) {
  return (
    <div className="space-y-2">
      {rows.map((ind, i) => {
        const rank = startRank + i;
        // Resolution priority: curated catalog (indexes.json + supplement)
        // > baked name (if not the "(unknown N)" placeholder) > generic.
        // Guarding against `isBakedUnknown` keeps a future bake-script
        // gap from leaking the raw placeholder string to readers.
        const fromCatalog = INDICATOR_NAME_BY_ID.get(ind.indicator_id);
        const bakedName = ind.indicator_name;
        const displayName =
          fromCatalog ??
          (bakedName && !isBakedUnknown(bakedName) ? bakedName : undefined) ??
          `Indicator ${ind.indicator_id}`;
        const ciSpread = ind.ci_upper - ind.ci_lower;
        return (
          <div key={ind.indicator_id} className="flex items-center gap-3 text-[12px]">
            <div
              className="w-6 text-right font-data text-[10px]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              {rank}.
            </div>
            <div className="w-48 truncate" title={displayName}>
              {displayName}
            </div>
            <div
              className="flex-1 h-3 rounded-sm relative"
              style={{ backgroundColor: "var(--qgi-surface-2)" }}
              title={`95% CI: ${(ind.ci_lower * 100).toFixed(0)}–${(
                ind.ci_upper * 100
              ).toFixed(0)}%`}
            >
              <div
                className="absolute h-full rounded-sm"
                style={{
                  left: `${ind.ci_lower * 100}%`,
                  width: `${ciSpread * 100}%`,
                  backgroundColor: "var(--qgi-accent)",
                  opacity: 0.25,
                }}
              />
              <div
                className="absolute h-full rounded-sm"
                style={{
                  left: `${Math.max(0, (ind.frequency - 0.005) * 100)}%`,
                  width: `1%`,
                  backgroundColor: "var(--qgi-accent)",
                  opacity: 0.95,
                }}
              />
            </div>
            <div
              className="w-12 text-right tabular-nums font-data"
              style={{ color: "var(--qgi-text-muted)" }}
              title={`${Math.round(
                ind.frequency * totalInstances
              )} of ${totalInstances.toLocaleString()} instances`}
            >
              {(ind.frequency * 100).toFixed(0)}%
            </div>
            <div
              className="w-14 text-right tabular-nums font-data text-[10px]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              ±{(ciSpread * 50).toFixed(0)}pp
            </div>
          </div>
        );
      })}
    </div>
  );
}
