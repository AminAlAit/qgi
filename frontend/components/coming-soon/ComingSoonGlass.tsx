/**
 * ComingSoonGlass — a locked-but-lush "coming soon" surface.
 *
 * Renders a rich backdrop under a blur, with a coming-soon sign that stays
 * CENTERED in the viewport while the backdrop SCROLLS behind it. Used by
 * /sanctions-simulator and /compare so a not-yet-live surface still shows the
 * full vision (scrollable) rather than a single frozen frame.
 *
 * Mechanics:
 *  - Root is height-locked (fills the app main column, no page-level scroll).
 *  - The backdrop sits in its own absolutely-positioned scroll layer
 *    (overflow-y: auto), so its tall content scrolls inside the frame.
 *  - The blurred content carries pointer-events: none, so the backdrop scrolls
 *    on wheel but its controls cannot be clicked.
 *  - The sign layer is a separate absolute layer with pointer-events: none
 *    (wheel passes through to the backdrop), and the card re-enables pointer
 *    events for its own links. The sign never scrolls, so it stays centered.
 *
 * Server component (pure layout, no hooks).
 */
import type { ReactNode } from "react";

export function ComingSoonGlass({
  backdrop,
  children,
}: {
  backdrop: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      style={{
        position: "relative",
        height: "100%",
        overflow: "hidden",
        background: "var(--qgi-bg)",
        color: "var(--qgi-text)",
      }}
    >
      {/* Scrollable blurred backdrop */}
      <div style={{ position: "absolute", inset: 0, overflowY: "auto" }}>
        <div
          aria-hidden="true"
          style={{
            filter: "blur(7px) saturate(1.08)",
            opacity: 0.8,
            pointerEvents: "none",
            userSelect: "none",
            padding: "28px 40px 64px",
          }}
        >
          {backdrop}
        </div>
      </div>

      {/* Centered sign — fixed within the frame, scroll passes through to the
          backdrop. */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          pointerEvents: "none",
          background: "rgba(11, 18, 27, 0.45)",
        }}
      >
        <div style={{ pointerEvents: "auto", maxWidth: 560, width: "100%" }}>
          {children}
        </div>
      </div>
    </div>
  );
}

/** The standard coming-soon card chrome used inside ComingSoonGlass. */
export function ComingSoonCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      style={{
        background: "var(--qgi-surface)",
        borderTop: "1px solid var(--qgi-border)",
        borderRight: "1px solid var(--qgi-border)",
        borderBottom: "1px solid var(--qgi-border)",
        borderLeft: "3px solid var(--qgi-accent)",
        borderRadius: 8,
        padding: "30px 34px",
        boxShadow: "0 24px 64px rgba(0, 0, 0, 0.55)",
        textAlign: "left",
      }}
    >
      <div
        style={{
          fontSize: 10,
          letterSpacing: "3.5px",
          textTransform: "uppercase",
          color: "var(--qgi-accent)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: 12,
        }}
      >
        Coming soon
      </div>
      <h1
        style={{
          fontSize: 23,
          fontWeight: 600,
          lineHeight: 1.25,
          margin: "0 0 12px",
          color: "var(--qgi-text)",
        }}
      >
        {title}
      </h1>
      <div style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--qgi-text-muted)" }}>
        {children}
      </div>
    </section>
  );
}
