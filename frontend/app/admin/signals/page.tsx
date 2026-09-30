/**
 * /admin/signals — Surprising / Alarming Signals + GPR drill-down.
 *
 * "What changed today, what do I not know I need to know."
 *
 * Sections:
 *   A) Signal feed  — getSurprisingSignals(8), split into two groups:
 *        "MODEL MOVES · vs prior vintage" (non-GPR items)
 *        "LIVE NEWS · GPR"               (items whose headline includes "GPR")
 *      Severity is visually ranked: ALARM > SURPRISE > NOTABLE.
 *   B) GPR panel    — getGprSummary() stats + tier chart
 *
 * Server component; AdminSignalsCharts is client-only for ECharts.
 */
import { AdminPanel, AdminStat } from "@/components/admin/AdminPanel";
import { AdminSignalsCharts } from "@/components/admin/AdminSignalsCharts";
import { getSurprisingSignals, getGprSummary } from "@/lib/admin/admin-data";
import type { SignalItem } from "@/lib/admin/admin-data";

// ─── Per-severity visual config ──────────────────────────────────────────────
//
// ALARM   — thick danger border, tinted bg, larger headline, bold label.
// SURPRISE — medium amber border, faint tint, normal headline.
// NOTABLE  — hairline border (qgi-border), no tint, dimmed label.

interface SeverityConfig {
  borderWidth: string;
  borderColor: string;
  bg: string;
  labelColor: string;
  headlineFontSize: string;
  headlineFontWeight: number;
  headlineColor: string;
  labelText: string;
}

const SEVERITY_CONFIG: Record<string, SeverityConfig> = {
  alarm: {
    borderWidth: "4px",
    borderColor: "var(--qgi-danger)",
    bg: "rgba(248, 113, 113, 0.10)",
    labelColor: "var(--qgi-danger)",
    headlineFontSize: "14px",
    headlineFontWeight: 700,
    headlineColor: "var(--qgi-text)",
    labelText: "ALARM",
  },
  surprise: {
    borderWidth: "3px",
    borderColor: "var(--qgi-amber, var(--qgi-warning))",
    bg: "rgba(245, 158, 11, 0.07)",
    labelColor: "var(--qgi-amber, var(--qgi-warning))",
    headlineFontSize: "13px",
    headlineFontWeight: 600,
    headlineColor: "var(--qgi-text)",
    labelText: "SURPRISE",
  },
  notable: {
    borderWidth: "2px",
    borderColor: "var(--qgi-border)",
    bg: "transparent",
    labelColor: "var(--qgi-text-dim)",
    headlineFontSize: "12px",
    headlineFontWeight: 500,
    headlineColor: "var(--qgi-text-muted)",
    labelText: "NOTABLE",
  },
};

// ─── Signal card (shared renderer) ──────────────────────────────────────────

function SignalCard({ sig, idx }: { sig: SignalItem; idx: number }) {
  const cfg = SEVERITY_CONFIG[sig.severity] ?? SEVERITY_CONFIG.notable;
  return (
    <div
      key={idx}
      style={{
        borderLeft: `${cfg.borderWidth} solid ${cfg.borderColor}`,
        background: cfg.bg,
        borderRadius: "0 6px 6px 0",
        padding: sig.severity === "alarm" ? "12px 14px" : "10px 14px",
        display: "flex",
        flexDirection: "column",
        gap: "4px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "8px",
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            fontSize: "9px",
            fontWeight: 700,
            letterSpacing: "0.8px",
            color: cfg.labelColor,
            flexShrink: 0,
          }}
        >
          {cfg.labelText}
        </span>
        <span
          style={{
            fontSize: cfg.headlineFontSize,
            fontWeight: cfg.headlineFontWeight,
            color: cfg.headlineColor,
            lineHeight: 1.3,
          }}
        >
          {sig.headline}
        </span>
      </div>
      <span
        style={{
          fontSize: "12px",
          color:
            sig.severity === "notable" ? "var(--qgi-text-dim)" : "var(--qgi-text-muted)",
          lineHeight: 1.5,
        }}
      >
        {sig.detail}
      </span>
    </div>
  );
}

// ─── Group sub-header ────────────────────────────────────────────────────────

function GroupHeader({ label }: { label: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        margin: "4px 0 2px",
      }}
    >
      <span
        style={{
          fontSize: "9px",
          fontWeight: 700,
          letterSpacing: "1px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
          flexShrink: 0,
        }}
      >
        {label}
      </span>
      <div
        style={{
          flex: 1,
          height: "1px",
          background: "var(--qgi-border)",
        }}
      />
    </div>
  );
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default async function SignalsPage() {
  const signals = getSurprisingSignals(8);
  const gpr = getGprSummary();

  // Split into two groups: GPR items vs model-score-move items
  const modelMoves = signals.filter((s) => !s.headline.includes("GPR"));
  const gprSignals = signals.filter((s) => s.headline.includes("GPR"));

  // Tier counts — guard undefined keys gracefully
  const tierA = gpr.tier_counts?.A ?? 0;
  const tierB = gpr.tier_counts?.B ?? 0;
  const tierC = gpr.tier_counts?.C ?? 0;

  // Spearman colour scale: >=0.40 good, 0.25-0.40 warn, <0.25 bad
  const spearmanTone =
    gpr.headline_delta_spearman >= 0.4
      ? "good"
      : gpr.headline_delta_spearman >= 0.25
        ? "warn"
        : "bad";

  // Recall colour scale: >=0.55 good, 0.40-0.55 warn, <0.40 bad
  const recallTone =
    gpr.mean_spike_recall >= 0.55
      ? "good"
      : gpr.mean_spike_recall >= 0.4
        ? "warn"
        : "bad";

  // Soft-bar pct
  const softBarTone =
    gpr.pct_passing_soft_bar >= 0.7
      ? "good"
      : gpr.pct_passing_soft_bar >= 0.5
        ? "warn"
        : "bad";

  return (
    <div>
      {/* ── Page heading ─────────────────────────────────────────────── */}
      <div style={{ marginBottom: "20px" }}>
        <h1
          style={{
            margin: 0,
            fontSize: "15px",
            fontWeight: 600,
            color: "var(--qgi-text)",
            letterSpacing: "0.3px",
          }}
        >
          Signals
        </h1>
        <p style={{ margin: "4px 0 0", fontSize: "12px", color: "var(--qgi-text-dim)" }}>
          What changed this vintage · what the model doesn&rsquo;t yet know
        </p>
      </div>

      {/* ── 12-col grid ──────────────────────────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(12, 1fr)",
          gap: "16px",
        }}
      >
        {/* ── A) Signal Feed ─── span 7 ─────────────────────────────── */}
        <AdminPanel
          title="Signal Feed"
          subtitle="Score moves ≥ 8 pts vs prior vintage · GPR news spikes"
          span={7}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {/* ── Group 1: Model score moves ──────────────────────────── */}
            <GroupHeader label="Model Moves · vs prior vintage" />
            {modelMoves.length === 0 ? (
              <p
                style={{
                  margin: "0 0 4px",
                  fontSize: "12px",
                  color: "var(--qgi-text-dim)",
                  fontStyle: "italic",
                }}
              >
                None this vintage — all score deltas are within normal bounds.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {modelMoves.map((sig, i) => (
                  <SignalCard key={i} sig={sig} idx={i} />
                ))}
              </div>
            )}

            {/* ── Group 2: Live news / GPR ────────────────────────────── */}
            <GroupHeader label="Live News · GPR" />
            {gprSignals.length === 0 ? (
              <p
                style={{
                  margin: "0 0 4px",
                  fontSize: "12px",
                  color: "var(--qgi-text-dim)",
                  fontStyle: "italic",
                }}
              >
                None this vintage.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {gprSignals.map((sig, i) => (
                  <SignalCard key={i} sig={sig} idx={i} />
                ))}
              </div>
            )}
          </div>
        </AdminPanel>

        {/* ── B) GPR Stats ─── span 5 ──────────────────────────────── */}
        <AdminPanel
          title="GPR — News-Movement Signal"
          subtitle="GPR = news-movement signal; KEEP-NAIVE (r>0.9 unreachable, corpus ceiling)."
          span={5}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "16px 20px",
            }}
          >
            <AdminStat
              label="Validated countries"
              value={gpr.n_validated}
              sub={`of ${gpr.n_total} total`}
              tone={
                gpr.n_validated >= 40 ? "good" : gpr.n_validated >= 25 ? "warn" : "bad"
              }
            />
            <AdminStat
              label="Pct passing soft bar"
              value={`${(gpr.pct_passing_soft_bar * 100).toFixed(0)}%`}
              sub="of 44 clearing ≥0.25 Δ-Spearman"
              tone={softBarTone}
            />
            <AdminStat
              label="Δ Spearman (headline)"
              value={gpr.headline_delta_spearman.toFixed(3)}
              sub="news-delta vs score-delta"
              tone={spearmanTone}
            />
            <AdminStat
              label="Mean spike recall"
              value={gpr.mean_spike_recall.toFixed(2)}
              sub="news spikes caught by model"
              tone={recallTone}
            />
          </div>

          {/* Tier breakdown header */}
          <div
            style={{
              marginTop: "20px",
              marginBottom: "6px",
              fontSize: "10px",
              letterSpacing: "0.5px",
              textTransform: "uppercase",
              color: "var(--qgi-text-dim)",
            }}
          >
            Tier distribution
          </div>

          {/* Tier pill row */}
          <div style={{ display: "flex", gap: "10px", marginBottom: "8px" }}>
            {(
              [
                { tier: "A", count: tierA, color: "var(--qgi-success)" },
                { tier: "B", count: tierB, color: "var(--qgi-warning)" },
                { tier: "C", count: tierC, color: "var(--qgi-text-dim)" },
              ] as const
            ).map(({ tier, count, color }) => (
              <div
                key={tier}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "2px",
                  flex: 1,
                  background: "var(--qgi-surface-2, var(--qgi-surface))",
                  border: "1px solid var(--qgi-border)",
                  borderRadius: "6px",
                  padding: "8px 4px",
                }}
              >
                <span
                  className="font-data"
                  style={{ fontSize: "20px", fontWeight: 700, color, lineHeight: 1 }}
                >
                  {count}
                </span>
                <span
                  style={{
                    fontSize: "10px",
                    letterSpacing: "0.4px",
                    color: "var(--qgi-text-muted)",
                  }}
                >
                  Tier {tier}
                </span>
              </div>
            ))}
          </div>

          {/* ECharts horizontal bar */}
          <AdminSignalsCharts tierA={tierA} tierB={tierB} tierC={tierC} />
        </AdminPanel>

        {/* ── B2) GPR meta note ─── span 5 (below GPR stats) ───────── */}
        <AdminPanel
          title="Research Context"
          subtitle="Why r > 0.9 is unreachable"
          span={5}
        >
          <p
            style={{
              margin: 0,
              fontSize: "12px",
              color: "var(--qgi-text-muted)",
              lineHeight: 1.7,
            }}
          >
            GPR measures the share of geopolitically-framed GKG articles for a
            country-month. The annual indicator models operate on sovereign-risk events at
            a yearly cadence; the news corpus reacts in days. Cross-frequency Spearman of
            ~0.46 confirms the news layer carries real movement signal — it simply cannot
            clock above ~0.46 given the temporal resolution mismatch and corpus noise
            floor. This is the{" "}
            <strong style={{ color: "var(--qgi-text)" }}>KEEP-NAIVE</strong> finding: no
            post-processing improves on the raw share. Confirmed across three independent
            validation passes.
          </p>
          <div
            style={{
              marginTop: "14px",
              padding: "8px 12px",
              background: "var(--qgi-surface-2, var(--qgi-bg))",
              border: "1px solid var(--qgi-border)",
              borderRadius: "6px",
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
            }}
          >
            Live AWS/GCP spend, CloudWatch Lambda heartbeat, live SQS/SFN queue depth —
            <span style={{ color: "var(--qgi-warning)", marginLeft: "4px" }}>
              needs cloud read-role (not wired)
            </span>
          </div>
        </AdminPanel>

        {/* ── A2) Signal legend ─── span 7 (below feed) ────────────── */}
        <AdminPanel title="Signal Legend" span={7} pad>
          <div style={{ display: "flex", gap: "24px", flexWrap: "wrap" }}>
            {(
              [
                {
                  severity: "alarm",
                  color: "var(--qgi-danger)",
                  desc: "Score delta ≥ 15 pts vs prior vintage, or GPR spike ≥ 12 pts. Investigate.",
                },
                {
                  severity: "surprise",
                  color: "var(--qgi-amber, var(--qgi-warning))",
                  desc: "Score delta 8–14 pts. Noteworthy but within plausible data revision range.",
                },
                {
                  severity: "notable",
                  color: "var(--qgi-text-dim)",
                  desc: "GPR quarterly move that warrants a manual country-page check.",
                },
              ] as const
            ).map(({ severity, color, desc }) => (
              <div
                key={severity}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "10px",
                  minWidth: "220px",
                  flex: 1,
                }}
              >
                <div
                  style={{
                    width: "3px",
                    minHeight: "36px",
                    alignSelf: "stretch",
                    background: color,
                    borderRadius: "2px",
                    flexShrink: 0,
                  }}
                />
                <div>
                  <span
                    style={{
                      display: "block",
                      fontSize: "9px",
                      fontWeight: 700,
                      letterSpacing: "0.8px",
                      color,
                      marginBottom: "2px",
                    }}
                  >
                    {severity.toUpperCase()}
                  </span>
                  <span
                    style={{
                      fontSize: "11px",
                      color: "var(--qgi-text-muted)",
                      lineHeight: 1.5,
                    }}
                  >
                    {desc}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </AdminPanel>
      </div>
    </div>
  );
}
