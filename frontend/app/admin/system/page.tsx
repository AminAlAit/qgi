/**
 * /admin/system — System, Data Health & Deployment Lineage
 *
 * Sections:
 *   A) Machine Pulse   — live HTTP probe of qgintelligence.com
 *   B) Build Data Health — buildBytes vs 250 MB Vercel function limit
 *   C) Data Freshness  — getFreshnessClock() full table with age colouring
 *   D) Deployment Lineage — vintage + runIndex (real) + explicit "needs wiring" rows
 *   E) Cloud Reads Not Wired — honest panel; roadmap framing, zero fake numbers
 *
 * HARD RULES (from orchestrator):
 *   - All numbers come from the lib. Anything that requires a live cloud API is
 *     explicitly labelled "needs cloud read-role (not wired)" — never fabricated.
 *   - Async server component. No client-side JS unless absolutely required for a chart.
 */
import type { Metadata } from "next";
import { AdminPanel, AdminStat } from "@/components/admin/AdminPanel";
import { getHeadlineVitals, getFreshnessClock } from "@/lib/admin/admin-data";

export const metadata: Metadata = {
  title: "System · QGI Admin",
  robots: { index: false, follow: false },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtBytes(bytes: number): string {
  if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(2) + " GB";
  if (bytes >= 1_000_000) return (bytes / 1_000_000).toFixed(1) + " MB";
  if (bytes >= 1_024) return (bytes / 1_024).toFixed(0) + " KB";
  return bytes + " B";
}

/** Parse whatever date-ish string the artifact emits into a JS Date (or null). */
function parseDate(raw: string): Date | null {
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Days since a date (positive = past, negative = future). */
function daysAgo(d: Date): number {
  return Math.floor((Date.now() - d.getTime()) / 86_400_000);
}

function ageTone(days: number): "good" | "warn" | "bad" {
  if (days > 90) return "bad";
  if (days > 30) return "warn";
  return "good";
}

function ageLabel(days: number): string {
  if (days < 0) return `${Math.abs(days)}d ahead`;
  if (days === 0) return "today";
  if (days === 1) return "1 day ago";
  if (days < 60) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (days < 365) return `${weeks}w ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

/** Format bytes: good if <= 200 MB, warn <= 240 MB, bad > 240 MB */
function buildBytesTone(bytes: number): "good" | "warn" | "bad" {
  const mb = bytes / 1_000_000;
  if (mb > 240) return "bad";
  if (mb > 200) return "warn";
  return "good";
}

// ─── Section A: Machine Pulse — live HTTP probe ───────────────────────────────

interface PulseResult {
  ok: boolean;
  status: number | null;
  latencyMs: number | null;
  error: string | null;
}

async function probeLiveSite(): Promise<PulseResult> {
  const start = Date.now();
  try {
    const res = await fetch("https://qgintelligence.com", {
      signal: AbortSignal.timeout(3000),
      // HEAD avoids downloading the body; still triggers a full SSL + routing stack
      method: "HEAD",
      cache: "no-store",
    });
    return {
      ok: res.ok,
      status: res.status,
      latencyMs: Date.now() - start,
      error: null,
    };
  } catch (err: unknown) {
    return {
      ok: false,
      status: null,
      latencyMs: Date.now() - start,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

// ─── Tone helpers for pulse ───────────────────────────────────────────────────

function latencyTone(ms: number | null): "good" | "warn" | "bad" {
  if (ms === null) return "bad";
  if (ms <= 600) return "good";
  if (ms <= 1500) return "warn";
  return "bad";
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default async function SystemPage() {
  const [vitals, freshnessRows, pulse] = await Promise.all([
    Promise.resolve(getHeadlineVitals()),
    Promise.resolve(getFreshnessClock()),
    probeLiveSite(),
  ]);

  const VERCEL_LIMIT_BYTES = 250 * 1_000_000; // 250 MB
  const buildMb = (vitals.buildBytes / 1_000_000).toFixed(1);
  const limitPct = ((vitals.buildBytes / VERCEL_LIMIT_BYTES) * 100).toFixed(0);
  const buildTone = buildBytesTone(vitals.buildBytes);

  // Freshness rows enriched with parsed ages
  const enrichedRows = freshnessRows.map((row) => {
    const d = parseDate(row.date);
    const days = d ? daysAgo(d) : null;
    return {
      ...row,
      parsedDate: d,
      days,
      tone: days !== null ? ageTone(days) : ("bad" as const),
    };
  });

  return (
    <div>
      {/* Page heading */}
      <div style={{ marginBottom: "20px" }}>
        <h1
          style={{
            margin: 0,
            fontSize: "18px",
            fontWeight: 700,
            color: "var(--qgi-text)",
            letterSpacing: "0.2px",
          }}
        >
          System
        </h1>
        <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--qgi-text-dim)" }}>
          Data health, deployment lineage, and cloud observability gaps — run-
          {vitals.runIndex} · {vitals.vintage}
        </p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(12, 1fr)",
          gap: "16px",
        }}
      >
        {/* ── A: Machine Pulse ─────────────────────────────────────────── */}
        <AdminPanel
          title="Machine Pulse"
          subtitle="Live HTTP HEAD probe · qgintelligence.com · 3 s timeout"
          span={4}
          right={
            <span
              style={{
                fontSize: "10px",
                fontWeight: 600,
                letterSpacing: "0.6px",
                textTransform: "uppercase",
                color: pulse.ok ? "var(--qgi-success)" : "var(--qgi-danger)",
              }}
            >
              {pulse.ok ? "● LIVE" : "● DOWN"}
            </span>
          }
        >
          <div style={{ display: "flex", gap: "24px", flexWrap: "wrap" }}>
            <AdminStat
              label="HTTP Status"
              value={pulse.status ?? "—"}
              tone={pulse.ok ? "good" : "bad"}
              sub={pulse.error ? pulse.error.slice(0, 60) : undefined}
            />
            <AdminStat
              label="Latency"
              value={pulse.latencyMs !== null ? `${pulse.latencyMs} ms` : "—"}
              tone={latencyTone(pulse.latencyMs)}
              sub={
                pulse.latencyMs !== null
                  ? pulse.latencyMs <= 600
                    ? "fast"
                    : pulse.latencyMs <= 1500
                      ? "acceptable"
                      : "slow — check Vercel edge routing"
                  : "request failed or timed out"
              }
            />
          </div>
          <p
            style={{
              marginTop: "12px",
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              lineHeight: 1.5,
            }}
          >
            Probed at render time from the Next.js server process (localhost dev).
            Measures full-stack latency: DNS + TLS + Vercel edge + CDN cache. Not a
            substitute for an uptime monitor — this is a sanity signal only.
          </p>
        </AdminPanel>

        {/* ── B: Build Data Health ──────────────────────────────────────── */}
        <AdminPanel
          title="Build Data Health"
          subtitle="S3-fetched data committed to git · Vercel 250 MB function limit"
          span={4}
        >
          <div
            style={{
              display: "flex",
              gap: "24px",
              flexWrap: "wrap",
              marginBottom: "14px",
            }}
          >
            <AdminStat
              label="Build data size"
              value={`${buildMb} MB`}
              tone={buildTone}
              sub={`${limitPct}% of the 250 MB limit`}
            />
            <AdminStat
              label="Data files"
              value={vitals.buildFileCount}
              tone="default"
              sub="in build-manifest.json"
            />
          </div>

          {/* Visual bar: build size vs limit */}
          <div style={{ marginBottom: "10px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                marginBottom: "4px",
              }}
            >
              <span>0</span>
              <span>200 MB (warn)</span>
              <span>250 MB (limit)</span>
            </div>
            <div
              style={{
                position: "relative",
                height: "8px",
                background: "var(--qgi-surface-2)",
                borderRadius: "4px",
                overflow: "hidden",
              }}
            >
              {/* warn zone: 200–250 MB */}
              <div
                style={{
                  position: "absolute",
                  left: "80%",
                  width: "20%",
                  top: 0,
                  bottom: 0,
                  background: "rgba(251, 191, 36, 0.15)",
                }}
              />
              {/* actual fill */}
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${Math.min(100, (vitals.buildBytes / VERCEL_LIMIT_BYTES) * 100)}%`,
                  background:
                    buildTone === "good"
                      ? "var(--qgi-success)"
                      : buildTone === "warn"
                        ? "var(--qgi-warning)"
                        : "var(--qgi-danger)",
                  borderRadius: "4px",
                  transition: "width 0.3s",
                }}
              />
            </div>
          </div>

          <div
            style={{
              marginTop: "8px",
              padding: "8px 10px",
              background: "var(--qgi-bg)",
              borderRadius: "6px",
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              lineHeight: 1.5,
            }}
          >
            <strong style={{ color: "var(--qgi-text-muted)" }}>Vintage:</strong>{" "}
            <span className="font-data">{vitals.vintage}</span>
            <span style={{ margin: "0 8px", opacity: 0.4 }}>·</span>
            <strong style={{ color: "var(--qgi-text-muted)" }}>Run:</strong>{" "}
            <span className="font-data">run-{vitals.runIndex}</span>
            {buildTone !== "good" && (
              <p style={{ margin: "6px 0 0", color: "var(--qgi-warning)" }}>
                Approaching limit — consider moving more blobs to S3 build-fetch (#995
                indicator panels).
              </p>
            )}
          </div>
        </AdminPanel>

        {/* ── D: Deployment Lineage (top-right, 4 col) ──────────────────── */}
        <AdminPanel
          title="Deployment Lineage"
          subtitle="What we know locally · gaps marked explicitly"
          span={4}
        >
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "12px",
            }}
          >
            <thead>
              <tr>
                {["Field", "Value", "Source"].map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "4px 8px 6px",
                      fontSize: "10px",
                      fontWeight: 600,
                      letterSpacing: "0.5px",
                      textTransform: "uppercase",
                      color: "var(--qgi-text-dim)",
                      borderBottom: "1px solid var(--qgi-border)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* Real rows */}
              {[
                {
                  field: "TE fleet vintage",
                  value: vitals.vintage,
                  source: "te-fleet-run-2/MANIFEST",
                  real: true,
                },
                {
                  field: "Fleet run index",
                  value: `run-${vitals.runIndex}`,
                  source: "te-fleet-run-2/MANIFEST",
                  real: true,
                },
                {
                  field: "Trends walked",
                  value: `${vitals.trendsWalked} / ${vitals.trendsTotal}`,
                  source: "recipe-tracker.json",
                  real: true,
                },
                {
                  field: "Build data size",
                  value: fmtBytes(vitals.buildBytes),
                  source: "build-manifest.json",
                  real: true,
                },
              ].map((row) => (
                <tr key={row.field}>
                  <td
                    style={{
                      padding: "6px 8px",
                      color: "var(--qgi-text-muted)",
                      borderBottom: "1px solid var(--qgi-border)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {row.field}
                  </td>
                  <td
                    className="font-data"
                    style={{
                      padding: "6px 8px",
                      color: "var(--qgi-text)",
                      borderBottom: "1px solid var(--qgi-border)",
                    }}
                  >
                    {row.value}
                  </td>
                  <td
                    style={{
                      padding: "6px 8px",
                      color: "var(--qgi-text-dim)",
                      fontSize: "11px",
                      borderBottom: "1px solid var(--qgi-border)",
                      fontStyle: "italic",
                    }}
                  >
                    {row.source}
                  </td>
                </tr>
              ))}

              {/* Explicit "needs wiring" rows */}
              {[
                { field: "Vercel deploy SHA + deploy time", gap: "needs gh/Vercel API" },
                { field: "S3 build-fetch ETag", gap: "needs cloud read-role" },
              ].map((row) => (
                <tr key={row.field}>
                  <td
                    style={{
                      padding: "6px 8px",
                      color: "var(--qgi-text-dim)",
                      borderBottom: "1px solid var(--qgi-border)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {row.field}
                  </td>
                  <td
                    className="font-data"
                    style={{
                      padding: "6px 8px",
                      color: "var(--qgi-text-dim)",
                      borderBottom: "1px solid var(--qgi-border)",
                      fontStyle: "italic",
                    }}
                    colSpan={2}
                  >
                    — {row.gap}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </AdminPanel>

        {/* ── C: Data Freshness (full width) ───────────────────────────── */}
        <AdminPanel
          title="Data Freshness"
          subtitle="Age of each on-disk artifact · good < 30 d · warn 30–90 d · bad > 90 d"
          span={8}
        >
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <thead>
              <tr>
                {["Artifact", "Source file", "Last updated", "Age", ""].map((h, i) => (
                  <th
                    key={i}
                    style={{
                      textAlign: i === 3 || i === 4 ? "right" : "left",
                      padding: "4px 8px 6px",
                      fontSize: "10px",
                      fontWeight: 600,
                      letterSpacing: "0.5px",
                      textTransform: "uppercase",
                      color: "var(--qgi-text-dim)",
                      borderBottom: "1px solid var(--qgi-border)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {enrichedRows.map((row, i) => {
                const isLast = i === enrichedRows.length - 1;
                const rowStyle: React.CSSProperties = {
                  borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
                };
                const toneColor =
                  row.tone === "good"
                    ? "var(--qgi-success)"
                    : row.tone === "warn"
                      ? "var(--qgi-warning)"
                      : "var(--qgi-danger)";

                return (
                  <tr key={row.label}>
                    <td
                      style={{
                        ...rowStyle,
                        padding: "7px 8px",
                        color: "var(--qgi-text)",
                      }}
                    >
                      {row.label}
                    </td>
                    <td
                      style={{
                        ...rowStyle,
                        padding: "7px 8px",
                        color: "var(--qgi-text-dim)",
                        fontSize: "11px",
                        fontStyle: "italic",
                      }}
                    >
                      {row.source}
                    </td>
                    <td
                      className="font-data"
                      style={{
                        ...rowStyle,
                        padding: "7px 8px",
                        color: "var(--qgi-text-muted)",
                        whiteSpace: "nowrap",
                        textAlign: "right",
                      }}
                    >
                      {row.parsedDate
                        ? row.parsedDate.toISOString().slice(0, 10)
                        : row.date}
                    </td>
                    <td
                      className="font-data"
                      style={{
                        ...rowStyle,
                        padding: "7px 8px",
                        color: toneColor,
                        textAlign: "right",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {row.days !== null ? ageLabel(row.days) : "—"}
                    </td>
                    <td
                      style={{
                        ...rowStyle,
                        padding: "7px 8px",
                        textAlign: "right",
                        whiteSpace: "nowrap",
                      }}
                    >
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 6px",
                          borderRadius: "4px",
                          fontSize: "10px",
                          fontWeight: 600,
                          letterSpacing: "0.5px",
                          textTransform: "uppercase",
                          background:
                            row.tone === "good"
                              ? "rgba(52, 211, 153, 0.12)"
                              : row.tone === "warn"
                                ? "rgba(251, 191, 36, 0.12)"
                                : "rgba(248, 113, 113, 0.12)",
                          color: toneColor,
                        }}
                      >
                        {row.tone === "good"
                          ? "fresh"
                          : row.tone === "warn"
                            ? "aging"
                            : "stale"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </AdminPanel>

        {/* ── E: Cloud Reads Not Wired ──────────────────────────────────── */}
        <AdminPanel
          title="Cloud Reads Not Wired"
          subtitle="Signals that require a qgi-readonly role (qgi-aws-tf#809) — roadmap, not failures"
          span={4}
        >
          <p
            style={{
              margin: "0 0 12px",
              fontSize: "12px",
              color: "var(--qgi-text-muted)",
              lineHeight: 1.6,
            }}
          >
            The admin control room runs without live AWS or GCP credentials
            (founder-ratified contract #809). The items below will become real numbers
            once a scoped read-only cloud role is provisioned (tracked in qgi-infra #648).
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
            {[
              {
                service: "AWS Step Functions",
                signal: "Last pipeline run — start time, status, duration",
              },
              {
                service: "AWS SQS DLQ",
                signal: "Dead-letter depths per queue (ingestion + scoring fanout)",
              },
              {
                service: "CloudWatch / Lambda",
                signal: "Heartbeat timestamps, error counts, p99 duration",
              },
              {
                service: "AWS Budgets",
                signal: "Current-month $ spend vs budget alert threshold",
              },
              {
                service: "GCP / BigQuery",
                signal: "GDELT GPR BQ table row count + last-refresh timestamp",
              },
              {
                service: "Vercel API",
                signal: "Latest deploy SHA, deploy time, function size on the edge",
              },
            ].map((item, i, arr) => (
              <div
                key={item.service}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "10px",
                  padding: "9px 0",
                  borderBottom:
                    i < arr.length - 1 ? "1px solid var(--qgi-border)" : "none",
                }}
              >
                <span
                  style={{
                    marginTop: "2px",
                    display: "inline-block",
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    background: "var(--qgi-text-dim)",
                    flexShrink: 0,
                  }}
                />
                <div style={{ minWidth: 0 }}>
                  <span
                    className="font-data"
                    style={{
                      fontSize: "12px",
                      color: "var(--qgi-text-muted)",
                      fontWeight: 600,
                    }}
                  >
                    {item.service}
                  </span>
                  <p
                    style={{
                      margin: "2px 0 0",
                      fontSize: "11px",
                      color: "var(--qgi-text-dim)",
                      lineHeight: 1.5,
                    }}
                  >
                    {item.signal}
                  </p>
                </div>
                <span
                  style={{
                    marginLeft: "auto",
                    flexShrink: 0,
                    fontSize: "10px",
                    fontWeight: 600,
                    color: "var(--qgi-text-dim)",
                    letterSpacing: "0.4px",
                    fontStyle: "italic",
                  }}
                >
                  not wired
                </span>
              </div>
            ))}
          </div>
        </AdminPanel>
      </div>
    </div>
  );
}
