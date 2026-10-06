/**
 * FamilyChip — a threat-family chip: icon-or-dot + label.
 *
 * 2026-05-29 (V4.1 round 2): per rule §1.2 the bare A/B/C/D/E/F/G/H letter
 * glyph never appears next to the family label on user-facing surfaces.
 * When no `iconNode` is supplied, the chip falls back to a small color
 * dot rather than the letter — color + label carry the family identity.
 * Tooltip still references the letter as internal taxonomy.
 *
 * `iconNode` — optional. Used on country-scoped surfaces (Rule 2) where
 * the top-recipe icon for the family conveys more information than the dot.
 */
import type { CSSProperties, ReactNode } from "react";

export function FamilyChip({
  id,
  label,
  color,
  showLabel = true,
  emphasis = false,
  iconNode,
  style,
}: {
  id: string;
  label: string;
  color: string;
  /** When false, renders just the icon/dot (compact). */
  showLabel?: boolean;
  /** Dominant family gets a full-perimeter border; others are quieter. */
  emphasis?: boolean;
  /**
   * Optional icon node that replaces the family color dot. Used on
   * country-scoped surfaces (Rule 2) where the top-recipe icon for the
   * family conveys more information.
   */
  iconNode?: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <span
      title={label}
      data-family-id={id}
      aria-label={`${label} family`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: showLabel ? "6px" : 0,
        fontSize: "10px",
        lineHeight: 1.4,
        padding: showLabel ? "2px 8px 2px 6px" : "2px 5px",
        border: `1px solid ${color}${emphasis ? "" : "99"}`,
        borderRadius: "3px",
        color,
        background: `${color}14`, // ~8% alpha tint, surface stays navy underneath
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.3px",
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {iconNode != null ? (
        <span style={{ display: "inline-flex", alignItems: "center" }}>{iconNode}</span>
      ) : (
        <span
          aria-hidden
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: color,
            display: "inline-block",
            flexShrink: 0,
          }}
        />
      )}
      {showLabel && <span style={{ opacity: 0.95 }}>{label}</span>}
    </span>
  );
}
