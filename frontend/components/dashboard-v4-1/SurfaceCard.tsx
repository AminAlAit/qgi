/**
 * SurfaceCard — V4.1 rebuild.
 *
 * Changes from V4:
 * - ribbon prop dropped entirely. No colored ribbon strip in the top-right.
 * - metric_value / metric_label are optional. Cards where these are NOT
 *   methodology counts omit them; cards where they ARE counts keep them.
 *   Caller-side: use toV41SurfaceCardData() to strip ribbon + optionalise
 *   the metric pair for UI-architectural cards.
 *
 * Unchanged from V4:
 * - chips array (at-a-glance status; useful).
 * - Card border, hover transition, icon box, color accents, description text,
 *   "open ->" CTA pattern.
 * - Metric block renders only when metric_value is present (no empty block).
 *
 * Export: toV41SurfaceCardData() helper — strips ribbon, clears metric on the
 * three UI-architectural cards (Recipes, Risk Board, Analogues).
 */
import Link from "next/link";
import type { Route } from "next";
import type { LucideIcon } from "lucide-react";
import type { SurfaceCardData as V4SurfaceCardData } from "@/components/dashboard-v4/SurfaceCard";

/** V4.1 surface card data. ribbon removed; metric_value/label optional. */
export interface SurfaceCardData {
  surface_id: string;
  name: string;
  href: string;
  description: string;
  Icon: LucideIcon;
  color: string;
  /** Present only for cards where the count is a methodology fact (not UI architecture). */
  metric_value?: string;
  /** Present only when metric_value is present. */
  metric_label?: string;
  chips?: Array<{ label: string; color: string }>;
}

/**
 * The three surface IDs whose metric_value / metric_label are UI-architectural
 * (capabilities-per-recipe, top-pairs-ranked, analogs-per-country) rather than
 * methodology counts. We clear them in the transform.
 */
const UI_ARCHITECTURAL_METRICS = new Set(["recipes-v4-1", "risk-board", "analogues"]);

/**
 * Strip ribbon and drop UI-architectural metrics from a V4 SurfaceCardData.
 * Worker A imports this and applies it when building the V4.1 data array.
 */
export function toV41SurfaceCardData(card: V4SurfaceCardData): SurfaceCardData {
  const { ribbon: _ribbon, metric_value, metric_label, ...rest } = card;
  if (UI_ARCHITECTURAL_METRICS.has(card.surface_id)) {
    return rest;
  }
  return { ...rest, metric_value, metric_label };
}

export function SurfaceCard({ card }: { card: SurfaceCardData }) {
  const { Icon, color } = card;
  return (
    <Link
      href={card.href as Route}
      style={{ textDecoration: "none", color: "inherit", display: "block" }}
    >
      <article
        style={{
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          padding: "16px",
          minHeight: "200px",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
          transition: "border-color 0.15s, transform 0.15s",
          cursor: "pointer",
        }}
      >
        {/* Icon — no ribbon slot */}
        <div>
          <div
            aria-hidden="true"
            style={{
              width: "52px",
              height: "52px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--qgi-bg)",
              border: `1px solid ${color}`,
              borderRadius: "8px",
              color,
            }}
          >
            <Icon size={28} strokeWidth={1.5} />
          </div>
        </div>

        {/* Name + description */}
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontSize: "16px",
              fontWeight: 600,
              lineHeight: 1.2,
              color: "var(--qgi-text)",
              marginBottom: "5px",
            }}
          >
            {card.name}
          </div>
          <div
            style={{ fontSize: "12px", color: "var(--qgi-text-muted)", lineHeight: 1.45 }}
          >
            {card.description}
          </div>
        </div>

        {/* Chips */}
        {card.chips && card.chips.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
            {card.chips.map((c, i) => (
              <span
                key={`${c.label}-${i}`}
                style={{
                  fontSize: "9.5px",
                  padding: "2px 6px",
                  borderRadius: "3px",
                  border: `1px solid ${c.color}`,
                  color: c.color,
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: "0.3px",
                  background: "rgba(255,255,255,0.02)",
                }}
              >
                {c.label}
              </span>
            ))}
          </div>
        )}

        {/* Metric block — only rendered when metric_value is present */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginTop: "auto",
            paddingTop: "10px",
            borderTop: "1px solid rgba(255,255,255,0.04)",
          }}
        >
          {card.metric_value ? (
            <div>
              <div
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "22px",
                  fontWeight: 600,
                  color,
                  lineHeight: 1,
                  letterSpacing: "-0.3px",
                }}
              >
                {card.metric_value}
              </div>
              {card.metric_label && (
                <div
                  style={{
                    fontSize: "9.5px",
                    letterSpacing: "0.9px",
                    color: "var(--qgi-text-dim)",
                    fontFamily: "ui-monospace, monospace",
                    textTransform: "uppercase",
                    marginTop: "3px",
                  }}
                >
                  {card.metric_label}
                </div>
              )}
            </div>
          ) : (
            <div />
          )}
          <span
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-muted)",
              letterSpacing: "0.4px",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            open {"→"}
          </span>
        </div>
      </article>
    </Link>
  );
}
