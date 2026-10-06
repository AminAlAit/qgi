/**
 * TerminalPanelShell — briefing-terminal team's own base panel wrapper.
 *
 * Tighter than dashboard-v4-1/PanelBase: 12px/14px padding, 4px border-radius,
 * monospace 9px uppercase title, no caption prop, no rightSlot complexity.
 *
 * Namespace: components/briefing-terminal/ only. Never imported by other teams.
 */
import type { ReactNode } from "react";

export interface TerminalPanelShellProps {
  title?: string;
  /** Left-border accent color. Defaults to #5B7E99 (calm slate). */
  accent?: string;
  children: ReactNode;
  /** Optional element rendered top-right of the title bar. */
  topRight?: ReactNode;
  style?: React.CSSProperties;
}

export function TerminalPanelShell({
  title,
  accent = "#5B7E99",
  children,
  topRight,
  style,
}: TerminalPanelShellProps) {
  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${accent}`,
        borderRadius: "4px",
        padding: "12px 14px",
        ...style,
      }}
    >
      {(title || topRight) && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "8px",
            marginBottom: "10px",
          }}
        >
          {title && (
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "9px",
                fontWeight: 700,
                letterSpacing: "1.8px",
                textTransform: "uppercase",
                color: "var(--qgi-text-dim)",
              }}
            >
              {title}
            </span>
          )}
          {topRight && <div style={{ flexShrink: 0 }}>{topRight}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
