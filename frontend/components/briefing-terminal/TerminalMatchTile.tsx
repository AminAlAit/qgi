/**
 * TerminalMatchTile — individual tile in the horizontal match strip (§4).
 *
 * 80px wide × ~110px tall. Flag + country + recipe label + score + RESEMBLANCE label.
 * Thin left border in l1_color. Links to /trends/{recipe_id}/countries/{iso2}.
 * Server component (sparkline loaded client-side in the strip wrapper).
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { MUTED_GRAY, confidenceT, lerpHexToRgb } from "@/lib/color-lerp";

export interface TerminalMatchTileData {
  country: string;
  iso2: string;
  recipe_id: string;
  recipe_label: string;
  l1_color: string;
  score: number;
  zone_label: string | null;
  composite: number[];
}

export function TerminalMatchTile({ m }: { m: TerminalMatchTileData }) {
  const cT = confidenceT(m.score);
  const scoreColor = lerpHexToRgb(MUTED_GRAY, m.l1_color, cT);

  return (
    <Link
      href={`/trends/${m.recipe_id}/countries/${m.iso2}` as Route}
      className="qgi-match-tile"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "5px",
        padding: "8px 8px 8px 9px",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${m.l1_color}`,
        borderRadius: "4px",
        width: "104px",
        flexShrink: 0,
        textDecoration: "none",
        color: "inherit",
        transition: "transform 120ms ease, box-shadow 120ms ease",
      }}
    >
      {/* Flag + country */}
      <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
        <FlagImg emoji={flagFor(m.country)} name={m.country} width={12} radius={1} />
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            color: "var(--qgi-text)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {m.country}
        </span>
      </div>
      {/* Recipe label — allow 2-line wrap so long names show fully */}
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "9px",
          color: "var(--qgi-text-dim)",
          overflow: "hidden",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          whiteSpace: "normal",
          lineHeight: 1.3,
        }}
      >
        {m.recipe_label}
      </span>
      {/* Score */}
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "22px",
            fontWeight: 700,
            color: scoreColor,
            lineHeight: 1,
            letterSpacing: "-0.5px",
          }}
        >
          {Math.round(m.score)}
        </span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            letterSpacing: "0.8px",
            textTransform: "uppercase",
            color: "var(--qgi-text-dim)",
          }}
        >
          MATCH
        </span>
      </div>
    </Link>
  );
}
