"use client";

/**
 * RiskBoardViews — the Trends | News Topics view switch for /risk-board
 * (2026-06-10, HF merge step 1; reworked after the 3-lens review).
 *
 * - Plain aria-pressed buttons, not ARIA tabs: the segmented-control look
 *   doesn't need tab semantics, and half-implementing the tab keyboard
 *   pattern misleads assistive tech (review finding).
 * - The Topics view lazy-mounts on first activation (defers TopicBoard +
 *   echarts hydration for the majority who stay on Trends), then stays
 *   mounted behind display:none so lens/mode state survives flips.
 * - Deep link: #topics opens the Topics view; a hashchange listener keeps
 *   future in-app hash links working. The rAF defer matches the Sidebar's
 *   set-state-in-effect idiom.
 */

import { useEffect, useState, type ReactNode } from "react";

type View = "trends" | "topics";

export function RiskBoardViews({
  trends,
  topics,
}: {
  trends: ReactNode;
  topics: ReactNode;
}) {
  const [view, setView] = useState<View>("trends");
  const [topicsMounted, setTopicsMounted] = useState(false);

  // Honor #topics deep links: on mount (rAF-deferred past first paint) and
  // on any later in-app hash change.
  useEffect(() => {
    const apply = () => {
      if (window.location.hash === "#topics") {
        setView("topics");
        setTopicsMounted(true);
      }
    };
    const raf = requestAnimationFrame(apply);
    const onHash = () => apply();
    window.addEventListener("hashchange", onHash);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("hashchange", onHash);
    };
  }, []);

  const switchTo = (v: View) => {
    setView(v);
    if (v === "topics") setTopicsMounted(true);
    // Keep the URL shareable without polluting history.
    const base = window.location.pathname + window.location.search;
    window.history.replaceState(null, "", v === "topics" ? `${base}#topics` : base);
  };

  return (
    <div>
      {/* View switch — structural Trends vs news Topics. */}
      <div
        role="group"
        aria-label="Board view"
        style={{
          display: "inline-flex",
          gap: "2px",
          padding: "3px",
          marginBottom: "16px",
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
        }}
      >
        <ViewButton
          active={view === "trends"}
          onClick={() => switchTo("trends")}
          label="Trends"
          sub="structural"
        />
        <ViewButton
          active={view === "topics"}
          onClick={() => switchTo("topics")}
          label="News Topics"
          sub="news pulse"
        />
      </div>

      <div style={{ display: view === "trends" ? "block" : "none" }}>{trends}</div>
      <div style={{ display: view === "topics" ? "block" : "none" }}>
        {topicsMounted && topics}
      </div>
    </div>
  );
}

function ViewButton({
  active,
  onClick,
  label,
  sub,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  sub: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: "1px",
        padding: "7px 16px",
        background: active ? "var(--qgi-surface-2)" : "transparent",
        border: "none",
        borderRadius: "6px",
        cursor: "pointer",
        boxShadow: active ? "inset 0 0 0 1px var(--qgi-accent)" : "none",
      }}
    >
      <span
        style={{
          fontSize: "12.5px",
          fontWeight: 600,
          color: active ? "var(--qgi-accent)" : "var(--qgi-text-muted)",
          lineHeight: 1.2,
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: "10px",
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          fontFamily: "ui-monospace, monospace",
          color: "var(--qgi-text-dim)",
        }}
      >
        {sub}
      </span>
    </button>
  );
}
