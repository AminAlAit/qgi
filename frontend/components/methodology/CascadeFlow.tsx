/**
 * CascadeFlow — the two-methods data-flow visual for /methodology.
 *
 *   The Cascade method
 *     Indicators + curated history  →  SCDIs  →  Patterns
 *     SCDIs + curated & verified events  →  Recipes
 *   The Trajectory Engine
 *     a recipe's shape + a country's recent signals  →  a resemblance score
 *
 * Icon nodes + connectors, plain-language sublabels, no method internals.
 * Server component; responsive (rows wrap on narrow screens).
 */
import {
  Database,
  GitMerge,
  Waves,
  CalendarCheck,
  ScrollText,
  Globe2,
  Gauge,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { TOTAL_INDICATORS } from "@/lib/site-stats";

const ACCENT = "var(--qgi-accent)";

function Node({
  Icon,
  label,
  sub,
  tint,
}: {
  Icon: LucideIcon;
  label: string;
  sub: string;
  tint: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        gap: "6px",
        minWidth: "120px",
        maxWidth: "150px",
      }}
    >
      <div
        style={{
          width: "52px",
          height: "52px",
          borderRadius: "12px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${tint}1A`,
          border: `1px solid ${tint}`,
          color: tint,
          flexShrink: 0,
        }}
      >
        <Icon size={24} strokeWidth={1.6} aria-hidden="true" />
      </div>
      <div
        style={{
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--qgi-text)",
          lineHeight: 1.2,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: "10.5px", color: "var(--qgi-text-dim)", lineHeight: 1.35 }}>
        {sub}
      </div>
    </div>
  );
}

function Connector({ symbol }: { symbol: "+" | "→" }) {
  return (
    <div
      aria-hidden="true"
      style={{
        fontSize: symbol === "→" ? "22px" : "20px",
        color: symbol === "→" ? ACCENT : "var(--qgi-text-dim)",
        fontFamily: "ui-monospace, monospace",
        lineHeight: 1,
        alignSelf: "center",
        padding: "0 4px",
        flexShrink: 0,
      }}
    >
      {symbol === "→" ? "→" : "+"}
    </div>
  );
}

function FlowRow({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "6px",
        flexWrap: "wrap",
        padding: "18px 12px",
      }}
    >
      {children}
    </div>
  );
}

function FlowLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: "10px",
        letterSpacing: "1.5px",
        textTransform: "uppercase",
        color: "var(--qgi-text-dim)",
        fontFamily: "ui-monospace, monospace",
        marginBottom: "2px",
      }}
    >
      {children}
    </div>
  );
}

export function CascadeFlow() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* The Cascade method */}
      <div
        style={{
          border: "1px solid var(--qgi-border)",
          borderRadius: "10px",
          background: "var(--qgi-surface)",
          padding: "16px 12px 8px",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <FlowLabel>The Cascade method</FlowLabel>
        </div>
        <FlowRow>
          <Node
            Icon={Database}
            label="Indicators"
            sub={`${TOTAL_INDICATORS} public, open-data signals`}
            tint="#38bdf8"
          />
          <Connector symbol="→" />
          <Node
            Icon={GitMerge}
            label="SCDIs"
            sub="signals that move together across countries"
            tint="#7B5EE6"
          />
          <Connector symbol="→" />
          <Node
            Icon={Waves}
            label="Patterns"
            sub="countries whose paths rhyme"
            tint="#7B5EE6"
          />
        </FlowRow>
        <div style={{ borderTop: "1px dashed var(--qgi-border)", margin: "0 12px" }} />
        <FlowRow>
          <Node
            Icon={GitMerge}
            label="SCDIs"
            sub="the signal relationships"
            tint="#7B5EE6"
          />
          <Connector symbol="+" />
          <Node
            Icon={CalendarCheck}
            label="Verified events"
            sub="curated & fact-checked"
            tint="#3FBF8F"
          />
          <Connector symbol="→" />
          <Node
            Icon={ScrollText}
            label="Trends"
            sub="the shape that runs ahead of an event"
            tint="#E68F29"
          />
        </FlowRow>
      </div>

      {/* The Trajectory Engine */}
      <div
        style={{
          border: "1px solid var(--qgi-border)",
          borderRadius: "10px",
          background: "var(--qgi-surface)",
          padding: "16px 12px 8px",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <FlowLabel>The Trajectory Engine</FlowLabel>
        </div>
        <FlowRow>
          <Node
            Icon={ScrollText}
            label="A trend's shape"
            sub="from the Cascade method"
            tint="#E68F29"
          />
          <Connector symbol="+" />
          <Node
            Icon={Globe2}
            label="A country's recent signals"
            sub="how it's moving now"
            tint="#38bdf8"
          />
          <Connector symbol="→" />
          <Node
            Icon={Gauge}
            label="Resemblance score"
            sub="how closely it's tracing the trend"
            tint="#3FBF8F"
          />
        </FlowRow>
      </div>
    </div>
  );
}
