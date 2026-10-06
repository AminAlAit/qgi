/**
 * /admin/trends — Full Trend Health Matrix (drill-down)
 *
 * Sections:
 *   A) Header stat row — totals + tier counts from getHeadlineVitals()
 *   B) THE MATRIX — all 69 Trends, walked first (cv-AUC desc), queued last
 *   C) n_pos LADDER — all walked recipes sorted asc; gate = 60
 *   D) cv-AUC histogram (client island, AdminTrendsCharts)
 *
 * Rules:
 *   - Async server component. Real data only — no mocks.
 *   - Charts in a "use client" island (AdminTrendsCharts.tsx).
 *   - typedRoutes: Link hrefs cast with `as Route`.
 *   - cv-AUC colour: >=0.78 success, 0.70-0.78 warning, <0.70 danger.
 *   - n_pos colour: >=80 success, 60-79 warning, <60 danger (below gate).
 *   - Queued rows muted; walked rows full-colour.
 *   - If a walked recipe has null nCountriesScored / topCountry, show "—".
 */

import { Fragment } from "react";
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { AdminPanel, AdminStat } from "@/components/admin/AdminPanel";
import {
  getHeadlineVitals,
  getTrendMatrix,
  getNposLadder,
  getAucReadyCount,
  NPOS_GATE,
  type TrendRow,
  type NposRow,
} from "@/lib/admin/admin-data";
import {
  AdminTrendsAucHistogram,
  type AucHistogramBuckets,
} from "@/components/admin/AdminTrendsCharts";

export const metadata: Metadata = {
  title: "Trends · QGI Admin",
  robots: { index: false, follow: false },
};

// ─── Colour helpers ──────────────────────────────────────────────────────────

function aucColor(auc: number | null): string {
  if (auc == null) return "var(--qgi-text-dim)";
  if (auc >= 0.78) return "var(--qgi-success)";
  if (auc >= 0.7) return "var(--qgi-warning)";
  return "var(--qgi-danger)";
}

function nposColor(n: number | null): string {
  if (n == null) return "var(--qgi-text-dim)";
  if (n >= 80) return "var(--qgi-success)";
  if (n >= NPOS_GATE) return "var(--qgi-warning)";
  return "var(--qgi-danger)";
}

function tierBadgeStyle(tier: string): CSSProperties {
  const base: CSSProperties = {
    display: "inline-block",
    padding: "1px 6px",
    borderRadius: "4px",
    fontSize: "10px",
    fontWeight: 700,
    letterSpacing: "0.5px",
    textTransform: "uppercase",
    fontFamily: "inherit",
  };
  switch (tier) {
    case "validated":
      return {
        ...base,
        background: "rgba(52,211,153,0.12)",
        color: "var(--qgi-success)",
      };
    case "directional":
      return {
        ...base,
        background: "rgba(251,191,36,0.12)",
        color: "var(--qgi-warning)",
      };
    case "experimental":
      return {
        ...base,
        background: "rgba(90,120,150,0.15)",
        color: "var(--qgi-text-muted)",
      };
    default: // queued
      return {
        ...base,
        background: "rgba(90,120,150,0.08)",
        color: "var(--qgi-text-dim)",
      };
  }
}

function statusBadgeStyle(status: string): CSSProperties {
  const base: CSSProperties = {
    display: "inline-block",
    padding: "1px 5px",
    borderRadius: "3px",
    fontSize: "10px",
    letterSpacing: "0.3px",
    fontFamily: "inherit",
  };
  switch (status) {
    case "graduated":
      return {
        ...base,
        background: "rgba(52,211,153,0.14)",
        color: "var(--qgi-success)",
      };
    case "live_legacy":
      return { ...base, background: "rgba(56,189,248,0.12)", color: "var(--qgi-accent)" };
    case "walked_no_graduation":
      return {
        ...base,
        background: "rgba(251,191,36,0.10)",
        color: "var(--qgi-warning)",
      };
    case "in_progress":
      return {
        ...base,
        background: "rgba(100,160,200,0.10)",
        color: "var(--qgi-text-muted)",
      };
    default: // queued
      return { ...base, background: "transparent", color: "var(--qgi-text-dim)" };
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "walked_no_graduation":
      return "walked";
    case "live_legacy":
      return "legacy";
    case "graduated":
      return "graduated";
    case "in_progress":
      return "in progress";
    default:
      return status;
  }
}

function fmtAuc(v: number | null): string {
  return v != null ? v.toFixed(3) : "—";
}

function fmtDelta(v: number | null): string {
  if (v == null || v === 0) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(1);
}

function deltaColor(v: number | null): string {
  if (v == null || v === 0) return "var(--qgi-text-dim)";
  if (Math.abs(v) >= 15) return v > 0 ? "var(--qgi-success)" : "var(--qgi-danger)";
  if (Math.abs(v) >= 8) return "var(--qgi-warning)";
  return "var(--qgi-text-muted)";
}

function verdictStyle(verdict: string | null): CSSProperties {
  if (!verdict) return { color: "var(--qgi-text-dim)", fontSize: "10px" };
  const v = verdict.toLowerCase();
  if (v.includes("strong") || v.includes("pass") || v.includes("validated"))
    return { color: "var(--qgi-success)", fontSize: "10px", fontWeight: 600 };
  if (v.includes("fail") || v.includes("insufficient") || v.includes("weak"))
    return { color: "var(--qgi-danger)", fontSize: "10px" };
  return { color: "var(--qgi-text-muted)", fontSize: "10px" };
}

/** Render the "pts to validated bar" cell value + color. */
function toValidatedCell(toValidated: number | null): { text: string; color: string } {
  if (toValidated == null) return { text: "—", color: "var(--qgi-text-dim)" };
  if (toValidated === 0) return { text: "✓ at bar", color: "var(--qgi-success)" };
  const pts = toValidated.toFixed(2);
  const color = toValidated <= 0.05 ? "var(--qgi-warning)" : "var(--qgi-text-dim)";
  return { text: `−${pts}`, color };
}

// ─── Matrix table row ────────────────────────────────────────────────────────

function MatrixRow({ row, stripe }: { row: TrendRow; stripe: boolean }) {
  const muted = !row.walked;
  const rowBg = stripe ? "rgba(255,255,255,0.025)" : "transparent";
  const textBase = muted ? "var(--qgi-text-dim)" : "var(--qgi-text)";
  const textMuted = muted ? "var(--qgi-text-dim)" : "var(--qgi-text-muted)";
  const toVal = toValidatedCell(row.toValidated);

  return (
    <tr style={{ background: rowBg, opacity: muted ? 0.65 : 1 }}>
      {/* Trend label — linked for walked rows */}
      <td
        style={{
          padding: "6px 10px 6px 8px",
          color: textBase,
          fontSize: "12px",
          maxWidth: "200px",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          borderBottom: "1px solid var(--qgi-border)",
        }}
        title={row.label}
      >
        {row.walked ? (
          <Link
            href={`/admin/trends/${row.recipeId}` as Route}
            style={{
              color: "var(--qgi-accent)",
              textDecoration: "none",
              fontWeight: 500,
            }}
          >
            {row.label}
          </Link>
        ) : (
          row.label
        )}
      </td>

      {/* Family (l1) */}
      <td
        style={{
          padding: "6px 10px 6px 8px",
          borderBottom: "1px solid var(--qgi-border)",
          whiteSpace: "nowrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              display: "inline-block",
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: row.l1Color || "var(--qgi-text-dim)",
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: "11px",
              color: textMuted,
              maxWidth: "110px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={row.l1Label}
          >
            {row.l1Label}
          </span>
        </div>
      </td>

      {/* Status */}
      <td
        style={{
          padding: "6px 8px",
          borderBottom: "1px solid var(--qgi-border)",
          whiteSpace: "nowrap",
        }}
      >
        <span style={statusBadgeStyle(row.status)}>{statusLabel(row.status)}</span>
      </td>

      {/* Tier */}
      <td
        style={{
          padding: "6px 8px",
          borderBottom: "1px solid var(--qgi-border)",
          whiteSpace: "nowrap",
        }}
      >
        {row.walked ? (
          <span style={tierBadgeStyle(row.tier)}>{row.tier}</span>
        ) : (
          <span style={{ fontSize: "10px", color: "var(--qgi-text-dim)" }}>—</span>
        )}
      </td>

      {/* cv-AUC */}
      <td
        className="font-data"
        style={{
          padding: "6px 10px",
          textAlign: "right",
          borderBottom: "1px solid var(--qgi-border)",
          color: aucColor(row.locoAuc),
          fontWeight: row.locoAuc != null && row.locoAuc >= 0.78 ? 700 : 400,
          whiteSpace: "nowrap",
          fontSize: "12px",
        }}
      >
        {fmtAuc(row.locoAuc)}
      </td>

      {/* n_pos */}
      <td
        className="font-data"
        style={{
          padding: "6px 10px",
          textAlign: "right",
          borderBottom: "1px solid var(--qgi-border)",
          color: nposColor(row.nPos),
          whiteSpace: "nowrap",
          fontSize: "12px",
        }}
      >
        {row.nPos ?? "—"}
      </td>

      {/* Countries scored */}
      <td
        className="font-data"
        style={{
          padding: "6px 10px",
          textAlign: "right",
          borderBottom: "1px solid var(--qgi-border)",
          color: textMuted,
          whiteSpace: "nowrap",
          fontSize: "12px",
        }}
      >
        {row.nCountriesScored ?? "—"}
      </td>

      {/* Top country + score */}
      <td
        style={{
          padding: "6px 10px",
          borderBottom: "1px solid var(--qgi-border)",
          whiteSpace: "nowrap",
          maxWidth: "140px",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
        title={
          row.topCountry
            ? `${row.topCountry.name} — score ${row.topCountry.score.toFixed(0)}`
            : ""
        }
      >
        {row.topCountry ? (
          <span style={{ fontSize: "11px" }}>
            <span style={{ color: textBase }}>{row.topCountry.name}</span>
            <span
              className="font-data"
              style={{ color: "var(--qgi-accent)", marginLeft: "6px", fontSize: "11px" }}
            >
              {row.topCountry.score.toFixed(0)}
            </span>
          </span>
        ) : (
          <span style={{ color: "var(--qgi-text-dim)", fontSize: "11px" }}>—</span>
        )}
      </td>

      {/* Max Δ vs prior */}
      <td
        className="font-data"
        style={{
          padding: "6px 10px",
          textAlign: "right",
          borderBottom: "1px solid var(--qgi-border)",
          color: deltaColor(row.maxAbsDelta),
          whiteSpace: "nowrap",
          fontSize: "12px",
        }}
      >
        {fmtDelta(row.maxAbsDelta)}
      </td>

      {/* Verdict */}
      <td
        style={{
          padding: "6px 10px 6px 8px",
          borderBottom: "1px solid var(--qgi-border)",
          maxWidth: "140px",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={row.verdict ?? ""}
      >
        <span style={verdictStyle(row.verdict)}>{row.verdict ?? "—"}</span>
      </td>

      {/* → Validated */}
      <td
        className="font-data"
        style={{
          padding: "6px 10px",
          textAlign: "right",
          borderBottom: "1px solid var(--qgi-border)",
          color: toVal.color,
          fontWeight: toVal.text === "✓ at bar" ? 700 : 400,
          whiteSpace: "nowrap",
          fontSize: "11px",
        }}
      >
        {toVal.text}
      </td>
    </tr>
  );
}

// ─── n_pos Ladder row ────────────────────────────────────────────────────────

function LadderRow({ row, i, total }: { row: NposRow; i: number; total: number }) {
  const isLast = i === total - 1;
  const isAtGate = row.nPos === NPOS_GATE;
  const isBelowGate = row.nPos < NPOS_GATE;
  const barPct = Math.min(100, (row.nPos / (NPOS_GATE * 2.5)) * 100);
  const barColor = isBelowGate
    ? "var(--qgi-danger)"
    : row.nPos < 80
      ? "var(--qgi-warning)"
      : "var(--qgi-success)";
  const numColor = nposColor(row.nPos);
  const stripe = i % 2 === 1;

  return (
    <tr
      style={{
        background: stripe ? "rgba(255,255,255,0.025)" : "transparent",
        borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
        // highlight any at/under gate
        outline: isBelowGate || isAtGate ? "none" : "none",
      }}
    >
      {/* rank */}
      <td
        className="font-data"
        style={{
          padding: "6px 8px",
          color: "var(--qgi-text-dim)",
          fontSize: "10px",
          textAlign: "right",
          verticalAlign: "middle",
          width: "28px",
        }}
      >
        {i + 1}
      </td>
      {/* label */}
      <td
        style={{
          padding: "6px 12px 6px 4px",
          color: isBelowGate ? "var(--qgi-danger)" : "var(--qgi-text-muted)",
          fontSize: "12px",
          maxWidth: "200px",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          verticalAlign: "middle",
        }}
        title={row.label}
      >
        {isBelowGate && (
          <span
            style={{
              display: "inline-block",
              width: "5px",
              height: "5px",
              borderRadius: "50%",
              background: "var(--qgi-danger)",
              marginRight: "6px",
              marginBottom: "1px",
              verticalAlign: "middle",
              flexShrink: 0,
            }}
          />
        )}
        {row.label}
      </td>
      {/* n_pos value */}
      <td
        className="font-data"
        style={{
          padding: "6px 12px",
          color: numColor,
          fontWeight: 700,
          fontSize: "13px",
          textAlign: "right",
          verticalAlign: "middle",
          whiteSpace: "nowrap",
          width: "52px",
        }}
      >
        {row.nPos}
      </td>
      {/* cv-AUC */}
      <td
        className="font-data"
        style={{
          padding: "6px 12px",
          color: aucColor(row.locoAuc),
          fontSize: "12px",
          textAlign: "right",
          verticalAlign: "middle",
          whiteSpace: "nowrap",
          width: "60px",
        }}
      >
        {fmtAuc(row.locoAuc)}
      </td>
      {/* mini bar */}
      <td style={{ padding: "6px 8px", verticalAlign: "middle", width: "120px" }}>
        <div
          style={{
            position: "relative",
            height: "6px",
            background: "var(--qgi-surface-2)",
            borderRadius: "3px",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              height: "100%",
              width: `${barPct}%`,
              background: barColor,
              borderRadius: "3px",
              opacity: 0.8,
            }}
          />
          {/* gate tick at 40% (= NPOS_GATE / (NPOS_GATE * 2.5)) */}
          <div
            style={{
              position: "absolute",
              left: "40%",
              top: 0,
              height: "100%",
              width: "1px",
              background: "var(--qgi-text-dim)",
              opacity: 0.5,
            }}
          />
        </div>
      </td>
    </tr>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default async function TrendsPage() {
  const vitals = getHeadlineVitals();
  const rawMatrix = getTrendMatrix();
  const nposLadder = getNposLadder();
  const aucReadyCount = getAucReadyCount();

  // Sort: walked first (cv-AUC desc), queued last (alphabetically)
  const walked = rawMatrix
    .filter((r) => r.walked)
    .sort((a, b) => (b.locoAuc ?? -1) - (a.locoAuc ?? -1));
  const queued = rawMatrix
    .filter((r) => !r.walked)
    .sort((a, b) => a.label.localeCompare(b.label));
  const sortedMatrix = [...walked, ...queued];

  // cv-AUC histogram buckets (walked only)
  const buckets: AucHistogramBuckets = {
    under55: 0,
    b5565: 0,
    b6575: 0,
    over75: 0,
  };
  for (const r of walked) {
    const auc = r.locoAuc;
    if (auc == null) continue;
    if (auc < 0.55) buckets.under55++;
    else if (auc < 0.65) buckets.b5565++;
    else if (auc < 0.78) buckets.b6575++;
    else buckets.over75++;
  }

  // Derived
  const belowGate = nposLadder.filter((r) => r.nPos < NPOS_GATE).length;
  const atOrAboveGate = nposLadder.length - belowGate;

  const tc = vitals.tierCounts;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* ── Page heading ─────────────────────────────────────────────────── */}
      <div style={{ marginBottom: "4px" }}>
        <h1
          style={{
            margin: 0,
            fontSize: "18px",
            fontWeight: 700,
            color: "var(--qgi-text)",
            letterSpacing: "0.2px",
          }}
        >
          Trend Health Matrix
        </h1>
        <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--qgi-text-dim)" }}>
          All {vitals.trendsTotal} Trends — {vitals.trendsWalked} walked ·{" "}
          {vitals.trendsQueued} queued · run-{vitals.runIndex} ·{" "}
          {vitals.vintage.slice(0, 10)}
        </p>
      </div>

      {/* ── A) HEADER STAT ROW ───────────────────────────────────────────── */}
      <AdminPanel
        title="Trend Inventory"
        subtitle={`Total ${vitals.trendsTotal} · ${vitals.trendsWalked} walked · ${vitals.trendsQueued} queued · tier distribution · ${aucReadyCount} clear cv-AUC ≥ 0.78`}
        span={12}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
            gap: "20px",
          }}
        >
          <AdminStat label="Total Trends" value={vitals.trendsTotal} />
          <AdminStat
            label="Walked"
            value={vitals.trendsWalked}
            sub={`${((vitals.trendsWalked / vitals.trendsTotal) * 100).toFixed(0)}% of total`}
            tone="good"
          />
          <AdminStat
            label="Queued"
            value={vitals.trendsQueued}
            sub="no cv-AUC yet"
            tone="warn"
          />
          <AdminStat
            label="Validated"
            value={tc.validated ?? 0}
            sub={`graduated tier · ${aucReadyCount} clear cv-AUC ≥ 0.78`}
            tone={(tc.validated ?? 0) > 0 ? "good" : "dim"}
          />
          <AdminStat
            label="Directional"
            value={tc.directional ?? 0}
            sub="0.70–0.78"
            tone={(tc.directional ?? 0) > 0 ? "warn" : "dim"}
          />
          <AdminStat
            label="Experimental"
            value={tc.experimental ?? 0}
            sub="< 0.70"
            tone="dim"
          />
          <AdminStat
            label="Below n_pos gate"
            value={belowGate}
            sub={`gate = ${NPOS_GATE}`}
            tone={belowGate > 0 ? "bad" : "good"}
          />
          <AdminStat
            label="At/above gate"
            value={atOrAboveGate}
            sub="model trainable"
            tone={atOrAboveGate > 0 ? "good" : "dim"}
          />
        </div>
      </AdminPanel>

      {/* Grid for matrix + ladder */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(12, 1fr)",
          gap: "16px",
          alignItems: "start",
        }}
      >
        {/* ── B) THE MATRIX ─────────────────────────────────────────────── */}
        <AdminPanel
          title="Trend Health Matrix"
          subtitle={`${walked.length} walked (cv-AUC desc) + ${queued.length} queued · columns: label, family, status, tier, cv-AUC, n_pos, countries, top country, max Δ, verdict, → validated`}
          span={12}
          pad={false}
        >
          <div style={{ overflowX: "auto", width: "100%" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "12px",
                tableLayout: "auto",
              }}
            >
              <thead>
                <tr
                  style={{
                    background: "var(--qgi-surface-2)",
                    position: "sticky",
                    top: 0,
                    zIndex: 2,
                  }}
                >
                  {[
                    { label: "Trend", align: "left" },
                    { label: "Family", align: "left" },
                    { label: "Status", align: "left" },
                    { label: "Tier", align: "left" },
                    { label: "cv-AUC", align: "right" },
                    { label: "n_pos", align: "right" },
                    { label: "Ctrs", align: "right" },
                    { label: "Top country", align: "left" },
                    { label: "Max Δ", align: "right" },
                    { label: "Verdict", align: "left" },
                    { label: "→ Validated", align: "right" },
                  ].map((col) => (
                    <th
                      key={col.label}
                      style={{
                        padding: "8px 10px",
                        textAlign: col.align as CSSProperties["textAlign"],
                        color: "var(--qgi-text-dim)",
                        fontWeight: 600,
                        fontSize: "10px",
                        letterSpacing: "0.5px",
                        textTransform: "uppercase",
                        borderBottom: "1px solid var(--qgi-border)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {/* Divider between walked and queued */}
                {sortedMatrix.map((row, i) => {
                  const isFirstQueued =
                    !row.walked && i > 0 && sortedMatrix[i - 1].walked;
                  return (
                    <Fragment key={row.recipeId}>
                      {isFirstQueued && (
                        <tr>
                          <td
                            colSpan={11}
                            style={{
                              padding: "5px 10px",
                              background: "var(--qgi-bg)",
                              fontSize: "10px",
                              fontWeight: 600,
                              letterSpacing: "0.5px",
                              textTransform: "uppercase",
                              color: "var(--qgi-text-dim)",
                              borderBottom: "1px solid var(--qgi-border)",
                              borderTop: "2px solid var(--qgi-border)",
                            }}
                          >
                            Queued — no cv-AUC yet ({queued.length})
                          </td>
                        </tr>
                      )}
                      <MatrixRow row={row} stripe={i % 2 === 1} />
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          {/* Legend */}
          <div
            style={{
              display: "flex",
              gap: "20px",
              padding: "10px 12px",
              borderTop: "1px solid var(--qgi-border)",
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontSize: "10px", color: "var(--qgi-success)" }}>
              cv-AUC ≥ 0.78 = validated
            </span>
            <span style={{ fontSize: "10px", color: "var(--qgi-warning)" }}>
              0.70–0.78 = directional
            </span>
            <span style={{ fontSize: "10px", color: "var(--qgi-danger)" }}>
              &lt; 0.70 = experimental
            </span>
            <span
              style={{
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                marginLeft: "auto",
              }}
            >
              n_pos &lt; {NPOS_GATE} = below XGBoost trainability gate
            </span>
            <span style={{ fontSize: "10px", color: "var(--qgi-text-dim)" }}>
              Max Δ = largest |score change vs prior vintage| across scored countries
            </span>
            <span style={{ fontSize: "10px", color: "var(--qgi-success)" }}>
              → Validated: ✓ at bar = cv-AUC ≥ 0.78; −X = pts still needed; — = queued
            </span>
          </div>
        </AdminPanel>

        {/* ── C) n_pos LADDER ──────────────────────────────────────────── */}
        <AdminPanel
          title="n_pos Ladder"
          subtitle={`${nposLadder.length} walked Trends · asc — gate = ${NPOS_GATE} · below gate = model untrained`}
          span={4}
          pad={false}
        >
          <div style={{ overflowY: "auto", maxHeight: "480px" }}>
            <table
              style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}
            >
              <thead>
                <tr
                  style={{
                    background: "var(--qgi-surface-2)",
                    position: "sticky",
                    top: 0,
                  }}
                >
                  {[
                    { label: "#", align: "right" },
                    { label: "Trend", align: "left" },
                    { label: "n_pos", align: "right" },
                    { label: "AUC", align: "right" },
                    { label: "Bar", align: "left" },
                  ].map((col) => (
                    <th
                      key={col.label}
                      style={{
                        padding: "7px 8px",
                        textAlign: col.align as CSSProperties["textAlign"],
                        color: "var(--qgi-text-dim)",
                        fontWeight: 600,
                        fontSize: "10px",
                        letterSpacing: "0.5px",
                        textTransform: "uppercase",
                        borderBottom: "1px solid var(--qgi-border)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {nposLadder.map((row, i) => (
                  <LadderRow
                    key={row.recipeId}
                    row={row}
                    i={i}
                    total={nposLadder.length}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <div
            style={{
              padding: "8px 10px",
              borderTop: "1px solid var(--qgi-border)",
              fontSize: "10px",
              color: "var(--qgi-text-dim)",
            }}
          >
            Bar tick = gate ({NPOS_GATE}). Red dot + red label = below gate.
            {belowGate > 0 && (
              <span style={{ color: "var(--qgi-danger)", marginLeft: "6px" }}>
                {belowGate} below gate.
              </span>
            )}
          </div>
        </AdminPanel>

        {/* ── D) cv-AUC HISTOGRAM (client island) ──────────────────────── */}
        <AdminPanel
          title="cv-AUC Distribution"
          subtitle="Walked Trends only — bucket histogram"
          span={8}
        >
          <AdminTrendsAucHistogram buckets={buckets} walkedCount={walked.length} />
          <div
            style={{
              marginTop: "12px",
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "12px",
            }}
          >
            {(
              [
                { label: "< 0.55", count: buckets.under55, tone: "bad" as const },
                { label: "0.55–0.65", count: buckets.b5565, tone: "bad" as const },
                { label: "0.65–0.78", count: buckets.b6575, tone: "warn" as const },
                { label: "≥ 0.78", count: buckets.over75, tone: "good" as const },
              ] satisfies Array<{
                label: string;
                count: number;
                tone: "bad" | "warn" | "good";
              }>
            ).map((b) => (
              <AdminStat
                key={b.label}
                label={`AUC ${b.label}`}
                value={b.count}
                tone={b.count === 0 ? "dim" : b.tone}
              />
            ))}
          </div>
        </AdminPanel>
      </div>
      {/* /grid */}
    </div>
  );
}
