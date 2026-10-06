/**
 * Admin Control Room — Hub Overview
 *
 * The "80-second what do I do next?" view.
 * Server component: all data from real lib accessors, no mocks.
 * Client island: AdminFlywheelBar only.
 */
import Link from "next/link";
import type { Route } from "next";
import { AdminPanel, AdminStat } from "@/components/admin/AdminPanel";
import { AdminFlywheelBar } from "@/components/admin/AdminFlywheelBar";
import {
  getHeadlineVitals,
  getTrendMatrix,
  getFreshnessClock,
  getNposLadder,
  computeFlywheel,
  getAucReadyCount,
  NPOS_GATE,
} from "@/lib/admin/admin-data";
import { getCurationProgress, getXQueue } from "@/lib/admin/admin-content";

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmtBytes(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)} KB`;
  return `${n} B`;
}

function ageDays(dateStr: string): number {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return -1;
  return Math.floor((Date.now() - d.getTime()) / 86_400_000);
}

function freshnessTone(days: number): "good" | "warn" | "bad" {
  if (days < 0) return "bad";
  if (days > 90) return "bad";
  if (days > 30) return "warn";
  return "good";
}

function aucTone(auc: number | null): "good" | "warn" | "bad" | "dim" {
  if (auc == null) return "dim";
  if (auc >= 0.78) return "good";
  if (auc >= 0.7) return "warn";
  return "bad";
}

function nposTone(n: number): "good" | "warn" | "bad" {
  if (n >= 80) return "good";
  if (n >= NPOS_GATE) return "warn";
  return "bad";
}

function tierBadge(tier: string): string {
  switch (tier) {
    case "validated":
      return "V";
    case "directional":
      return "D";
    case "experimental":
      return "E";
    default:
      return "Q";
  }
}

// ─── V1: Machine Pulse — server-side liveness probe ─────────────────────────
async function probeLiveSite(): Promise<{
  ok: boolean;
  status: number | null;
  latencyMs: number | null;
}> {
  const t0 = Date.now();
  try {
    const res = await fetch("https://qgintelligence.com", {
      signal: AbortSignal.timeout(3000),
      method: "HEAD",
      cache: "no-store",
    });
    return { ok: res.ok, status: res.status, latencyMs: Date.now() - t0 };
  } catch {
    return { ok: false, status: null, latencyMs: null };
  }
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default async function AdminOverviewPage() {
  // Parallel data fetches
  const [cur, xq, probe] = await Promise.all([
    getCurationProgress(),
    getXQueue(),
    probeLiveSite(),
  ]);

  // Sync accessors
  const vitals = getHeadlineVitals();
  const matrix = getTrendMatrix();
  const freshness = getFreshnessClock();
  const nposLadder = getNposLadder();
  const aucReadyCount = getAucReadyCount();
  const fly = computeFlywheel({
    curationDone: cur.done,
    curationTotal: cur.total,
    xPostsThisWeek: xq.postedThisWeek,
  });

  // Derived
  const walkedTrends = matrix
    .filter((r) => r.walked)
    .sort((a, b) => (b.locoAuc ?? 0) - (a.locoAuc ?? 0));
  const top10 = walkedTrends.slice(0, 10);
  const nposBottom6 = nposLadder.slice(0, 6);

  const buildMB = vitals.buildBytes / 1_000_000;
  const buildLimitMB = 250;
  const buildPct = (buildMB / buildLimitMB) * 100;
  const buildTone: "good" | "warn" | "bad" =
    buildPct >= 90 ? "bad" : buildPct >= 70 ? "warn" : "good";

  const lastPostLabel = xq.lastPostAt ? `${ageDays(xq.lastPostAt)}d ago` : "never";

  // Top ~3 pending X posts for the queue preview (not posted/sent)
  const xPendingPreview: Array<{ type: string; slug: string; batch: string }> = [];
  for (const batch of xq.batches) {
    for (const item of batch.items) {
      if (item.status !== "posted" && item.status !== "sent") {
        xPendingPreview.push({ type: item.type, slug: item.slug, batch: batch.batch });
      }
      if (xPendingPreview.length >= 3) break;
    }
    if (xPendingPreview.length >= 3) break;
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* ── A) FLYWHEEL SCORE HEADER ──────────────────────────────────────── */}
      <AdminPanel
        title="QGI Flywheel Score"
        subtitle="0.30·trained + 0.25·curation + 0.20·median-AUC + 0.15·coverage + 0.10·X posts"
        span={12}
      >
        <AdminFlywheelBar score={fly.score} components={fly.components} />
      </AdminPanel>

      {/* ── B) 6-VITALS GRID — 2 rows × 3 cols ───────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: "16px",
        }}
      >
        {/* V1 — MACHINE PULSE */}
        {/* Visually dominant when live: success left-border + large HTTP status */}
        <section
          style={{
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderTop: "2px solid #5B7E99",
            borderLeft: probe.ok
              ? "4px solid var(--qgi-success)"
              : "4px solid var(--qgi-danger)",
            borderRadius: "8px",
            display: "flex",
            flexDirection: "column",
            minWidth: 0,
            overflow: "hidden",
          }}
        >
          <header
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: "12px",
              padding: "12px 16px",
              borderBottom: "1px solid var(--qgi-border)",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <h2
                style={{
                  margin: 0,
                  fontSize: "12px",
                  fontWeight: 600,
                  letterSpacing: "0.6px",
                  textTransform: "uppercase",
                  color: "var(--qgi-text)",
                }}
              >
                Machine Pulse
              </h2>
              <p
                style={{
                  margin: "2px 0 0",
                  fontSize: "11px",
                  color: "var(--qgi-text-dim)",
                }}
              >
                qgintelligence.com + build
              </p>
            </div>
            <span
              className="font-data"
              style={{
                fontSize: "11px",
                fontWeight: 700,
                color: probe.ok ? "var(--qgi-success)" : "var(--qgi-danger)",
                flexShrink: 0,
              }}
            >
              {probe.ok ? "● LIVE" : "● DOWN"}
            </span>
          </header>
          <div style={{ padding: "14px 16px", flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {/* Large HTTP status — the dominant signal */}
              <div
                style={{
                  display: "flex",
                  gap: "20px",
                  alignItems: "flex-end",
                  flexWrap: "wrap",
                }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                  <span
                    style={{
                      fontSize: "10px",
                      letterSpacing: "0.5px",
                      textTransform: "uppercase",
                      color: "var(--qgi-text-dim)",
                    }}
                  >
                    HTTP status
                  </span>
                  <span
                    className="font-data"
                    style={{
                      fontSize: "32px",
                      fontWeight: 700,
                      lineHeight: 1,
                      color: probe.ok ? "var(--qgi-success)" : "var(--qgi-danger)",
                    }}
                  >
                    {probe.ok
                      ? `${probe.status} OK`
                      : probe.status
                        ? `${probe.status} ERR`
                        : "unreachable"}
                  </span>
                </div>
                {probe.latencyMs != null && (
                  <AdminStat
                    label="Latency"
                    value={`${probe.latencyMs} ms`}
                    tone={
                      probe.latencyMs < 800
                        ? "good"
                        : probe.latencyMs < 2000
                          ? "warn"
                          : "bad"
                    }
                  />
                )}
                <AdminStat
                  label="Build vintage"
                  value={vitals.vintage.slice(0, 10)}
                  tone="default"
                />
              </div>

              {/* Muted cloud stubs */}
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <span style={{ fontSize: "10px", color: "var(--qgi-text-dim)" }}>
                  Vercel deploy SHA — needs gh/Vercel API
                </span>
                <span style={{ fontSize: "10px", color: "var(--qgi-text-dim)" }}>
                  Live-Pulse Lambda heartbeat — needs cloud read-role (not wired)
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* V2 — DATA FRESHNESS */}
        <AdminPanel title="Data Freshness" subtitle="Age of on-disk artifacts">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <tbody>
              {freshness.map((row) => {
                const days = ageDays(row.date);
                const tone = freshnessTone(days);
                const color =
                  tone === "good"
                    ? "var(--qgi-success)"
                    : tone === "warn"
                      ? "var(--qgi-warning)"
                      : "var(--qgi-danger)";
                return (
                  <tr
                    key={row.label}
                    style={{ borderBottom: "1px solid var(--qgi-border)" }}
                  >
                    <td
                      style={{
                        padding: "6px 0",
                        color: "var(--qgi-text-muted)",
                        maxWidth: "180px",
                      }}
                    >
                      {row.label}
                    </td>
                    <td
                      className="font-data"
                      style={{
                        padding: "6px 0 6px 8px",
                        color,
                        whiteSpace: "nowrap",
                        textAlign: "right",
                      }}
                    >
                      {days >= 0 ? `${days}d ago` : row.date.slice(0, 10)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </AdminPanel>

        {/* V3 — TREND HEALTH */}
        <AdminPanel
          title="Trend Health"
          subtitle={`Top 10 of ${walkedTrends.length} walked · cv-AUC desc`}
          right={
            <Link
              href={"/admin/trends" as Route}
              style={{
                fontSize: "11px",
                color: "var(--qgi-accent)",
                textDecoration: "none",
              }}
            >
              Full 69-Trend matrix →
            </Link>
          }
        >
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--qgi-border)" }}>
                {["Label", "AUC", "n+", "Tier", "Ctrs", "Top"].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: "0 4px 6px",
                      textAlign: h === "Label" ? "left" : "right",
                      color: "var(--qgi-text-dim)",
                      fontWeight: 500,
                      fontSize: "10px",
                      letterSpacing: "0.4px",
                      textTransform: "uppercase",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {top10.map((t) => {
                const aucColor =
                  aucTone(t.locoAuc) === "good"
                    ? "var(--qgi-success)"
                    : aucTone(t.locoAuc) === "warn"
                      ? "var(--qgi-warning)"
                      : aucTone(t.locoAuc) === "bad"
                        ? "var(--qgi-danger)"
                        : "var(--qgi-text-dim)";
                const nposColor =
                  t.nPos == null
                    ? "var(--qgi-text-dim)"
                    : nposTone(t.nPos) === "good"
                      ? "var(--qgi-success)"
                      : nposTone(t.nPos) === "warn"
                        ? "var(--qgi-warning)"
                        : "var(--qgi-danger)";
                return (
                  <tr
                    key={t.recipeId}
                    style={{ borderBottom: "1px solid var(--qgi-border)" }}
                  >
                    <td
                      style={{
                        padding: "5px 4px",
                        color: "var(--qgi-text)",
                        maxWidth: "120px",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={t.label}
                    >
                      {t.label}
                    </td>
                    <td
                      className="font-data"
                      style={{
                        padding: "5px 4px",
                        textAlign: "right",
                        color: aucColor,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {t.locoAuc != null ? t.locoAuc.toFixed(3) : "—"}
                    </td>
                    <td
                      className="font-data"
                      style={{ padding: "5px 4px", textAlign: "right", color: nposColor }}
                    >
                      {t.nPos ?? "—"}
                    </td>
                    <td
                      className="font-data"
                      style={{
                        padding: "5px 4px",
                        textAlign: "right",
                        color: "var(--qgi-text-muted)",
                        fontSize: "10px",
                      }}
                    >
                      {tierBadge(t.tier)}
                    </td>
                    <td
                      className="font-data"
                      style={{
                        padding: "5px 4px",
                        textAlign: "right",
                        color: "var(--qgi-text-muted)",
                      }}
                    >
                      {t.nCountriesScored ?? "—"}
                    </td>
                    <td
                      style={{
                        padding: "5px 4px",
                        textAlign: "right",
                        color: "var(--qgi-text-dim)",
                        fontSize: "10px",
                        maxWidth: "80px",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={
                        t.topCountry
                          ? `${t.topCountry.name} ${t.topCountry.score.toFixed(0)}`
                          : ""
                      }
                    >
                      {t.topCountry
                        ? `${t.topCountry.name} ${t.topCountry.score.toFixed(0)}`
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </AdminPanel>

        {/* V4 — n_pos GATE */}
        <AdminPanel title="n_pos Gate" subtitle={`Bottom 6 walked — gate = ${NPOS_GATE}`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {nposBottom6.map((row) => {
              const tone = nposTone(row.nPos);
              const barColor =
                tone === "good"
                  ? "var(--qgi-success)"
                  : tone === "warn"
                    ? "var(--qgi-warning)"
                    : "var(--qgi-danger)";
              const barPct = Math.min(100, (row.nPos / (NPOS_GATE * 2)) * 100);
              return (
                <div key={row.recipeId}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "baseline",
                      marginBottom: "3px",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "11px",
                        color: "var(--qgi-text-muted)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        maxWidth: "180px",
                      }}
                      title={row.label}
                    >
                      {row.label}
                    </span>
                    <span
                      className="font-data"
                      style={{
                        fontSize: "12px",
                        fontWeight: 600,
                        color: barColor,
                        flexShrink: 0,
                        marginLeft: "8px",
                      }}
                    >
                      {row.nPos}
                    </span>
                  </div>
                  {/* bar */}
                  <div
                    style={{
                      height: "5px",
                      borderRadius: "3px",
                      background: "var(--qgi-surface-2)",
                      position: "relative",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        top: 0,
                        height: "100%",
                        width: `${barPct}%`,
                        borderRadius: "3px",
                        background: barColor,
                        opacity: 0.8,
                      }}
                    />
                    {/* gate marker at 50% of bar (= NPOS_GATE) */}
                    <div
                      style={{
                        position: "absolute",
                        left: "50%",
                        top: "-2px",
                        height: "9px",
                        width: "1px",
                        background: "var(--qgi-text-dim)",
                        opacity: 0.6,
                      }}
                    />
                  </div>
                </div>
              );
            })}
            <p
              style={{
                margin: "4px 0 0",
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
              }}
            >
              Bar mid-point = gate ({NPOS_GATE}). Red = below gate (model untrained).
            </p>
          </div>
        </AdminPanel>

        {/* V5 — X QUEUE */}
        <AdminPanel
          title="X Queue"
          subtitle="Content outbox (localhost sibling repo)"
          right={
            <Link
              href={"/admin/content" as Route}
              style={{
                fontSize: "11px",
                color: "var(--qgi-accent)",
                textDecoration: "none",
              }}
            >
              Content hub →
            </Link>
          }
        >
          {!xq.present ? (
            <p style={{ margin: 0, fontSize: "12px", color: "var(--qgi-text-dim)" }}>
              outbox not on disk (localhost only — run from the qgi-6.0 root with docs-specs
              sibling present)
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                <AdminStat label="Built" value={xq.built} tone="default" />
                <AdminStat
                  label="Approved"
                  value={xq.approved}
                  tone={xq.approved > 0 ? "good" : "dim"}
                />
                <AdminStat
                  label="Pending"
                  value={xq.pending}
                  tone={xq.pending > 0 ? "warn" : "dim"}
                />
                <AdminStat
                  label="Posted this week"
                  value={xq.postedThisWeek}
                  tone={
                    xq.postedThisWeek >= 3
                      ? "good"
                      : xq.postedThisWeek >= 1
                        ? "warn"
                        : "bad"
                  }
                  sub={`last: ${lastPostLabel}`}
                />
              </div>

              {/* Pending post preview (up to 3) */}
              {xPendingPreview.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <span
                    style={{
                      fontSize: "10px",
                      letterSpacing: "0.4px",
                      textTransform: "uppercase",
                      color: "var(--qgi-text-dim)",
                      marginBottom: "2px",
                    }}
                  >
                    Next pending
                  </span>
                  {xPendingPreview.map((item, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        gap: "6px",
                        alignItems: "baseline",
                        padding: "5px 8px",
                        background: "var(--qgi-surface-2)",
                        borderRadius: "5px",
                        minWidth: 0,
                      }}
                    >
                      <span
                        className="font-data"
                        style={{
                          fontSize: "10px",
                          color: "var(--qgi-warning)",
                          flexShrink: 0,
                          textTransform: "uppercase",
                          letterSpacing: "0.3px",
                        }}
                      >
                        {item.type}
                      </span>
                      <span
                        style={{
                          fontSize: "10px",
                          color: "var(--qgi-text-dim)",
                          flexShrink: 0,
                        }}
                      >
                        ·
                      </span>
                      <span
                        style={{
                          fontSize: "11px",
                          color: "var(--qgi-text-muted)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          minWidth: 0,
                        }}
                        title={`${item.batch} / ${item.slug}`}
                      >
                        {item.slug}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Batch summary */}
              {xq.batches.length > 0 && (
                <table
                  style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}
                >
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--qgi-border)" }}>
                      {["Batch", "Appr?", "Built", "Pend", "Posted"].map((h) => (
                        <th
                          key={h}
                          style={{
                            padding: "0 4px 5px",
                            textAlign: h === "Batch" ? "left" : "right",
                            color: "var(--qgi-text-dim)",
                            fontWeight: 500,
                            fontSize: "10px",
                            textTransform: "uppercase",
                            letterSpacing: "0.4px",
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {xq.batches.map((b) => (
                      <tr
                        key={b.batch}
                        style={{ borderBottom: "1px solid var(--qgi-border)" }}
                      >
                        <td
                          style={{
                            padding: "4px 4px",
                            color: "var(--qgi-text-muted)",
                            fontSize: "10px",
                            maxWidth: "120px",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {b.batch}
                        </td>
                        <td
                          style={{
                            padding: "4px 4px",
                            textAlign: "right",
                            color: b.approved
                              ? "var(--qgi-success)"
                              : "var(--qgi-text-dim)",
                            fontSize: "11px",
                          }}
                        >
                          {b.approved ? "✓" : "·"}
                        </td>
                        <td
                          className="font-data"
                          style={{
                            padding: "4px 4px",
                            textAlign: "right",
                            color: "var(--qgi-text-muted)",
                          }}
                        >
                          {b.built}
                        </td>
                        <td
                          className="font-data"
                          style={{
                            padding: "4px 4px",
                            textAlign: "right",
                            color:
                              b.pending > 0
                                ? "var(--qgi-warning)"
                                : "var(--qgi-text-dim)",
                          }}
                        >
                          {b.pending}
                        </td>
                        <td
                          className="font-data"
                          style={{
                            padding: "4px 4px",
                            textAlign: "right",
                            color: "var(--qgi-text-muted)",
                          }}
                        >
                          {b.posted}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </AdminPanel>

        {/* V6 — COST & FLYWHEEL INPUTS */}
        <AdminPanel
          title="Cost &amp; Coverage"
          subtitle="Curation progress · Build size · Cloud spend"
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {/* Curation progress */}
            <div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: "6px",
                }}
              >
                <span style={{ fontSize: "11px", color: "var(--qgi-text-muted)" }}>
                  §G curation (what-happened-next)
                </span>
                <span
                  className="font-data"
                  style={{ fontSize: "12px", fontWeight: 600, color: "var(--qgi-text)" }}
                >
                  {cur.done.toLocaleString()} / {cur.total.toLocaleString()}
                </span>
              </div>
              {/* progress bar */}
              <div
                style={{
                  height: "8px",
                  borderRadius: "4px",
                  background: "var(--qgi-surface-2)",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${cur.pct.toFixed(1)}%`,
                    background:
                      cur.pct >= 80
                        ? "var(--qgi-success)"
                        : cur.pct >= 50
                          ? "var(--qgi-warning)"
                          : "var(--qgi-accent)",
                    borderRadius: "4px",
                    transition: "width 0.4s ease",
                  }}
                />
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginTop: "4px",
                }}
              >
                <span style={{ fontSize: "10px", color: "var(--qgi-text-dim)" }}>
                  {cur.pct.toFixed(1)}% complete
                </span>
                <span style={{ fontSize: "10px", color: "var(--qgi-text-dim)" }}>
                  {(cur.total - cur.done).toLocaleString()} remaining
                </span>
              </div>
            </div>

            {/* Build size */}
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <AdminStat
                label="Build data size"
                value={fmtBytes(vitals.buildBytes)}
                sub={`${buildPct.toFixed(0)}% of 250 MB Vercel limit`}
                tone={buildTone}
              />
              <AdminStat
                label="Build files"
                value={vitals.buildFileCount}
                tone="default"
              />
            </div>

            {/* Build size bar */}
            <div
              style={{
                height: "6px",
                borderRadius: "3px",
                background: "var(--qgi-surface-2)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${Math.min(100, buildPct)}%`,
                  background:
                    buildTone === "good"
                      ? "var(--qgi-success)"
                      : buildTone === "warn"
                        ? "var(--qgi-warning)"
                        : "var(--qgi-danger)",
                  borderRadius: "3px",
                }}
              />
            </div>

            {/* Muted cloud stubs */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "4px",
                paddingTop: "4px",
                borderTop: "1px solid var(--qgi-border)",
              }}
            >
              <span style={{ fontSize: "10px", color: "var(--qgi-text-dim)" }}>
                AWS/GCP $ spend — needs cloud read-role (not wired)
              </span>
              <span style={{ fontSize: "10px", color: "var(--qgi-text-dim)" }}>
                Step Functions run cost — needs cloud read-role (not wired)
              </span>
            </div>
          </div>
        </AdminPanel>
      </div>
      {/* /grid */}

      {/* ── System scale quick-stats strip ─────────────────────────────────── */}
      <AdminPanel
        title="System Scale"
        subtitle="Raw inventory counts — cross-checks the flywheel inputs"
        span={12}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
            gap: "20px",
          }}
        >
          <AdminStat label="Trends total" value={vitals.trendsTotal} />
          <AdminStat label="Trends walked" value={vitals.trendsWalked} tone="good" />
          <AdminStat label="Trends queued" value={vitals.trendsQueued} tone="warn" />

          {/* Graduated tier — 0 is expected (graduation gates on more than AUC).
              Amber emphasis: notable but not alarming. Paired with AUC-ready count
              to kill the "0 validated but 8 look strong" confusion. */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "2px",
              padding: "8px 10px",
              background:
                "color-mix(in srgb, var(--qgi-amber, var(--qgi-warning)) 10%, transparent)",
              border:
                "1px solid color-mix(in srgb, var(--qgi-amber, var(--qgi-warning)) 35%, transparent)",
              borderRadius: "6px",
            }}
          >
            <span
              style={{
                fontSize: "10px",
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                color: "var(--qgi-text-dim)",
              }}
            >
              Graduated
            </span>
            <span
              className="font-data"
              style={{
                fontSize: "22px",
                fontWeight: 600,
                lineHeight: 1.1,
                color: "var(--qgi-amber, var(--qgi-warning))",
              }}
            >
              {vitals.tierCounts.validated ?? 0}
            </span>
            <span style={{ fontSize: "11px", color: "var(--qgi-text-muted)" }}>
              full graduation tier
            </span>
          </div>

          {/* AUC-ready: the 8 that clear the bar — paired with Graduated above */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "2px",
              padding: "8px 10px",
              background: "color-mix(in srgb, var(--qgi-success) 8%, transparent)",
              border: "1px solid color-mix(in srgb, var(--qgi-success) 25%, transparent)",
              borderRadius: "6px",
            }}
          >
            <span
              style={{
                fontSize: "10px",
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                color: "var(--qgi-text-dim)",
              }}
            >
              cv-AUC ≥ 0.78
            </span>
            <span
              className="font-data"
              style={{
                fontSize: "22px",
                fontWeight: 600,
                lineHeight: 1.1,
                color: "var(--qgi-success)",
              }}
            >
              {aucReadyCount}
            </span>
            <span style={{ fontSize: "11px", color: "var(--qgi-text-muted)" }}>
              clears AUC bar (not yet grad.)
            </span>
          </div>

          <AdminStat
            label="Directional"
            value={vitals.tierCounts.directional ?? 0}
            tone="warn"
          />
          <AdminStat
            label="Experimental"
            value={vitals.tierCounts.experimental ?? 0}
            tone="dim"
          />
          <AdminStat
            label="Indicators"
            value={vitals.indicators}
            sub="WB + V-Dem + FAOSTAT"
          />
          <AdminStat label="Events" value={vitals.events.toLocaleString()} />
          <AdminStat label="Event categories" value={vitals.eventCategories} />
          <AdminStat label="Countries indexed" value={vitals.countriesIndexed} />
          <AdminStat
            label="Countries verified"
            value={vitals.countriesVerified}
            tone={vitals.countriesVerified >= 150 ? "good" : "warn"}
          />
          <AdminStat
            label="GPR validated"
            value={`${vitals.gprValidated} / ${vitals.gprTotal}`}
            tone={vitals.gprValidated >= 40 ? "good" : "warn"}
          />
        </div>
      </AdminPanel>
    </div>
  );
}
