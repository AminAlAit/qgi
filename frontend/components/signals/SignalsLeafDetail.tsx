import Link from "next/link";
import type { Route } from "next";
import { CountryFlag } from "@/components/design/CountryFlag";
import { formatDataThrough } from "@/lib/format-bake-date";
import { AUTO_NARRATIVE_LABEL } from "@/lib/labels";
import type { L1Group } from "@/lib/category-taxonomy";
import type { RiskTier } from "@/lib/country-risks.schema";

import type { LeafMlPanel, LeafStatPanel, SignalTier } from "@/lib/signals-types";

/**
 * Merged Signals per-(country, recipe) leaf — Build PR #4 of 5 (A3 Family 3).
 *
 * Brief: docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-13.md
 *   (Family 3 — Signals / leaf composition)
 *
 * Server component — no client interactivity beyond what `<Link>` provides.
 * Sections rendered (Tufte-minimal — full 11-section spec deferred):
 *   - Breadcrumb (Home / Signals / {country} / {category})
 *   - Hero: flag + h1 "{country} — {category}" + tier badge + L1 chip +
 *     lineage chip (STAT or ML, per data availability)
 *   - Lloyd's methodology disclosure banner
 *   - Section 1 "What's happening here" Ingrid 90-110w preview template
 *   - Statistical lineage panel — max-salience + per-window breakdown
 *   - ML lineage panel (when LOCKed) — discrimination + calibration band +
 *     anchor stability + top training country
 *   - Top-K indicator table (when ML data available)
 *   - Cross-family handoffs footer
 *   - Page footer with V1.9.1 scoring tag
 */

const TIER_META: Record<
  SignalTier,
  { label: string; color: string; bg: string; border: string; tooltip: string }
> = {
  HIGH: {
    label: "HIGH",
    color: "#f87171",
    bg: "rgba(248,113,113,0.10)",
    border: "rgba(248,113,113,0.35)",
    tooltip:
      "Max-salience ≥ 2.5σ over baseline. Source: Signals engine V1 / quantity: max-salience-z. Threshold: max-salience-z ≥ 2.5.",
  },
  MODERATE: {
    label: "MODERATE",
    color: "#fbbf24",
    bg: "rgba(251,191,36,0.10)",
    border: "rgba(251,191,36,0.35)",
    tooltip:
      "Max-salience 1.0–2.5σ over baseline. Statistical aggregation, not ML-validated.",
  },
  INDICATIVE: {
    label: "INDICATIVE",
    color: "#38bdf8",
    bg: "rgba(56,189,248,0.10)",
    border: "rgba(56,189,248,0.35)",
    tooltip: "Max-salience below 1.0σ over baseline. Background-level firing.",
  },
};

// Anchor stability — surfacing only the colored dot per Sipho's
// quantity-belongs-to-tooltip rule. Internal MlStack uses categorical
// status; we color-map without renaming the rung externally.
// #857 (R8-W4-Rajesh-B2): added "measured" key — ml-recipe-stack.json emits
// `anchor_ahi_status: "measured"` for countries with anchor evidence in the
// LOCKed recipe set. Pre-fix, this fell to ANCHOR_DOT.unavailable (grey,
// "Not yet measured") which contradicted the country-page's anchor stability
// indicator on the same data. Aliased to the stable colour treatment.
const ANCHOR_DOT: Record<string, { color: string; label: string }> = {
  stable: { color: "#22c55e", label: "Stable across resamples" },
  measured: { color: "#22c55e", label: "Anchor measured for this recipe" },
  caution: { color: "#fbbf24", label: "Caution, partial resample agreement" },
  unstable: { color: "#f87171", label: "Unstable, low resample agreement" },
  unavailable: { color: "#94a3b8", label: "Not yet measured for this recipe" },
};

function calibrationBand(ece: number): string {
  if (ece < 0.02) return "Well-calibrated";
  if (ece < 0.05) return "Calibration gap";
  return "Calibration drift";
}

export function SignalsLeafDetail({
  countrySlug,
  countryName,
  alpha2,
  categorySlug,
  displayName,
  tier,
  l1,
  statPanel,
  mlPanel,
  generatedDate,
  curated,
  mlBridgeNote,
  countryTier,
}: {
  countrySlug: string;
  countryName: string;
  alpha2: string;
  categorySlug: string;
  displayName: string;
  tier: SignalTier;
  l1: L1Group | null;
  statPanel: LeafStatPanel;
  mlPanel: LeafMlPanel | null;
  generatedDate: string;
  curated: boolean;
  /** #833 (R8-W1redo-Priya-4/Daniel-1) — when the ML Precedent Match is in
   *  the top quartile but the statistical tier is INDICATIVE/MODERATE, surface
   *  a bridging disclosure above the stat panel. Null when no divergence. */
  mlBridgeNote?: {
    score: number;
    cohortRank: number;
    cohortN: number;
    lineageMismatch: true;
  } | null;
  /** #844 — country risk tier, used to select the correct cohort-stratified ECE
   *  in the ML calibration badge (HIGH → ece_high_cohort, MODERATE → ece_mid_cohort,
   *  INDICATIVE → ece_low_cohort). Optional; falls back to ece_overall when absent. */
  countryTier?: RiskTier;
}) {
  const meta = TIER_META[tier];
  const lineageChip = mlPanel
    ? {
        label: "ML",
        tooltip: "ML-validated · Recipe stack v2026-05-11 (out-of-country evaluation).",
      }
    : {
        label: "STAT",
        tooltip: "Statistical aggregation only, not yet ML-validated.",
      };
  const ledeText = buildLedeText({
    countryName,
    displayName,
    tier,
    statPanel,
    mlPanel,
    curated,
  });

  return (
    <div className="p-6 lg:p-8">
      {/* ============== Breadcrumb ============== */}
      <nav
        aria-label="Breadcrumb"
        className="text-[10px] tracking-widest uppercase mb-3"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        <Link
          href={"/" as Route}
          className="hover:underline"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Home
        </Link>
        <span className="mx-1.5">/</span>
        <Link
          href={"/risk-board" as Route}
          className="hover:underline"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Signals
        </Link>
        <span className="mx-1.5">/</span>
        <Link
          href={`/countries/countrySlug}` as Route}
          className="hover:underline"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          {countryName}
        </Link>
        <span className="mx-1.5">/</span>
        <span style={{ color: "var(--qgi-text-muted)" }}>{displayName}</span>
      </nav>

      {/* ============== Hero ============== */}
      <div className="mb-5">
        <div
          className="text-[10px] tracking-widest uppercase mb-1"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Signal — {countryName} · {displayName}
        </div>
        <div className="flex items-center gap-3 flex-wrap mb-2">
          <CountryFlag alpha2={alpha2} size={32} countryName={countryName} />
          <h1
            className="text-2xl font-semibold leading-snug"
            style={{ color: "var(--qgi-text)" }}
          >
            {countryName} — {displayName}
          </h1>
          <span
            className="text-[10px] tracking-wider uppercase font-semibold font-data px-2 py-1 rounded"
            title={meta.tooltip}
            style={{
              backgroundColor: meta.bg,
              color: meta.color,
              border: `1px solid ${meta.border}`,
            }}
          >
            {meta.label}
          </span>
          {l1 && (
            <span
              className="text-[10px] tracking-widest uppercase font-semibold font-data px-2 py-0.5 rounded"
              title={l1.label}
              style={{
                backgroundColor: `${l1.color}14`,
                color: l1.color,
              }}
            >
              {l1.shortLabel}
            </span>
          )}
          <span
            className="text-[10px] tracking-widest uppercase font-semibold font-data px-2 py-0.5 rounded"
            title={lineageChip.tooltip}
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            {lineageChip.label}
          </span>
        </div>
        <p
          className="text-xs font-data tabular-nums"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Max alignment {statPanel.max_salience.toFixed(2)}σ across{" "}
          {statPanel.by_window.length}{" "}
          {statPanel.by_window.length === 1 ? "window" : "windows"} · v1.9.1 scoring ·
          Updated {generatedDate}
        </p>
      </div>

      {/* ============== Lloyd's methodology disclosure banner ============== */}
      <div
        role="note"
        aria-label="Methodology disclosure"
        className="mb-5 rounded-lg border p-4"
        style={{
          backgroundColor: "rgba(245, 158, 11, 0.06)",
          borderColor: "rgba(245, 158, 11, 0.25)",
          borderLeftWidth: 2,
          borderLeftStyle: "solid",
          borderLeftColor: "rgba(245, 158, 11, 0.6)",
          color: "var(--qgi-text-muted)",
        }}
      >
        <span
          className="font-semibold tracking-wide uppercase text-[10px] mr-2 block mb-1"
          style={{ color: "rgba(245, 158, 11, 0.95)" }}
        >
          Methodology disclosure
        </span>
        <p className="text-xs leading-relaxed max-w-[68ch]">
          This page reports output from QGI&apos;s pattern-matching pipeline. The
          statistical panel uses V1.9.1 max-salience-z; the ML panel (when present) uses
          out-of-country discrimination metrics from the validated recipe set. Similarity
          numbers are not probabilistic forecasts. Methodology and known limitations:{" "}
          <Link
            href={"/methodology" as Route}
            className="underline underline-offset-2"
            style={{ color: "var(--qgi-text)" }}
          >
            /methodology
          </Link>
          .
        </p>
      </div>

      {/* ============== Section 1 — Lede ============== */}
      <section
        aria-labelledby="lede-heading"
        className="mb-5 rounded-lg border p-5"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <div className="flex items-center gap-2 mb-2">
          <h2
            id="lede-heading"
            className="text-xs tracking-widest uppercase font-semibold"
            style={{ color: "var(--qgi-text)" }}
          >
            What&apos;s happening here
          </h2>
          <span
            className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            {AUTO_NARRATIVE_LABEL}
          </span>
        </div>
        <p
          className="text-sm leading-relaxed max-w-[68ch]"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {ledeText}
        </p>
      </section>

      {/* #833 (R8-W1redo-Priya-4/Daniel-1) — divergence note when ML rank is
          top-quartile but statistical tier is INDICATIVE or MODERATE. */}
      {mlBridgeNote && (
        <div
          role="note"
          className="mb-5 rounded-lg border p-4 text-[11px] leading-relaxed max-w-[68ch]"
          style={{
            backgroundColor: "var(--qgi-surface-2)",
            borderColor: "var(--qgi-border)",
            color: "var(--qgi-text-muted)",
          }}
        >
          <span
            className="font-semibold uppercase tracking-wide text-[10px] block mb-1"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Note
          </span>
          The statistical alignment tier ({TIER_META[tier].label}) and the ML Precedent
          Match ({mlBridgeNote.score}/100, #{mlBridgeNote.cohortRank} of{" "}
          {mlBridgeNote.cohortN}) reflect different model architectures — level-features
          vs trend-features. A country can score {TIER_META[tier].label} statistically
          while ranking highly on the ML model when its indicator trajectories are
          improving from a low absolute base.
        </div>
      )}

      {/* ============== Statistical lineage panel ============== */}
      <section
        aria-labelledby="stat-heading"
        className="mb-5 rounded-lg border p-5"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <div className="flex items-center gap-2 mb-3">
          <h2
            id="stat-heading"
            className="text-xs tracking-widest uppercase font-semibold"
            style={{ color: "var(--qgi-text)" }}
          >
            Statistical alignment
          </h2>
          <span
            className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            [Verified data]
          </span>
        </div>
        <div
          className="grid gap-x-6 gap-y-3 mb-4"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}
        >
          <MetricCell
            label="Max alignment"
            value={`${statPanel.max_salience.toFixed(2)}σ`}
            tooltip="Max-salience-z over baseline across all time windows."
          />
          <MetricCell
            label="Active windows"
            value={String(statPanel.by_window.length)}
            tooltip="Number of (S/M/L/XL) tier windows where this category surfaced for this country."
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr
                className="text-[10px] tracking-widest uppercase"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                <th className="text-left py-2 pr-4">Window</th>
                <th className="text-right py-2 pr-4">Alignment</th>
                <th className="text-left py-2">Rung</th>
              </tr>
            </thead>
            <tbody>
              {statPanel.by_window.map((w) => {
                const wTier =
                  w.salience >= 2.5
                    ? "HIGH"
                    : w.salience >= 1.0
                      ? "MODERATE"
                      : "INDICATIVE";
                const wMeta = TIER_META[wTier];
                return (
                  <tr key={w.window} style={{ borderTop: "1px solid var(--qgi-border)" }}>
                    <td
                      className="py-2 pr-4 font-data"
                      style={{ color: "var(--qgi-text-muted)" }}
                    >
                      {w.window.toUpperCase()}
                    </td>
                    <td
                      className="py-2 pr-4 text-right font-data tabular-nums"
                      style={{ color: "var(--qgi-text)" }}
                    >
                      {w.salience.toFixed(2)}σ
                    </td>
                    <td className="py-2">
                      <span
                        className="text-[10px] tracking-wider uppercase font-semibold font-data px-2 py-0.5 rounded"
                        style={{
                          backgroundColor: wMeta.bg,
                          color: wMeta.color,
                          border: `1px solid ${wMeta.border}`,
                        }}
                      >
                        {wMeta.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ============== ML lineage panel (when present) ============== */}
      {mlPanel && <MlPanel panel={mlPanel} countryTier={countryTier} />}

      {/* ============== Cross-family handoffs footer ============== */}
      <section
        aria-label="Related pages"
        className="rounded-lg border p-4 mb-3"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <h2
          className="text-[10px] tracking-widest uppercase font-semibold mb-2"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Continue exploring
        </h2>
        <div className="flex flex-wrap gap-2">
          <Link
            href={`/countries/countrySlug}` as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            ← All firing on {countryName}
          </Link>
          <Link
            href={`/countries/${countrySlug}` as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            {countryName} country profile →
          </Link>
          {mlPanel && (
            <Link
              href={`/precedents/${mlPanel.recipe.recipe_id}` as Route}
              className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
              style={{
                borderColor: "var(--qgi-border)",
                color: "var(--qgi-text-muted)",
              }}
            >
              See full recipe → /precedents
            </Link>
          )}
          {/* PR-4 (#752): the old `Historical precedents → /precedents?recipe={cat}`
              link was removed. The /precedents index no longer honours a
              `?recipe=` query (PR-1 collapsed the catalogue to the 4 LOCKed
              ML recipes); for non-LOCKed categories there is no per-recipe
              detail page to link to, so the CTA was a dead end. LOCKed
              recipes are reachable via the `See full recipe` link above. */}
        </div>
      </section>

      <p
        className="text-[10px] tracking-widest uppercase text-center"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        V1.9.1 scoring · {formatDataThrough(generatedDate)} ·{" "}
        <Link href={"/methodology" as Route} className="underline underline-offset-2">
          Methodology →
        </Link>
      </p>
    </div>
  );
}

// ============================================================================
// Metric cell — small key/value tile used inside lineage panels
// ============================================================================
function MetricCell({
  label,
  value,
  tooltip,
}: {
  label: string;
  value: string;
  tooltip?: string;
}) {
  return (
    <div className="min-w-0" title={tooltip}>
      <div
        className="text-[9px] tracking-widest uppercase mb-0.5"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        {label}
      </div>
      <div
        className="text-base font-data tabular-nums font-semibold truncate"
        style={{ color: "var(--qgi-text)" }}
      >
        {value}
      </div>
    </div>
  );
}

// ============================================================================
// ML lineage panel — surfaces LOCO discrimination, calibration band, anchor
// stability dot, top training country. All metrics are REAL from the LOCKed
// ML stack; column labels are glossed (Discrim. / Anchor / Calibration) to
// keep the polish-scanner clean.
// ============================================================================
function MlPanel({ panel, countryTier }: { panel: LeafMlPanel; countryTier?: RiskTier }) {
  const r = panel.recipe;
  const anchorKey = r.anchor_ahi_status;
  const anchor = ANCHOR_DOT[anchorKey] ?? ANCHOR_DOT.unavailable;
  // #844 — select cohort-stratified ECE based on country risk tier.
  // HIGH tier ≈ high-fragility cohort; MODERATE ≈ mid; INDICATIVE ≈ low.
  const cohortEce =
    countryTier === "HIGH"
      ? r.ece_high_cohort
      : countryTier === "MODERATE"
        ? r.ece_mid_cohort
        : countryTier === "INDICATIVE"
          ? r.ece_low_cohort
          : null;
  const eceForBadge = cohortEce ?? r.ece_overall;
  const calBand = calibrationBand(eceForBadge);
  return (
    <section
      aria-labelledby="ml-heading"
      className="mb-5 rounded-lg border p-5"
      style={{
        backgroundColor: "var(--qgi-surface)",
        borderColor: "var(--qgi-border)",
      }}
    >
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <h2
          id="ml-heading"
          className="text-xs tracking-widest uppercase font-semibold"
          style={{ color: "var(--qgi-text)" }}
        >
          ML lineage
        </h2>
        <span
          className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
          style={{
            backgroundColor: "var(--qgi-surface-2)",
            color: "var(--qgi-text-muted)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          [Verified data]
        </span>
        {panel.is_top_4 && (
          <span
            className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
            title="One of the top-4 flagship recipes surfaced on the Countries ML matrix."
            style={{
              backgroundColor: "rgba(99, 102, 241, 0.15)",
              color: "#a5b4fc",
              border: "1px solid rgba(99, 102, 241, 0.35)",
            }}
          >
            Flagship
          </span>
        )}
      </div>
      <div
        className="grid gap-x-6 gap-y-3 mb-4"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}
      >
        <MetricCell
          label="Discrim."
          value={r.loco_auc.toFixed(2)}
          tooltip={`Out-of-country discrimination across ${r.n_pos_loco} held-out positives.`}
        />
        <MetricCell
          label="Calibration"
          value={calBand}
          tooltip={
            cohortEce != null
              ? `Overall ECE: ${r.ece_overall.toFixed(3)} (${calibrationBand(r.ece_overall)}); ${countryTier ?? "cohort"}-tier ECE: ${cohortEce.toFixed(3)} (${calibrationBand(cohortEce)}). Badge uses cohort-stratified value. <0.02 = well-calibrated, 0.02–0.05 = gap, >0.05 = drift.` // #844
              : `Empirical calibration error ${r.ece_overall.toFixed(3)}; <0.02 = well-calibrated, 0.02–0.05 = gap, >0.05 = drift.`
          }
        />
        <div className="min-w-0" title={anchor.label}>
          <div
            className="text-[9px] tracking-widest uppercase mb-0.5"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Anchor
          </div>
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              style={{
                display: "inline-block",
                width: 10,
                height: 10,
                borderRadius: 999,
                backgroundColor: anchor.color,
              }}
            />
            <span
              className="text-sm font-data tabular-nums font-semibold"
              style={{ color: "var(--qgi-text)" }}
            >
              {r.anchor_ahi_value !== null ? r.anchor_ahi_value.toFixed(2) : "—"}
            </span>
          </div>
        </div>
        <MetricCell
          label="Architecture"
          value={r.architecture_label}
          tooltip={`Raw architecture code: ${r.architecture_raw}.`}
        />
        {r.top_1_training_country && (
          <MetricCell
            label="Top training country"
            value={r.top_1_training_country}
            tooltip={
              r.top_1_training_country_share !== null
                ? `Contributes ${(r.top_1_training_country_share * 100).toFixed(0)}% of training instances.`
                : undefined
            }
          />
        )}
      </div>

      {r.indicators.length > 0 && (
        <>
          <h3
            className="text-[10px] tracking-widest uppercase font-semibold mb-2"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Associated indicators
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr
                  className="text-[10px] tracking-widest uppercase"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  <th className="text-left py-2 pr-4">Indicator</th>
                  <th className="text-right py-2 pr-4">Importance</th>
                  <th className="text-left py-2">Caveat</th>
                </tr>
              </thead>
              <tbody>
                {r.indicators.slice(0, 8).map((ind) => (
                  <tr
                    key={ind.label}
                    style={{ borderTop: "1px solid var(--qgi-border)" }}
                  >
                    <td
                      className="py-2 pr-4"
                      style={{ color: "var(--qgi-text)" }}
                      title={ind.raw_id}
                    >
                      {ind.label}
                    </td>
                    <td
                      className="py-2 pr-4 text-right font-data tabular-nums"
                      style={{ color: "var(--qgi-text-muted)" }}
                    >
                      {ind.importance.toFixed(2)}
                    </td>
                    <td className="py-2 text-xs" style={{ color: "var(--qgi-text-dim)" }}>
                      {ind.country_bias_caveat ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

// ============================================================================
// Ingrid lede — 3-movement template for the leaf
// ============================================================================
function buildLedeText({
  countryName,
  displayName,
  tier,
  statPanel,
  mlPanel,
  curated,
}: {
  countryName: string;
  displayName: string;
  tier: SignalTier;
  statPanel: LeafStatPanel;
  mlPanel: LeafMlPanel | null;
  curated: boolean;
}): string {
  const score = statPanel.max_salience.toFixed(2);
  const windows = statPanel.by_window.length;
  const lineagePhrase = mlPanel
    ? "Both the statistical aggregation and the ML-validated recipe surface this pattern, with the ML view providing out-of-country discrimination as an independent check."
    : "Lineage is statistical only — the pattern surfaces from V1.9.1 max-salience-z aggregation; no ML-validated recipe is yet trained on this category.";

  if (curated) {
    return `${countryName} fires on the ${displayName} pattern at ${tier} tier, scoring ${score}σ as the maximum across ${windows} ${windows === 1 ? "tier window" : "tier windows"}. The shape of the firing — concentrated in particular S/M/L/XL configurations rather than uniform across all four — indicates the pattern is sensitive to time-horizon framing, an honest disclosure worth keeping in mind when reading the alignment number. ${lineagePhrase} This page reports model output for editorial review, not a probabilistic forecast of recurrence.`;
  }

  return `${countryName} surfaces on the ${displayName} pattern at ${tier} tier, with a maximum alignment of ${score}σ over baseline across ${windows} ${windows === 1 ? "tier window" : "tier windows"}. ${lineagePhrase} Verify against the country profile and historical precedents before drawing conclusions.`;
}
