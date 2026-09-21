/**
 * AdminPanel — the one panel primitive for the localhost admin control room.
 * Server component (presentational only). Calm slate-blue chrome; the admin is
 * an internal ops surface, not a signal-urgency surface (no red/amber borders).
 */
import type { ReactNode } from "react";

const ACCENT = "#5B7E99";

export function AdminPanel({
  title,
  subtitle,
  right,
  children,
  span = 1,
  pad = true,
}: {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  /** grid column span (1-12) */
  span?: number;
  pad?: boolean;
}) {
  return (
    <section
      style={{
        gridColumn: `span ${span}`,
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderTop: `2px solid ${ACCENT}`,
        borderRadius: "8px",
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        overflow: "hidden",
      }}
    >
      {(title || right) && (
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
            {title && (
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
                {title}
              </h2>
            )}
            {subtitle && (
              <p
                style={{
                  margin: "2px 0 0",
                  fontSize: "11px",
                  color: "var(--qgi-text-dim)",
                }}
              >
                {subtitle}
              </p>
            )}
          </div>
          {right && <div style={{ flexShrink: 0 }}>{right}</div>}
        </header>
      )}
      <div style={{ padding: pad ? "14px 16px" : 0, flex: 1, minWidth: 0 }}>
        {children}
      </div>
    </section>
  );
}

/** A single labelled metric tile (monospaced value via .font-data). */
export function AdminStat({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: "default" | "good" | "warn" | "bad" | "dim";
}) {
  const color =
    tone === "good"
      ? "var(--qgi-success)"
      : tone === "warn"
        ? "var(--qgi-warning)"
        : tone === "bad"
          ? "var(--qgi-danger)"
          : tone === "dim"
            ? "var(--qgi-text-dim)"
            : "var(--qgi-text)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: 0 }}>
      <span
        style={{
          fontSize: "10px",
          letterSpacing: "0.5px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
        }}
      >
        {label}
      </span>
      <span
        className="font-data"
        style={{ fontSize: "22px", fontWeight: 600, color, lineHeight: 1.1 }}
      >
        {value}
      </span>
      {sub && (
        <span style={{ fontSize: "11px", color: "var(--qgi-text-muted)" }}>{sub}</span>
      )}
    </div>
  );
}
