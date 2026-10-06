/**
 * Admin > Content & Outreach
 *
 * Sections:
 *   A) What-happened-next curation progress (from data/curation/)
 *   B) X content queue (from sibling docs-specs outbox — localhost only)
 *   C) Published reports (real slugs read from app/reports/ at build-time via
 *      the static REPORT_SLUGS array below — derived from the actual filesystem
 *      at the time this file was written, NOT hardcoded guesses; see the Glob
 *      comment for provenance).
 *
 * All numbers are real. No mocks.
 */
import type { Route } from "next";
import Link from "next/link";
import { readdirSync } from "fs";
import path from "path";
import { AdminPanel, AdminStat } from "@/components/admin/AdminPanel";
import { getCurationProgress, getXQueue } from "@/lib/admin/admin-content";

// ── Published report slugs — read LIVE from the filesystem (ground truth) ───
// Real directory listing of app/reports/ at render; backup dirs ("_classic-
// backup") and route groups ("(...)") excluded. Auto-stays-correct when a
// report is added — no manual list to maintain.
function getReportSlugs(): string[] {
  try {
    return readdirSync(path.join(process.cwd(), "app", "reports"), {
      withFileTypes: true,
    })
      .filter(
        (e) => e.isDirectory() && !e.name.startsWith("_") && !e.name.startsWith("(")
      )
      .map((e) => e.name)
      .sort();
  } catch {
    return [];
  }
}
const REPORT_SLUGS: string[] = getReportSlugs();

// ── Helpers ───────────────────────────────────────────────────────────────
function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

// ── Page ──────────────────────────────────────────────────────────────────
export default async function ContentPage() {
  const [cur, xq] = await Promise.all([getCurationProgress(), getXQueue()]);

  const pctCur = cur.present ? cur.pct : 0;
  const remaining = cur.present ? cur.total - cur.done : 0;

  // bar widths are safe 0–100
  const barW = Math.min(100, Math.max(0, pctCur));

  return (
    <div>
      {/* Page heading */}
      <div style={{ marginBottom: "20px" }}>
        <h1
          style={{
            margin: 0,
            fontSize: "15px",
            fontWeight: 700,
            letterSpacing: "0.5px",
            color: "var(--qgi-text)",
          }}
        >
          Content &amp; Outreach
        </h1>
        <p style={{ margin: "4px 0 0", fontSize: "12px", color: "var(--qgi-text-dim)" }}>
          Curation pipeline · X post queue · Published intelligence reports
        </p>
      </div>

      {/* ─── Grid ─────────────────────────────────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(12, 1fr)",
          gap: "16px",
        }}
      >
        {/* ─── A) CURATION ─────────────────────────────────────────── */}
        <AdminPanel
          title="What-Happened-Next Curation"
          subtitle="§G analogue — 3 440-event analogue pool"
          span={7}
        >
          {!cur.present ? (
            <p style={{ margin: 0, fontSize: "12px", color: "var(--qgi-text-dim)" }}>
              — curation file not found on disk (
              <code style={{ fontSize: "11px" }}>
                data/curation/what-happened-next.json
              </code>
              ). Expected on localhost with the full qgi-frontend checkout.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {/* Stat row */}
              <div style={{ display: "flex", gap: "32px", flexWrap: "wrap" }}>
                <AdminStat
                  label="Done"
                  value={fmt(cur.done)}
                  sub={`of ${fmt(cur.total)} events`}
                  tone="good"
                />
                <AdminStat
                  label="Remaining"
                  value={fmt(remaining)}
                  sub="events to curate"
                  tone={remaining > 500 ? "warn" : "good"}
                />
                <AdminStat
                  label="Progress"
                  value={`${pctCur.toFixed(1)}%`}
                  sub="of analogue pool"
                  tone={pctCur >= 80 ? "good" : pctCur >= 50 ? "warn" : "default"}
                />
              </div>

              {/* Progress bar */}
              <div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginBottom: "6px",
                    fontSize: "11px",
                    color: "var(--qgi-text-muted)",
                  }}
                >
                  <span>Curation progress</span>
                  <span className="font-data">
                    {fmt(cur.done)} / {fmt(cur.total)}
                  </span>
                </div>
                <div
                  style={{
                    height: "10px",
                    background: "var(--qgi-surface-2)",
                    borderRadius: "5px",
                    overflow: "hidden",
                    border: "1px solid var(--qgi-border)",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${barW}%`,
                      background:
                        pctCur >= 80
                          ? "var(--qgi-success)"
                          : pctCur >= 50
                            ? "var(--qgi-warning)"
                            : "var(--qgi-accent)",
                      borderRadius: "5px",
                      transition: "width 0.3s ease",
                    }}
                  />
                </div>
                <p
                  style={{
                    margin: "6px 0 0",
                    fontSize: "11px",
                    color: "var(--qgi-text-dim)",
                  }}
                >
                  Source:{" "}
                  <code style={{ fontSize: "10px" }}>
                    data/curation/what-happened-next.json
                  </code>{" "}
                  · SOLO-wave pipeline (parallel → rate-limit gated) · target{" "}
                  <span className="font-data">3 440</span> events
                </p>
              </div>
            </div>
          )}
        </AdminPanel>

        {/* ─── A2) Curation mini-note ───────────────────────────────── */}
        <AdminPanel title="Curation Status" subtitle="wave discipline" span={5}>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <div
              style={{
                padding: "8px 12px",
                background: "var(--qgi-surface-2)",
                borderRadius: "6px",
                border: "1px solid var(--qgi-border)",
                fontSize: "11px",
                color: "var(--qgi-text-muted)",
                lineHeight: 1.55,
              }}
            >
              <strong
                style={{
                  color: "var(--qgi-text)",
                  display: "block",
                  marginBottom: "4px",
                }}
              >
                Wave gate: SOLO waves only
              </strong>
              Parallel batches → rate-limit. Each wave completes before the next fires.
              Pipeline: research → draft → 2 web-verifiers → repair. Calibration: catch
              100% / FP 0% / ~95% yield.
            </div>
            <div
              style={{
                padding: "8px 12px",
                background: "var(--qgi-surface-2)",
                borderRadius: "6px",
                border: "1px solid var(--qgi-border)",
                fontSize: "11px",
                color: "var(--qgi-text-muted)",
                lineHeight: 1.55,
              }}
            >
              <strong
                style={{
                  color: "var(--qgi-text)",
                  display: "block",
                  marginBottom: "4px",
                }}
              >
                Pool: recipe-agnostic
              </strong>
              All 3 440 analogue events are curated into a single pool — not scoped per
              recipe. State managed in{" "}
              <code style={{ fontSize: "10px" }}>qgi-ml/curation/</code>.
            </div>
          </div>
        </AdminPanel>

        {/* ─── B) X CONTENT QUEUE ──────────────────────────────────── */}
        <AdminPanel
          title="X Content Queue"
          subtitle="outbox — sibling docs-specs repo (localhost only)"
          span={12}
        >
          {!xq.present ? (
            <p style={{ margin: 0, fontSize: "12px", color: "var(--qgi-text-dim)" }}>
              — outbox not on disk (localhost only, sibling docs-specs repo). Expected at{" "}
              <code style={{ fontSize: "11px" }}>
                ../docs/specs/internal/outreach/twitter-x/engine/outbox/
              </code>
              .
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
              {/* Stat strip */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
                  gap: "16px",
                }}
              >
                <AdminStat
                  label="Built"
                  value={fmt(xq.built)}
                  sub="posts authored"
                  tone="default"
                />
                <AdminStat
                  label="Approved"
                  value={fmt(xq.approved)}
                  sub="ready to send"
                  tone={xq.approved > 0 ? "good" : "dim"}
                />
                <AdminStat
                  label="Pending"
                  value={fmt(xq.pending)}
                  sub="unsent"
                  tone={xq.pending > 0 ? "warn" : "dim"}
                />
                <AdminStat
                  label="Posted total"
                  value={fmt(xq.postedTotal)}
                  sub="lifetime"
                  tone="default"
                />
                <AdminStat
                  label="Posted this week"
                  value={fmt(xq.postedThisWeek)}
                  sub="last 7 days"
                  tone={
                    xq.postedThisWeek >= 3
                      ? "good"
                      : xq.postedThisWeek >= 1
                        ? "warn"
                        : "dim"
                  }
                />
                <AdminStat
                  label="Last posted"
                  value={
                    <span style={{ fontSize: "14px" }}>
                      {xq.lastPostAt ? fmtDate(xq.lastPostAt) : "—"}
                    </span>
                  }
                  sub={xq.lastPostAt ? "UTC" : "no post logged"}
                  tone={xq.lastPostAt ? "default" : "dim"}
                />
              </div>

              {/* ── Batch editorial view ────────────────────────────── */}
              {xq.batches.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {xq.batches.map((b) => {
                    // actionable = pending posts inside an approved batch
                    const actionablePending = b.approved && b.pending > 0;
                    return (
                      <div
                        key={b.batch}
                        style={{
                          border: `1px solid ${actionablePending ? "rgba(251,191,36,0.35)" : "var(--qgi-border)"}`,
                          borderRadius: "7px",
                          background: actionablePending
                            ? "rgba(251,191,36,0.04)"
                            : "var(--qgi-surface-2)",
                          overflow: "hidden",
                        }}
                      >
                        {/* Batch header row */}
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "10px",
                            padding: "8px 12px",
                            borderBottom: "1px solid var(--qgi-border)",
                            flexWrap: "wrap",
                          }}
                        >
                          {/* Batch name */}
                          <code
                            style={{
                              fontSize: "11px",
                              fontWeight: 600,
                              color: "var(--qgi-text)",
                              flexShrink: 0,
                            }}
                          >
                            {b.batch}
                          </code>

                          {/* Approved chip */}
                          <span
                            style={{
                              display: "inline-block",
                              padding: "1px 7px",
                              borderRadius: "4px",
                              fontSize: "10px",
                              fontWeight: 600,
                              letterSpacing: "0.4px",
                              background: b.approved
                                ? "rgba(52,211,153,0.12)"
                                : "rgba(148,163,184,0.12)",
                              color: b.approved
                                ? "var(--qgi-success)"
                                : "var(--qgi-text-dim)",
                              flexShrink: 0,
                            }}
                          >
                            {b.approved ? "APPROVED" : "NOT APPROVED"}
                          </span>

                          {/* Actionable nudge */}
                          {actionablePending && (
                            <span
                              style={{
                                display: "inline-block",
                                padding: "1px 7px",
                                borderRadius: "4px",
                                fontSize: "10px",
                                fontWeight: 600,
                                letterSpacing: "0.4px",
                                background: "rgba(251,191,36,0.15)",
                                color: "var(--qgi-amber)",
                                flexShrink: 0,
                              }}
                            >
                              {b.pending} TO SEQUENCE
                            </span>
                          )}

                          {/* Spacer */}
                          <div style={{ flex: 1 }} />

                          {/* Counts strip */}
                          <div
                            style={{
                              display: "flex",
                              gap: "16px",
                              fontSize: "11px",
                              color: "var(--qgi-text-muted)",
                              flexShrink: 0,
                            }}
                          >
                            <span>
                              built{" "}
                              <span
                                className="font-data"
                                style={{ color: "var(--qgi-text)" }}
                              >
                                {b.built}
                              </span>
                            </span>
                            <span>
                              posted{" "}
                              <span
                                className="font-data"
                                style={{
                                  color:
                                    b.posted > 0
                                      ? "var(--qgi-success)"
                                      : "var(--qgi-text-dim)",
                                }}
                              >
                                {b.posted}
                              </span>
                            </span>
                            <span>
                              pending{" "}
                              <span
                                className="font-data"
                                style={{
                                  color: actionablePending
                                    ? "var(--qgi-amber)"
                                    : b.pending > 0
                                      ? "var(--qgi-text-muted)"
                                      : "var(--qgi-text-dim)",
                                }}
                              >
                                {b.pending}
                              </span>
                            </span>
                          </div>
                        </div>

                        {/* Per-post item list */}
                        {b.items.length > 0 && (
                          <div style={{ padding: "6px 0" }}>
                            {b.items.map((item) => {
                              const isPosted =
                                item.status === "posted" || item.status === "sent";
                              const isPending = !isPosted;
                              // "actionable" = pending post inside an approved batch
                              const isActionable = isPending && b.approved;

                              return (
                                <div
                                  key={item.idx}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "10px",
                                    padding: "5px 12px",
                                    borderBottom: "1px solid rgba(255,255,255,0.04)",
                                    // highlight actionable rows subtly
                                    background: isActionable
                                      ? "rgba(251,191,36,0.06)"
                                      : "transparent",
                                  }}
                                >
                                  {/* Index */}
                                  <span
                                    className="font-data"
                                    style={{
                                      fontSize: "10px",
                                      color: "var(--qgi-text-dim)",
                                      minWidth: "20px",
                                      flexShrink: 0,
                                    }}
                                  >
                                    {item.idx + 1}
                                  </span>

                                  {/* Type pill */}
                                  <span
                                    style={{
                                      fontSize: "10px",
                                      padding: "1px 6px",
                                      borderRadius: "3px",
                                      background: "rgba(91,126,153,0.15)",
                                      color: "var(--qgi-text-muted)",
                                      fontWeight: 500,
                                      letterSpacing: "0.3px",
                                      flexShrink: 0,
                                      whiteSpace: "nowrap",
                                    }}
                                  >
                                    {item.type}
                                  </span>

                                  {/* Slug */}
                                  <code
                                    style={{
                                      fontSize: "11px",
                                      color: isActionable
                                        ? "var(--qgi-text)"
                                        : "var(--qgi-text-muted)",
                                      flex: 1,
                                      overflow: "hidden",
                                      textOverflow: "ellipsis",
                                      whiteSpace: "nowrap",
                                      fontWeight: isActionable ? 600 : 400,
                                    }}
                                  >
                                    {item.slug}
                                  </code>

                                  {/* Status chip */}
                                  <span
                                    style={{
                                      display: "inline-block",
                                      padding: "1px 7px",
                                      borderRadius: "4px",
                                      fontSize: "10px",
                                      fontWeight: 600,
                                      letterSpacing: "0.4px",
                                      flexShrink: 0,
                                      background: isPosted
                                        ? "rgba(52,211,153,0.10)"
                                        : isActionable
                                          ? "rgba(251,191,36,0.15)"
                                          : "rgba(148,163,184,0.10)",
                                      color: isPosted
                                        ? "var(--qgi-success)"
                                        : isActionable
                                          ? "var(--qgi-amber)"
                                          : "var(--qgi-text-dim)",
                                    }}
                                  >
                                    {isPosted
                                      ? "posted"
                                      : isActionable
                                        ? "pending — queue"
                                        : "pending"}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {b.items.length === 0 && (
                          <p
                            style={{
                              margin: 0,
                              padding: "8px 12px",
                              fontSize: "11px",
                              color: "var(--qgi-text-dim)",
                            }}
                          >
                            — no manifest items for this batch
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {xq.batches.length === 0 && (
                <p style={{ margin: 0, fontSize: "12px", color: "var(--qgi-text-dim)" }}>
                  — no batches found in outbox directory.
                </p>
              )}
            </div>
          )}
        </AdminPanel>

        {/* ─── C) PUBLISHED REPORTS ─────────────────────────────────── */}
        <AdminPanel
          title="Published Intelligence Reports"
          subtitle={`${REPORT_SLUGS.length} routes live under /reports/`}
          span={6}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {REPORT_SLUGS.map((slug) => (
              <div
                key={slug}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "7px 10px",
                  borderRadius: "5px",
                  border: "1px solid var(--qgi-border)",
                  background: "var(--qgi-surface-2)",
                  gap: "12px",
                }}
              >
                {/* Checkmark + slug */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    minWidth: 0,
                  }}
                >
                  <span
                    style={{
                      flexShrink: 0,
                      width: "16px",
                      height: "16px",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      borderRadius: "3px",
                      background: "rgba(52,211,153,0.15)",
                      color: "var(--qgi-success)",
                      fontSize: "10px",
                      fontWeight: 700,
                    }}
                  >
                    ✓
                  </span>
                  <code
                    style={{
                      fontSize: "11px",
                      color: "var(--qgi-text)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    /reports/{slug}
                  </code>
                </div>
                {/* Live link */}
                <Link
                  href={`/reports/${slug}` as Route}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    flexShrink: 0,
                    fontSize: "10px",
                    color: "var(--qgi-accent)",
                    textDecoration: "none",
                    letterSpacing: "0.3px",
                    fontWeight: 500,
                  }}
                >
                  open ↗
                </Link>
              </div>
            ))}
          </div>
          <p
            style={{
              margin: "12px 0 0",
              fontSize: "10px",
              color: "var(--qgi-text-dim)",
              lineHeight: 1.5,
            }}
          >
            Read live from <code style={{ fontSize: "10px" }}>app/reports/</code> on disk
            (<code style={{ fontSize: "10px" }}>_classic-backup</code> + route groups
            excluded) — auto-updates when a report is added.
          </p>
        </AdminPanel>

        {/* ─── C2) Reports quick-stats ─────────────────────────────── */}
        <AdminPanel title="Reports Overview" subtitle="publishing snapshot" span={6}>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ display: "flex", gap: "24px", flexWrap: "wrap" }}>
              <AdminStat
                label="Live reports"
                value={REPORT_SLUGS.length}
                sub="routes in app/reports/"
                tone="good"
              />
              <AdminStat
                label="Byline"
                value="Amin Al-Ait"
                sub="all reports (never a persona)"
                tone="dim"
              />
            </div>
            <div
              style={{
                padding: "8px 12px",
                background: "var(--qgi-surface-2)",
                borderRadius: "6px",
                border: "1px solid var(--qgi-border)",
                fontSize: "11px",
                color: "var(--qgi-text-muted)",
                lineHeight: 1.55,
              }}
            >
              <strong
                style={{
                  color: "var(--qgi-text)",
                  display: "block",
                  marginBottom: "4px",
                }}
              >
                Deploy: Vercel auto-deploy on main push
              </strong>
              Live URL:{" "}
              <a
                href="https://qgintelligence.com/reports"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "var(--qgi-accent)", fontSize: "11px" }}
              >
                qgintelligence.com/reports
              </a>
              <br />
              <span style={{ color: "var(--qgi-text-dim)" }}>
                Vercel build SHA — needs cloud read-role (not wired)
              </span>
            </div>
            <div
              style={{
                padding: "8px 12px",
                background: "var(--qgi-surface-2)",
                borderRadius: "6px",
                border: "1px solid var(--qgi-border)",
                fontSize: "11px",
                color: "var(--qgi-text-muted)",
                lineHeight: 1.55,
              }}
            >
              <strong
                style={{
                  color: "var(--qgi-text)",
                  display: "block",
                  marginBottom: "4px",
                }}
              >
                Next reports in pipeline
              </strong>
              Tracked via GitHub issues in{" "}
              <code style={{ fontSize: "10px" }}>AminAlAit/qgi-aws-tf</code>. No live
              queue data available locally — check the Kanban board for backlog.
            </div>
          </div>
        </AdminPanel>
      </div>
    </div>
  );
}
