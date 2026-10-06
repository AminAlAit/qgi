/**
 * PanelBase — V4.1 dashboard aggregator panel wrapper.
 *
 * Aggregator panels (Highlights, Surfaces, Activity, "How to read") share a
 * consistent chrome: calm-slate-blue left border, surface background, a titled
 * header with optional caption, and an optional right-slot for auxiliary
 * controls.
 *
 * This is a DIFFERENT PanelBase from the one in precedents-v4-1/PanelBase.tsx.
 * That one uses a recipe family color and carries sectionPending state.
 * This one is for the dashboard's aggregator sections — accent defaults to
 * CALM_SLATE_BLUE (#5B7E99) and there is no recipe-specific state.
 */
import type { ReactNode } from "react";

export interface PanelBaseProps {
  title: string;
  caption?: string;
  /** Border-left color. Defaults to CALM_SLATE_BLUE (#5B7E99). */
  accent?: string;
  children: ReactNode;
  className?: string;
  /** Optional element placed top-right of the header row. */
  rightSlot?: ReactNode;
}

export function PanelBase({
  title,
  caption,
  accent = "#5B7E99",
  children,
  className,
  rightSlot,
}: PanelBaseProps) {
  return (
    <section
      className={className}
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${accent}`,
        borderRadius: "6px",
        padding: "16px 18px",
        marginBottom: "24px",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "10px",
          marginBottom: caption ? "4px" : "14px",
        }}
      >
        <h2
          style={{
            fontSize: "15px",
            fontWeight: 600,
            margin: 0,
            color: accent,
            letterSpacing: "0.1px",
            lineHeight: 1.25,
            flex: 1,
          }}
        >
          {title}
        </h2>
        {rightSlot && <div style={{ flexShrink: 0 }}>{rightSlot}</div>}
      </header>

      {caption && (
        <p
          style={{
            fontSize: "11.5px",
            lineHeight: 1.5,
            color: "var(--qgi-text-muted)",
            margin: "0 0 14px",
          }}
        >
          {caption}
        </p>
      )}

      <div>{children}</div>
    </section>
  );
}
