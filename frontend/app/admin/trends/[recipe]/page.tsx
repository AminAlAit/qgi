/**
 * /admin/trends/[recipe] — single Trend drill-down
 *
 * Async server component. Dynamic params are a Promise in Next.js 16.
 * Sections (using AdminPanel chrome):
 *   - Header: label + family + tier + verdict + description
 *   - MODEL: cv-AUC, CI ranges, toValidated, n_pos/neg, countries, window, walked_at, coverage
 *   - SHAP DRIVERS: horizontal bar chart (AdminTrendDetailShap client island)
 *   - GREEDY WALK: ordered step table
 *   - TOP COUNTRIES: score table
 *   - Back link → /admin/trends
 *
 * Rules:
 *   - No mocks. Every number from lib/admin/admin-data.ts.
 *   - Indicator codes → human names via lib/indicator-labels.ts (getIndicatorLabel).
 *   - typedRoutes: all Link hrefs cast with `as Route`.
 */

import type { Metadata } from "next";
import type { CSSProperties } from "react";
import Link from "next/link";
import type { Route } from "next";
import { notFound } from "next/navigation";
import { AdminPanel, AdminStat } from "@/components/admin/AdminPanel";
import { getTrendDetail } from "@/lib/admin/admin-data";
import { getIndicatorLabel } from "@/lib/indicator-labels";
import { AdminTrendDetailShap } from "@/components/admin/AdminTrendDetailShap";
import type { ShapDriver } from "@/components/admin/AdminTrendDetailShap";

export const metadata: Metadata = {
  title: "Trend Detail · QGI Admin",
  robots: { index: false, follow: false },
};

// ─── Colour helpers ───────────────────────────────────────────────────────────

function aucColor(auc: number | null): string {
  if (auc == null) return "var(--qgi-text-dim)";
  if (auc >= 0.78) return "var(--qgi-success)";
  if (auc >= 0.7) return "var(--qgi-warning)";
  return "var(--qgi-danger)";
}

function scoreColor(score: number): string {
  if (score >= 70) return "var(--qgi-danger)";
  if (score >= 50) return "var(--qgi-warning)";
  if (score >= 30) return "var(--qgi-text-muted)";
  return "var(--qgi-text-dim)";
}

function tierBadgeStyle(tier: string): CSSProperties {
  const base: CSSProperties = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: 700,
    letterSpacing: "0.5px",
    textTransform: "uppercase",
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
    default:
      return {
        ...base,
        background: "rgba(90,120,150,0.08)",
        color: "var(--qgi-text-dim)",
      };
  }
}

function verdictBadgeStyle(verdict: string | null): CSSProperties {
  const base: CSSProperties = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: 600,
  };
  if (!verdict) return { ...base, color: "var(--qgi-text-dim)" };
  const v = verdict.toLowerCase();
  if (v.includes("strong") || v.includes("pass") || v.includes("validated"))
    return { ...base, background: "rgba(52,211,153,0.10)", color: "var(--qgi-success)" };
  if (v.includes("fail") || v.includes("insufficient") || v.includes("weak"))
    return { ...base, background: "rgba(239,68,68,0.10)", color: "var(--qgi-danger)" };
  return { ...base, background: "rgba(251,191,36,0.10)", color: "var(--qgi-warning)" };
}

function coverageBadgeStyle(pass: boolean | null): CSSProperties {
  const base: CSSProperties = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: 600,
  };
  if (pass == null) return { ...base, color: "var(--qgi-text-dim)" };
  return pass
    ? { ...base, background: "rgba(52,211,153,0.10)", color: "var(--qgi-success)" }
    : { ...base, background: "rgba(239,68,68,0.10)", color: "var(--qgi-danger)" };
}

// ─── Subcomponents ────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize: "10px",
        fontWeight: 600,
        letterSpacing: "0.5px",
        textTransform: "uppercase",
        color: "var(--qgi-text-dim)",
      }}
    >
      {children}
    </span>
  );
}

function ThCell({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th
      style={{
        padding: "7px 10px",
        textAlign: right ? "right" : "left",
        color: "var(--qgi-text-dim)",
        fontWeight: 600,
        fontSize: "10px",
        letterSpacing: "0.5px",
        textTransform: "uppercase",
        borderBottom: "1px solid var(--qgi-border)",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </th>
  );
}

function TdCell({
  children,
  right,
  mono,
  style: extraStyle,
}: {
  children: React.ReactNode;
  right?: boolean;
  mono?: boolean;
  style?: CSSProperties;
}) {
  return (
    <td
      className={mono ? "font-data" : undefined}
      style={{
        padding: "6px 10px",
        textAlign: right ? "right" : "left",
        fontSize: "12px",
        color: "var(--qgi-text-muted)",
        borderBottom: "1px solid var(--qgi-border)",
        whiteSpace: "nowrap",
        ...extraStyle,
      }}
    >
      {children}
    </td>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default async function TrendDetailPage({
  params,
}: {
  params: Promise<{ recipe: string }>;
}) {
  const { recipe } = await params;
  const d = getTrendDetail(recipe);

  if (!d) notFound();

  // ── Queued (not walked) ──────────────────────────────────────────────────
  if (!d.walked) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
        <Link
          href={"/admin/trends" as Route}
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-dim)",
            textDecoration: "none",
          }}
        >
          ← All Trends
        </Link>
        <AdminPanel title={d.label} subtitle="Queued Trend — not yet walked" span={12}>
          <div style={{ padding: "24px 0", textAlign: "center" }}>
            <p style={{ margin: 0, fontSize: "14px", color: "var(--qgi-text-dim)" }}>
              This Trend is queued. No cv-AUC, SHAP data, or country scores are available
              yet.
            </p>
            <p
              style={{
                margin: "8px 0 0",
                fontSize: "12px",
                color: "var(--qgi-text-dim)",
              }}
            >
              Family:{" "}
              <strong style={{ color: d.family.color || "var(--qgi-text-muted)" }}>
                {d.family.label}
              </strong>
              &nbsp;·&nbsp;status: {d.status}
            </p>
          </div>
        </AdminPanel>
      </div>
    );
  }

  // ── Walked — full detail ──────────────────────────────────────────────────

  // Resolve SHAP drivers to human-readable names
  const shapDrivers: ShapDriver[] = d.shapDrivers.map((dr) => ({
    code: dr.code,
    weight: dr.weight,
    direction: dr.direction,
    label: getIndicatorLabel(dr.code),
  }));

  // toValidated display
  const toValText =
    d.toValidated == null
      ? "—"
      : d.toValidated === 0
        ? "✓ clears 0.78 bar"
        : `−${d.toValidated.toFixed(2)} pts to validated`;
  const toValColor =
    d.toValidated == null
      ? "var(--qgi-text-dim)"
      : d.toValidated === 0
        ? "var(--qgi-success)"
        : d.toValidated <= 0.05
          ? "var(--qgi-warning)"
          : "var(--qgi-text-muted)";

  const fmtCi = (pair: [number, number] | null) =>
    pair ? `[${pair[0].toFixed(3)}, ${pair[1].toFixed(3)}]` : "—";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* ── Back link ──────────────────────────────────────────────────────── */}
      <Link
        href={"/admin/trends" as Route}
        style={{
          fontSize: "12px",
          color: "var(--qgi-text-dim)",
          textDecoration: "none",
          alignSelf: "flex-start",
        }}
      >
        ← All Trends
      </Link>

      {/* ── HEADER ─────────────────────────────────────────────────────────── */}
      <AdminPanel span={12}>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {/* Title row */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              flexWrap: "wrap",
            }}
          >
            {/* Family color dot */}
            <span
              style={{
                display: "inline-block",
                width: "10px",
                height: "10px",
                borderRadius: "50%",
                background: d.family.color || "var(--qgi-text-dim)",
                flexShrink: 0,
              }}
              title={d.family.label}
            />
            <h1
              style={{
                margin: 0,
                fontSize: "20px",
                fontWeight: 700,
                color: "var(--qgi-text)",
                letterSpacing: "0.1px",
              }}
            >
              {d.label}
            </h1>
          </div>

          {/* Family + tier + verdict */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              flexWrap: "wrap",
            }}
          >
            <SectionLabel>{d.family.label}</SectionLabel>
            <span style={tierBadgeStyle(d.tier)}>{d.tier}</span>
            {d.verdict && <span style={verdictBadgeStyle(d.verdict)}>{d.verdict}</span>}
            <span
              style={{
                fontSize: "11px",
                color: "var(--qgi-text-dim)",
                fontFamily: "monospace",
              }}
            >
              {d.recipeId}
            </span>
          </div>

          {/* Description */}
          {d.description && (
            <p
              style={{
                margin: 0,
                fontSize: "13px",
                color: "var(--qgi-text-muted)",
                lineHeight: 1.6,
                maxWidth: "720px",
              }}
            >
              {d.description}
            </p>
          )}
        </div>
      </AdminPanel>

      {/* ── MODEL STATS ────────────────────────────────────────────────────── */}
      <AdminPanel
        title="Model"
        subtitle="XGBoost LOCO cross-validation metrics"
        span={12}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
            gap: "20px",
          }}
        >
          <AdminStat
            label="cv-AUC (LOCO)"
            value={
              <span style={{ color: aucColor(d.locoAuc) }}>
                {d.locoAuc != null ? d.locoAuc.toFixed(3) : "—"}
              </span>
            }
            sub={`95% CI ${fmtCi(d.ci95)}`}
            tone={
              d.locoAuc == null
                ? "dim"
                : d.locoAuc >= 0.78
                  ? "good"
                  : d.locoAuc >= 0.7
                    ? "warn"
                    : "bad"
            }
          />
          <AdminStat label="80% CI" value={fmtCi(d.ci80)} tone="dim" />
          <AdminStat
            label="→ Validated"
            value={
              <span style={{ color: toValColor, fontSize: "14px" }}>{toValText}</span>
            }
            tone="dim"
          />
          <AdminStat
            label="n_pos"
            value={d.nPos ?? "—"}
            sub="positive examples"
            tone={
              d.nPos == null
                ? "dim"
                : d.nPos >= 80
                  ? "good"
                  : d.nPos >= 60
                    ? "warn"
                    : "bad"
            }
          />
          <AdminStat
            label="n_neg"
            value={d.nNeg ?? "—"}
            sub="negative examples"
            tone="dim"
          />
          <AdminStat
            label="Countries scored"
            value={d.nCountriesScored ?? "—"}
            tone={d.nCountriesScored != null && d.nCountriesScored > 0 ? "good" : "dim"}
          />
          <AdminStat
            label="Chosen window"
            value={d.chosenWindow != null ? `${d.chosenWindow}y` : "—"}
            sub="greedy best window"
            tone="dim"
          />
          <AdminStat
            label="Coverage pass"
            value={
              <span style={coverageBadgeStyle(d.coveragePass)}>
                {d.coveragePass == null ? "—" : d.coveragePass ? "PASS" : "FAIL"}
              </span>
            }
            tone="dim"
          />
          <AdminStat
            label="Walked at"
            value={
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--qgi-text-dim)",
                  fontWeight: 400,
                }}
              >
                {d.walkedAt ? d.walkedAt.slice(0, 10) : "—"}
              </span>
            }
            tone="dim"
          />
        </div>
      </AdminPanel>

      {/* ── 2-column grid for SHAP + GREEDY WALK ─────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(12, 1fr)",
          gap: "16px",
          alignItems: "start",
        }}
      >
        {/* ── SHAP DRIVERS (client island) ─────────────────────────────── */}
        <AdminPanel
          title="SHAP Drivers"
          subtitle="Top-8 indicators by normalized SHAP weight · bar length ∝ weight"
          span={6}
        >
          <AdminTrendDetailShap drivers={shapDrivers} />
          {shapDrivers.length > 0 && (
            <div
              style={{
                marginTop: "10px",
                display: "flex",
                gap: "16px",
                fontSize: "10px",
                flexWrap: "wrap",
              }}
            >
              <span style={{ color: "var(--qgi-danger)" }}>risk ↑ = risk-increasing</span>
              <span style={{ color: "var(--qgi-success)" }}>
                risk ↓ = risk-decreasing
              </span>
              <span style={{ color: "var(--qgi-text-dim)" }}>
                neutral = direction unknown
              </span>
            </div>
          )}
        </AdminPanel>

        {/* ── GREEDY WALK ──────────────────────────────────────────────── */}
        <AdminPanel
          title="Greedy Walk"
          subtitle="Indicator selection steps (forward stepwise, best window per step)"
          span={6}
          pad={false}
        >
          {d.greedyWalk.length === 0 ? (
            <p
              style={{
                margin: 0,
                padding: "14px 16px",
                fontSize: "12px",
                color: "var(--qgi-text-dim)",
              }}
            >
              No greedy walk history available.
            </p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table
                style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}
              >
                <thead>
                  <tr style={{ background: "var(--qgi-surface-2)" }}>
                    <ThCell>#</ThCell>
                    <ThCell>Indicator</ThCell>
                    <ThCell right>Window</ThCell>
                    <ThCell right>AUC</ThCell>
                    <ThCell right>Lift</ThCell>
                  </tr>
                </thead>
                <tbody>
                  {d.greedyWalk.map((step, i) => {
                    const isLast = i === d.greedyWalk.length - 1;
                    const name = getIndicatorLabel(step.candidate);
                    return (
                      <tr
                        key={`gw-${step.step}-${i}`}
                        style={{
                          background:
                            i % 2 === 1 ? "rgba(255,255,255,0.02)" : "transparent",
                        }}
                      >
                        <TdCell
                          mono
                          style={{
                            color: "var(--qgi-text-dim)",
                            fontSize: "10px",
                            borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                          }}
                        >
                          {step.step}
                        </TdCell>
                        <TdCell
                          style={{
                            borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              flexDirection: "column",
                              gap: "1px",
                            }}
                          >
                            <span
                              style={{
                                color: "var(--qgi-text)",
                                fontSize: "11px",
                                maxWidth: "220px",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                              title={`${name} [${step.candidate}]`}
                            >
                              {name}
                            </span>
                            <span
                              style={{
                                color: "var(--qgi-text-dim)",
                                fontSize: "9px",
                                fontFamily: "monospace",
                                maxWidth: "220px",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {step.candidate}
                            </span>
                          </div>
                        </TdCell>
                        <TdCell
                          right
                          mono
                          style={{
                            borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                          }}
                        >
                          {step.window}y
                        </TdCell>
                        <TdCell
                          right
                          mono
                          style={{
                            color: aucColor(step.auc),
                            fontWeight: step.auc >= 0.78 ? 700 : 400,
                            borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                          }}
                        >
                          {step.auc.toFixed(3)}
                        </TdCell>
                        <TdCell
                          right
                          mono
                          style={{
                            color:
                              step.lift > 0.02
                                ? "var(--qgi-success)"
                                : step.lift > 0
                                  ? "var(--qgi-text-muted)"
                                  : "var(--qgi-danger)",
                            borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                          }}
                        >
                          {step.lift > 0 ? "+" : ""}
                          {step.lift.toFixed(3)}
                        </TdCell>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </AdminPanel>
      </div>
      {/* /2-column grid */}

      {/* ── TOP COUNTRIES ──────────────────────────────────────────────────── */}
      <AdminPanel
        title="Top Countries"
        subtitle="Top-10 by resemblance score · with top-3 SHAP driver contributions"
        span={12}
        pad={false}
      >
        {d.topCountries.length === 0 ? (
          <p
            style={{
              margin: 0,
              padding: "14px 16px",
              fontSize: "12px",
              color: "var(--qgi-text-dim)",
            }}
          >
            No country scores available. Needs cloud read-role wiring (S3/Athena).
          </p>
        ) : (
          <div style={{ overflowX: "auto" }}>
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
                  <ThCell>Rank</ThCell>
                  <ThCell>Country</ThCell>
                  <ThCell right>Score</ThCell>
                  <ThCell>Top drivers (SHAP share)</ThCell>
                </tr>
              </thead>
              <tbody>
                {d.topCountries.map((c, i) => {
                  const isLast = i === d.topCountries.length - 1;
                  return (
                    <tr
                      key={`tc-${c.name}-${i}`}
                      style={{
                        background:
                          i % 2 === 1 ? "rgba(255,255,255,0.02)" : "transparent",
                      }}
                    >
                      <TdCell
                        mono
                        style={{
                          color: "var(--qgi-text-dim)",
                          width: "40px",
                          borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                        }}
                      >
                        {c.rank}
                      </TdCell>
                      <TdCell
                        style={{
                          color: "var(--qgi-text)",
                          fontWeight: 500,
                          borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                        }}
                      >
                        {c.name}
                      </TdCell>
                      <TdCell
                        right
                        mono
                        style={{
                          color: scoreColor(c.score),
                          fontWeight: 700,
                          fontSize: "13px",
                          borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                        }}
                      >
                        {c.score.toFixed(0)}
                      </TdCell>
                      <TdCell
                        style={{
                          maxWidth: "380px",
                          borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                        }}
                      >
                        {c.drivers.length === 0 ? (
                          <span style={{ color: "var(--qgi-text-dim)" }}>—</span>
                        ) : (
                          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                            {c.drivers.map((dr, j) => {
                              const name = getIndicatorLabel(dr.code);
                              return (
                                <span
                                  key={`drv-${i}-${j}`}
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "4px",
                                    background: "var(--qgi-surface-2)",
                                    borderRadius: "3px",
                                    padding: "2px 6px",
                                    fontSize: "10px",
                                  }}
                                  title={`${name} [${dr.code}]`}
                                >
                                  <span
                                    style={{
                                      color: "var(--qgi-text-muted)",
                                      maxWidth: "160px",
                                      overflow: "hidden",
                                      textOverflow: "ellipsis",
                                      whiteSpace: "nowrap",
                                    }}
                                  >
                                    {name}
                                  </span>
                                  <span
                                    className="font-data"
                                    style={{ color: "var(--qgi-accent)", flexShrink: 0 }}
                                  >
                                    {dr.sharePct.toFixed(0)}%
                                  </span>
                                </span>
                              );
                            })}
                          </div>
                        )}
                      </TdCell>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </AdminPanel>

      {/* ── Selected indicators list ──────────────────────────────────────── */}
      {d.selectedIndicators.length > 0 && (
        <AdminPanel
          title="Selected Indicators"
          subtitle={`${d.selectedIndicators.length} indicators chosen by greedy walk`}
          span={12}
        >
          <div
            style={{
              display: "flex",
              gap: "8px",
              flexWrap: "wrap",
            }}
          >
            {d.selectedIndicators.map((code, i) => {
              const name = getIndicatorLabel(code);
              return (
                <span
                  key={`si-${code}-${i}`}
                  style={{
                    display: "inline-flex",
                    flexDirection: "column",
                    gap: "1px",
                    background: "var(--qgi-surface-2)",
                    borderRadius: "4px",
                    padding: "4px 8px",
                    fontSize: "11px",
                  }}
                  title={code}
                >
                  <span style={{ color: "var(--qgi-text-muted)" }}>{name}</span>
                  <span
                    style={{
                      color: "var(--qgi-text-dim)",
                      fontSize: "9px",
                      fontFamily: "monospace",
                    }}
                  >
                    {code}
                  </span>
                </span>
              );
            })}
          </div>
        </AdminPanel>
      )}

      {/* ── Back link (bottom) ───────────────────────────────────────────── */}
      <Link
        href={"/admin/trends" as Route}
        style={{
          fontSize: "12px",
          color: "var(--qgi-text-dim)",
          textDecoration: "none",
          alignSelf: "flex-start",
          marginBottom: "8px",
        }}
      >
        ← All Trends
      </Link>
    </div>
  );
}
