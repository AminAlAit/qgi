import Link from "next/link";
import type { Route } from "next";
import type { LucideIcon } from "lucide-react";

export interface SurfaceCardData {
  surface_id: string;
  name: string;
  href: string;
  description: string;
  Icon: LucideIcon;
  color: string;
  metric_value: string;
  metric_label: string;
  ribbon: "live" | "evolving" | "new" | "fenced";
  chips?: Array<{ label: string; color: string }>;
}

const RIBBON_META: Record<SurfaceCardData["ribbon"], { label: string; color: string }> = {
  live: { label: "LIVE", color: "#3FBF8F" },
  evolving: { label: "EVOLVING", color: "#a78bfa" },
  new: { label: "NEW", color: "var(--qgi-accent)" },
  fenced: { label: "RESEARCH · INERT", color: "#7A8FA0" },
};

export function SurfaceCard({ card }: { card: SurfaceCardData }) {
  const { Icon, color } = card;
  const ribbonMeta = RIBBON_META[card.ribbon];
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
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
          }}
        >
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
          <span
            style={{
              fontSize: "9.5px",
              padding: "3px 8px",
              border: `1px solid ${ribbonMeta.color}`,
              color: ribbonMeta.color,
              borderRadius: "3px",
              letterSpacing: "0.9px",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {ribbonMeta.label}
          </span>
        </div>

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
          </div>
          <span
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-muted)",
              letterSpacing: "0.4px",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            open →
          </span>
        </div>
      </article>
    </Link>
  );
}
