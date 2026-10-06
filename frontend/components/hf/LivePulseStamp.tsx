"use client";

/**
 * LivePulseStamp — the freshness gate's visible face.
 *
 * Fetches the live news-pulse state CLIENT-SIDE from /api/live-pulse. That
 * route runs in a request context, where the Vercel OIDC token (needed to read
 * the private S3 file) is available — ISR static regeneration is NOT such a
 * context, so reading S3 from the page server component silently returned
 * `absent`. Fetching from the dynamic route keeps the pages fast/static while
 * still showing live data.
 *
 * Confidence-first, no theatrics (V4.1): a single dot + a plain sentence. It
 * renders NOTHING while loading or when the poller has no fresh data
 * ("absent"), so every surface looks exactly as before until data is live.
 */
import { useEffect, useState } from "react";
import type { LiveStatus } from "@/lib/hf/live-pulse-core";

export interface LivePulseStampProps {
  /** Compact variant for dense headers (smaller text, no trailing hint). */
  compact?: boolean;
}

interface StampState {
  status: LiveStatus;
  ageMinutes: number | null;
}

function ago(min: number | null): string {
  if (min == null) return "";
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const h = Math.round(min / 60);
  return `${h}h ago`;
}

export function LivePulseStamp({ compact = false }: LivePulseStampProps) {
  const [stamp, setStamp] = useState<StampState | null>(null);

  useEffect(() => {
    let live = true;
    fetch("/api/live-pulse")
      .then((r) => (r.ok ? r.json() : null))
      .then((d: StampState | null) => {
        if (live && d) setStamp(d);
      })
      .catch(() => {
        /* network/absent -> stay invisible */
      });
    return () => {
      live = false;
    };
  }, []);

  // Loading or absent (no poller data yet) -> stay invisible (default look).
  if (!stamp || stamp.status === "absent") return null;
  const { status, ageMinutes } = stamp;

  const config: Record<
    Exclude<LiveStatus, "absent">,
    { dot: string; label: string; hint: string; pulse: boolean }
  > = {
    live: {
      dot: "var(--qgi-active, #f59e0b)",
      label: "Live news pulse",
      hint: `updated ${ago(ageMinutes)}`,
      pulse: true,
    },
    recent: {
      dot: "var(--qgi-signal, #06b6d4)",
      label: "News pulse",
      hint: `last updated ${ago(ageMinutes)}`,
      pulse: false,
    },
    paused: {
      dot: "var(--qgi-text-dim, #64748b)",
      label: "Live pulse paused",
      hint: "showing monthly readings",
      pulse: false,
    },
  };
  const c = config[status];

  return (
    <span
      title={
        status === "paused"
          ? "The hourly news poller has not refreshed recently. The board is showing the monthly vintage instead."
          : "News pulse is the share of a country's news that runs on this theme, refreshed hourly from the global news feed."
      }
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        fontSize: compact ? "10px" : "11px",
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.3px",
        color: "var(--qgi-text-muted)",
        whiteSpace: "nowrap",
      }}
    >
      {/* Reuse the shared pulse-ring (globals.css) — it carries the
          reduced-motion handling and rings in `currentColor`, so set the
          dot's color to the live hue. Only the "live" state pulses. */}
      <span
        aria-hidden
        className={c.pulse ? "qgi-pulse-dot" : undefined}
        style={{
          width: "7px",
          height: "7px",
          borderRadius: "50%",
          background: c.dot,
          color: c.dot,
          flexShrink: 0,
        }}
      />
      <span style={{ color: "var(--qgi-text-muted)" }}>{c.label}</span>
      {!compact && <span style={{ color: "var(--qgi-text-dim)" }}>· {c.hint}</span>}
    </span>
  );
}
