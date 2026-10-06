/**
 * TooltipChip — small icon-with-hover-tooltip primitive for V4.1.
 *
 * Used inline next to score chips and panel titles to carry the M8-R5
 * fact ("scores are ranks, not probabilities") WITHOUT the brand text
 * appearing on the page. Pure CSS hover/focus — no portal, no positioning
 * library.
 */
"use client";

import { useId, useState } from "react";
import { Info } from "lucide-react";

interface Props {
  label: string;
  tooltip: string;
  accentColor?: string;
  size?: "sm" | "md";
}

export function TooltipChip({
  label,
  tooltip,
  accentColor = "var(--qgi-accent)",
  size = "sm",
}: Props) {
  const tipId = useId();
  const [open, setOpen] = useState(false);
  const iconSize = size === "md" ? 15 : 13;

  return (
    <span
      style={{
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
      }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={label}
        aria-describedby={open ? tipId : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: size === "md" ? "20px" : "18px",
          height: size === "md" ? "20px" : "18px",
          padding: 0,
          border: "none",
          background: "transparent",
          cursor: "help",
          color: open ? accentColor : "var(--qgi-text-dim)",
          borderRadius: "50%",
          transition: "color 120ms ease",
        }}
      >
        <Info size={iconSize} strokeWidth={1.6} />
      </button>
      {open && (
        <span
          id={tipId}
          role="tooltip"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            zIndex: 50,
            width: "240px",
            padding: "10px 12px",
            background: "var(--qgi-surface-2)",
            border: "1px solid var(--qgi-border)",
            borderLeft: `2px solid ${accentColor}`,
            borderRadius: "5px",
            fontSize: "12px",
            lineHeight: 1.5,
            color: "var(--qgi-text)",
            boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
            letterSpacing: "0.1px",
            pointerEvents: "none",
          }}
        >
          {tooltip}
        </span>
      )}
    </span>
  );
}
