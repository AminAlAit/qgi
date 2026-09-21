/**
 * TerminalAnaloguesList — §5-left: historical precedent rows (ANALOGUES).
 *
 * Compact 4-row list with alternating row backgrounds.
 * Gold match_pct right-aligned. Links to /analogues. Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { TerminalPanelShell } from "./TerminalPanelShell";

export interface AnalogueRow {
  country_a: string;
  country_b: string;
  country_b_year: number;
  recipe_label: string;
  match_pct: number;
}

export interface TerminalAnaloguesListProps {
  rows: AnalogueRow[];
}

export function TerminalAnaloguesList({ rows }: TerminalAnaloguesListProps) {
  const topRows = rows.slice(0, 4);

  return (
    <TerminalPanelShell
      title="Analogues · Historical Precedents"
      accent="#C6A03C"
      style={{ height: "100%" }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        {topRows.map((row, i) => (
          <Link
            key={i}
            href={"/analogues" as Route}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 6px",
              textDecoration: "none",
              color: "inherit",
              background: i % 2 === 0 ? "rgba(22,32,50,0.5)" : "transparent",
              borderRadius: "2px",
            }}
          >
            {/* Country A */}
            <FlagImg
              emoji={flagFor(row.country_a)}
              name={row.country_a}
              width={12}
              radius={1}
            />
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10px",
                color: "var(--qgi-text)",
                whiteSpace: "nowrap",
              }}
            >
              {row.country_a}
            </span>
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "9px",
                color: "var(--qgi-text-dim)",
                fontStyle: "italic",
                flexShrink: 0,
              }}
            >
              resembles
            </span>
            {/* Country B */}
            <FlagImg
              emoji={flagFor(row.country_b)}
              name={row.country_b}
              width={12}
              radius={1}
            />
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10px",
                color: "var(--qgi-text)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                flex: 1,
              }}
            >
              {row.country_b}, {row.country_b_year} · {row.recipe_label}
            </span>
            {/* Match pct */}
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "11px",
                fontWeight: 700,
                color: "#C9A84C",
                flexShrink: 0,
              }}
            >
              {Math.round(row.match_pct)}%
            </span>
          </Link>
        ))}
      </div>
      <div style={{ marginTop: "10px" }}>
        <Link
          href={"/analogues" as Route}
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            color: "var(--qgi-accent)",
            textDecoration: "none",
            letterSpacing: "0.6px",
          }}
        >
          All analogues →
        </Link>
      </div>
    </TerminalPanelShell>
  );
}
