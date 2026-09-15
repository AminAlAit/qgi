/**
 * ReadMePanels — P6 "How to read this page" + P7 "Vintage & sources".
 *
 * P6 is the anti-causal firewall, de-shouted (Sofia/Kwame): the same truths
 * the old red alarm box carried, now four calm plain-language statements in
 * a quiet slate-blue panel that is always present and never dismissable.
 *
 * P7 carries honest provenance ONLY — vintage, refresh cadence, data
 * sources, and the plain "reported, not deployed" line. No internal
 * machinery (no Cohort / Walk # / Majles / LOCO).
 */
import Link from "next/link";
import type { Route } from "next";
import { PanelShell } from "./PanelShell";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";

const CALM_SLATE_BLUE = "#5B7E99";

const STATEMENTS = [
  "These scores rank how strongly a country's signals resemble past pre-event conditions. They are not the chance that an event will happen.",
  "The drivers show which indicators weigh in the score. They are statistical associations, not proven causes.",
  "The analogues are historical resemblances. They are not forecasts of what comes next.",
  "Nothing on this page says an event will happen.",
];

export function HowToReadPanel() {
  return (
    <PanelShell
      title="How to read this page"
      accent={CALM_SLATE_BLUE}
      dataTour="how-to-read-panel"
    >
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        {STATEMENTS.map((s, i) => (
          <li key={i} style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
            <span
              style={{
                color: CALM_SLATE_BLUE,
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px",
                lineHeight: 1.6,
                flexShrink: 0,
              }}
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <span style={{ fontSize: "13px", lineHeight: 1.6, color: "var(--qgi-text)" }}>
              {s}
            </span>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: "10px",
          letterSpacing: "0.8px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "4px",
          textTransform: "uppercase",
        }}
      >
        {k}
      </div>
      <div style={{ fontSize: "13px", color: "var(--qgi-text)", fontWeight: 600 }}>
        {v}
      </div>
    </div>
  );
}

export function VintageSourcesPanel({ country }: { country: CountryV4 }) {
  const sources = Array.from(
    new Set(country.drivers_movement.map((d) => d.provider))
  ).sort();

  return (
    <PanelShell
      title="Sources & cross-references"
      accent={NEUTRAL_SLATE}
      fullWidth
      dataTour="vintage-sources-panel"
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: "16px",
          marginBottom: "14px",
        }}
      >
        <Field k="Refresh cadence" v="At least 4× per year" />
        <Field k="Data sources" v={sources.join(" · ") || "n/a"} />
        <Field k="Trends matched" v={`${country.recipes_lit_count} in active rotation`} />
      </div>
      <p
        style={{
          fontSize: "12px",
          lineHeight: 1.55,
          color: "var(--qgi-text-muted)",
          margin: "0 0 12px",
          maxWidth: "72ch",
        }}
      >
        Each trend shown above is currently in active rotation on the risk board, with its
        own discrimination score, calibration state, and validation history on the trend
        page.
      </p>
      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
        {/* "Open in Compound Risk" link removed 2026-05-30 — that route
            was taken down. Will return when the page rejuvenates as
            Compound Negative-Event Density. */}
        <Link
          href={`/analogues?iso=${country.iso}` as Route}
          style={{
            fontSize: "12px",
            color: "var(--qgi-accent)",
            textDecoration: "none",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          Open the Nearest-Analogue finder →
        </Link>
        <Link
          href={"/risk-board" as Route}
          style={{
            fontSize: "12px",
            color: "var(--qgi-accent)",
            textDecoration: "none",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          See on the Live Risk Board →
        </Link>
      </div>
    </PanelShell>
  );
}
