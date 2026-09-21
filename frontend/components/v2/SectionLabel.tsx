/**
 * V2 shared section label — Tufte-style marginalia.
 *
 * Replaces the previous all-caps "text-xs tracking-widest uppercase"
 * `<h2>` pattern on V2 detail/list pages. Per Phase A2 persona walkthrough
 * (Elif P0): "All-caps section headers SCREAM in a doc whose payload is
 * numeric. Use small-caps or 11px tracked sentence-case labels, sitting
 * flush-left as marginalia, not chapter dividers."
 *
 * Design:
 *   - 11px font size
 *   - tracking-wide letter-spacing
 *   - title-case content (NOT uppercase via CSS)
 *   - muted text color
 *   - subtle bottom margin for breathing room
 *
 * Rendered as `<h2>` for accessibility / outline-tree, but visually quiet.
 */
import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Native HTML title attribute for analyst-recovery tooltips. */
  title?: string;
  /** Override the semantic level. Defaults to h2. */
  as?: "h2" | "h3";
  /** Extra className for layout slots (e.g. inline-flex for trailing chrome). */
  className?: string;
}

export function SectionLabel({ children, title, as: Tag = "h2", className = "" }: Props) {
  return (
    <Tag
      className={`text-[11px] tracking-wide mb-2 font-medium ${className}`}
      style={{ color: "var(--qgi-text-dim)" }}
      title={title}
    >
      {children}
    </Tag>
  );
}
