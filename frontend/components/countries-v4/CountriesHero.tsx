/**
 * CountriesHero — 4 Sofia-style hero tiles for /countries-v4.
 *
 * Tile order:
 *   1. Total countries on the board
 *   2. Countries lit on ≥1 recipe
 *   3. Countries with recipes_lit_count ≥ 3 (compound-risk gate)
 *   4. Country of the week (curated mock pick)
 *
 * Visual idiom matches `components/recipe-tracker/TrackerHero.tsx` —
 * monospaced count glyph, color-keyed border accent, icon in a square
 * inset.
 */
import React from "react";
import Link from "next/link";
import type { Route } from "next";
import { Globe, Flame, Layers, Award, type LucideIcon } from "lucide-react";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";

interface TileProps {
  count: React.ReactNode;
  label: string;
  sublabel: string;
  Icon: LucideIcon;
  color: string;
  big?: boolean;
  href?: Route;
}

function HeroTile({ count, label, sublabel, Icon, color, big, href }: TileProps) {
  const inner = (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: `1px solid ${color}66`,
        borderLeft: `3px solid ${color}`,
        borderRadius: "8px",
        padding: big ? "20px 22px" : "16px 18px",
        display: "flex",
        alignItems: "flex-start",
        gap: "14px",
        minHeight: big ? "112px" : "92px",
        boxShadow: big ? `0 0 22px ${color}22` : "none",
        height: "100%",
        cursor: href ? "pointer" : "default",
      }}
    >
      <div
        style={{
          width: big ? "44px" : "36px",
          height: big ? "44px" : "36px",
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--qgi-bg)",
          border: `1px solid ${color}`,
          borderRadius: "6px",
          color,
        }}
      >
        <Icon size={big ? 24 : 20} strokeWidth={1.6} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontWeight: 600,
            fontSize: big ? "36px" : "28px",
            lineHeight: 1.05,
            color,
            letterSpacing: "-0.5px",
            wordBreak: "break-word",
          }}
        >
          {count}
        </div>
        <div
          style={{
            marginTop: "8px",
            fontSize: "11px",
            letterSpacing: "1px",
            textTransform: "uppercase",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text)",
            fontWeight: 600,
          }}
        >
          {label}
        </div>
        <div
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-muted)",
            marginTop: "2px",
            lineHeight: 1.3,
          }}
        >
          {sublabel}
        </div>
      </div>
    </div>
  );

  if (href) {
    return (
      <Link href={href} style={{ textDecoration: "none", color: "inherit" }}>
        {inner}
      </Link>
    );
  }
  return inner;
}

export function CountriesHero({
  total,
  litAny,
  compoundHigh,
  countryOfTheWeek,
  vintage,
}: {
  total: number;
  litAny: number;
  compoundHigh: number;
  countryOfTheWeek: CountryV4;
  vintage: string;
}) {
  return (
    <header style={{ marginBottom: "8px" }}>
      <div
        style={{
          color: "var(--qgi-accent)",
          fontSize: "10px",
          letterSpacing: "4px",
          textTransform: "uppercase",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "8px",
        }}
      >
        Trajectory Engine · Country Atlas
      </div>
      <div
        style={{
          display: "flex",
          gap: "16px",
          alignItems: "flex-end",
          justifyContent: "space-between",
          flexWrap: "wrap",
          marginBottom: "20px",
        }}
      >
        <div style={{ maxWidth: "820px" }}>
          <h1
            style={{
              fontSize: "34px",
              fontWeight: 600,
              lineHeight: 1.1,
              margin: "0 0 10px",
            }}
          >
            What does QGI say about this country, right now?
          </h1>
          <p
            style={{
              color: "var(--qgi-text-muted)",
              fontSize: "14px",
              lineHeight: 1.55,
              margin: 0,
            }}
          >
            Every country in the QGI corpus, surfaced as a per-country TE hub: recipe
            scores + driving indicators + momentum + nearest analogues + compound view,
            all cross-referenced into the Risk Board, Compound Risk, and Nearest-Analogue
            views. Click any card to open the country&apos;s hub.
          </p>
        </div>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            letterSpacing: "1px",
            color: "var(--qgi-text-dim)",
            padding: "6px 10px",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "4px",
            whiteSpace: "nowrap",
          }}
        >
          Release {vintage}
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.1fr 1fr 1fr 1.4fr",
          gap: "12px",
        }}
      >
        <HeroTile
          count={String(total)}
          label="Countries on board"
          sublabel="In the current corpus"
          Icon={Globe}
          color="#38bdf8"
        />
        <HeroTile
          count={String(litAny)}
          label="Lit on ≥1 recipe"
          sublabel="Currently above firing threshold"
          Icon={Flame}
          color="#E68F29"
        />
        <HeroTile
          count={String(compoundHigh)}
          label="Compound ≥3"
          sublabel="3+ recipes lit at once"
          Icon={Layers}
          color="#f59e0b"
        />
        <HeroTile
          big
          count={
            <span style={{ display: "inline-flex", alignItems: "center", gap: "10px" }}>
              <FlagImg
                emoji={countryOfTheWeek.flag_emoji}
                name={countryOfTheWeek.name}
                width={32}
                radius={3}
              />
              {countryOfTheWeek.name}
            </span>
          }
          label="Country of the week"
          sublabel={`Curated · compound ${countryOfTheWeek.compound_score.toFixed(1)} · ${countryOfTheWeek.recipes_lit_count} lit`}
          Icon={Award}
          color="#a78bfa"
          href={`/countries-v4/${countryOfTheWeek.iso.toLowerCase()}` as Route}
        />
      </div>
    </header>
  );
}
