/**
 * SpotlightTile — compact secondary signal tile (right column of HeroSplit).
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

export interface SpotlightData {
  kind: "alarm" | "riser" | "match";
  countryName: string;
  topicLabel: string;
  accentColor: string;
  metric: string;
  metricLabel: string;
  badge?: string;
  href: Route;
}

export function SpotlightTile({ data }: { data: SpotlightData }) {
  return (
    <style>{`
      .qgi-spotlight:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.3);
      }
    `}</style>
  );
}

export function SpotlightTileInner({ data }: { data: SpotlightData }) {
  return (
    <>
      <style>{`
        .qgi-spotlight { transition: transform 140ms ease, box-shadow 140ms ease; }
        .qgi-spotlight:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.3); }
      `}</style>
      <Link
        href={data.href}
        className="qgi-spotlight"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          padding: "12px",
          textDecoration: "none",
          color: "inherit",
          background: "var(--qgi-bg)",
          border: "1px solid var(--qgi-border)",
          borderLeft: `3px solid ${data.accentColor}`,
          borderRadius: "8px",
        }}
      >
        {/* Country + Topic */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px", minWidth: 0 }}>
          <FlagImg
            emoji={flagFor(data.countryName)}
            name={data.countryName}
            width={14}
            radius={2}
          />
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {data.countryName}
          </span>
          <span style={{ color: "var(--qgi-border)", fontSize: "11px" }}>·</span>
          <span
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-muted)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {data.topicLabel}
          </span>
        </div>

        {/* Metric row */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "18px",
              fontWeight: 700,
              color: data.accentColor,
              lineHeight: 1,
            }}
          >
            {data.metric}
          </span>
          <span
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {data.metricLabel}
          </span>
          {data.badge && (
            <span
              style={{
                fontSize: "10px",
                fontWeight: 700,
                fontFamily: "ui-monospace, monospace",
                letterSpacing: "1px",
                textTransform: "uppercase",
                padding: "2px 6px",
                borderRadius: "3px",
                background: `${data.accentColor}18`,
                color: data.accentColor,
                border: `1px solid ${data.accentColor}40`,
                marginLeft: "auto",
              }}
            >
              {data.badge}
            </span>
          )}
        </div>
      </Link>
    </>
  );
}
