import type { RecipeStatus } from "@/lib/te-mock/recipes";

/** STATUS_META — V4.1 round-3 vocabulary (2026-05-29 amendment).
 *
 *  Two-bucket collapse — every "active rotation" status reads as **"in play"**
 *  (lowercase, calm slate-blue, pulsing family-color dot in the gallery
 *  card). Every pre-walk / queued status reads as **"Coming soon"**
 *  (slate-dim, no dot). The earlier 4-bucket vocabulary
 *  (Validated / In play / Coming soon / Prior version) is retired —
 *  high-confidence framing will surface differently in a future iteration. */
export const STATUS_META: Record<
  RecipeStatus,
  { label: string; color: string; bgAlpha: string }
> = {
  graduated: {
    label: "in play",
    color: "#5B7E99",
    bgAlpha: "rgba(91,126,153,0.15)",
  },
  walked_no_graduation: {
    label: "in play",
    color: "#5B7E99",
    bgAlpha: "rgba(91,126,153,0.15)",
  },
  in_progress: {
    label: "in play",
    color: "#5B7E99",
    bgAlpha: "rgba(91,126,153,0.15)",
  },
  live_legacy: {
    label: "in play",
    color: "#5B7E99",
    bgAlpha: "rgba(91,126,153,0.15)",
  },
  queued: { label: "Coming soon", color: "#7A8FA0", bgAlpha: "rgba(122,143,160,0.15)" },
};

export function StatusChip({
  status,
  size = "sm",
}: {
  status: RecipeStatus;
  size?: "sm" | "md";
}) {
  const meta = STATUS_META[status];
  const padding = size === "sm" ? "3px 9px" : "5px 12px";
  const fontSize = size === "sm" ? "11px" : "12px";
  return (
    <span
      style={{
        padding,
        fontSize,
        border: `1px solid ${meta.color}`,
        color: meta.color,
        backgroundColor: meta.bgAlpha,
        borderRadius: "4px",
        letterSpacing: "0.3px",
        fontFamily: "ui-monospace, monospace",
        fontWeight: 600,
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        whiteSpace: "nowrap",
      }}
    >
      {meta.label}
    </span>
  );
}
