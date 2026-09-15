/**
 * PanelShell — the V4.1 panel card frame for the country page.
 *
 * Mirrors the Recipes V4.1 panel idiom: dark navy surface, 1px border, a
 * 3px left border in the accent color, a small UPPERCASE mono eyebrow
 * title in the accent, an optional ⓘ hover tooltip, an optional caption,
 * then content. `fullWidth` makes the panel span the whole grid row.
 *
 * Accent convention on this page (Talia): structural panels (lit recipes,
 * movement, provenance) use neutral slate; the drivers pair uses the
 * top-lit family color; analogs use an archival gold; the read-me panel
 * uses a calm slate-blue. Family color never floods the surface.
 */
import type { CSSProperties, ReactNode } from "react";
import { ExplainTip } from "@/components/design/ExplainTip";

export function PanelShell({
  title,
  accent,
  icon,
  caption,
  tooltip,
  fullWidth = false,
  titleCase = false,
  children,
  style,
  dataTour,
}: {
  title: string;
  accent: string;
  /** Render the eyebrow title in Title Case instead of the default ALL CAPS. */
  titleCase?: boolean;
  /** Optional leading symbol (e.g. a family-colored RecipeIcon) rendered in
   *  the accent color before the title. */
  icon?: ReactNode;
  caption?: ReactNode;
  tooltip?: string;
  fullWidth?: boolean;
  children: ReactNode;
  style?: CSSProperties;
  /** Optional data-tour anchor for product tour steps. */
  dataTour?: string;
}) {
  return (
    <section
      data-tour={dataTour}
      style={{
        gridColumn: fullWidth ? "1 / -1" : "auto",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${accent}`,
        borderRadius: "6px",
        padding: "16px 18px 18px",
        minWidth: 0,
        ...style,
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "12px",
          marginBottom: caption ? "6px" : "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
          {icon && (
            <span
              style={{ display: "inline-flex", color: accent, flexShrink: 0 }}
              aria-hidden
            >
              {icon}
            </span>
          )}
          <h2
            style={{
              fontSize: "13px",
              letterSpacing: titleCase ? "0.2px" : "0.6px",
              textTransform: titleCase ? "none" : "uppercase",
              color: accent,
              fontFamily: "ui-monospace, monospace",
              fontWeight: 600,
              margin: 0,
            }}
          >
            {title}
          </h2>
        </div>
        {tooltip && (
          // Real tooltip (hover + click + keyboard), not a native title attr:
          // the 2026-06-11 persona panel unanimously hit this chip as a dead
          // click. 10px -> 10.5px per the same panel's tiny-text findings.
          <ExplainTip
            text={tooltip}
            style={{
              fontSize: "10.5px",
              letterSpacing: "0.4px",
              color: "var(--qgi-text-muted)",
              fontFamily: "ui-monospace, monospace",
              border: "1px solid var(--qgi-border)",
              borderRadius: "3px",
              padding: "1px 6px",
              userSelect: "none",
              whiteSpace: "nowrap",
              flexShrink: 0,
              display: "inline-block",
            }}
          >
            ⓘ what this means
          </ExplainTip>
        )}
      </header>
      {caption && (
        // <div>, not <p>: captions take ReactNode and may contain tooltip
        // components whose popups are block-level — a <div> inside a <p> is
        // invalid HTML and logged hydration errors (QA panel 2026-06-11).
        <div
          style={{
            fontSize: "12px",
            lineHeight: 1.5,
            color: "var(--qgi-text-dim)",
            margin: "0 0 14px",
            maxWidth: "72ch",
          }}
        >
          {caption}
        </div>
      )}
      {children}
    </section>
  );
}
