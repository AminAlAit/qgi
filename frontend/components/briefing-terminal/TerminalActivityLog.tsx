/**
 * TerminalActivityLog — §5-center: world activity compact table.
 *
 * COUNTRY | DIRECTION | TOP TOPIC | STRUCT. Monospace throughout.
 * Max 6 rows, alternating backgrounds. Links to /countries. Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { TerminalPanelShell } from "./TerminalPanelShell";
import type { WorldActivityRow } from "@/lib/te-mock/dashboard-v4-1-data";

export interface TerminalActivityLogProps {
  rows: WorldActivityRow[];
}

export function TerminalActivityLog({ rows }: TerminalActivityLogProps) {
  const topRows = rows.slice(0, 6);

  return (
    <TerminalPanelShell title="Activity Log" accent="#5B7E99" style={{ height: "100%" }}>
      {/* Header row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto auto",
          gap: "8px",
          padding: "3px 6px",
          marginBottom: "4px",
          fontFamily: "ui-monospace, monospace",
          fontSize: "9px",
          letterSpacing: "1px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
        }}
      >
        <span>Country / Event</span>
        <span style={{ textAlign: "right" }}>Date</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
        {topRows.map((row, i) => (
          <Link
            key={i}
            href={row.href as Route}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto",
              gap: "8px",
              alignItems: "center",
              padding: "5px 6px",
              textDecoration: "none",
              color: "inherit",
              background: i % 2 === 0 ? "rgba(22,32,50,0.5)" : "transparent",
              borderRadius: "2px",
            }}
          >
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10px",
                color: "var(--qgi-text-muted)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {row.title}
            </span>
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "9px",
                color: "var(--qgi-text-dim)",
                flexShrink: 0,
                textAlign: "right",
              }}
            >
              {row.date}
            </span>
          </Link>
        ))}
      </div>
      <div style={{ marginTop: "10px" }}>
        <Link
          href={"/countries" as Route}
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            color: "var(--qgi-accent)",
            textDecoration: "none",
            letterSpacing: "0.6px",
          }}
        >
          Countries →
        </Link>
      </div>
    </TerminalPanelShell>
  );
}
