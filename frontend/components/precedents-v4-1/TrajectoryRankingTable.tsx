"use client";

/**
 * TrajectoryRankingTable — the /trends/trajectory-ranking client
 * surface (migrated + rebuilt from the old /patterns/ranking to the V4.1
 * bar). Top-30 countries by how closely their current movement resembles any
 * trajectory in the catalog. Search + family filter + sortable columns.
 *
 * Built to the bar: flagcdn flags, family color as thin accent, honest plain
 * copy (no M8-R5 / walk / gate jargon, no "pattern" wording, no emoji status
 * dots, no em-dashes), links into the trajectory deep-dives.
 */
import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { Search, ListFilter } from "lucide-react";
import type { RankingEntry } from "@/lib/te-mock/patterns-v4-data";
import { familyColor, CALM_SLATE_BLUE } from "@/lib/te-mock/l1-families";
import { flagFor } from "@/lib/te-mock/country-flags";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";

type SortKey = "rank" | "country" | "top_score" | "region";

export interface TrajectoryRankingTableProps {
  rows: RankingEntry[];
  families: Array<{ id: string; label: string; color: string }>;
}

export function TrajectoryRankingTable({ rows, families }: TrajectoryRankingTableProps) {
  const [query, setQuery] = useState("");
  const [familyFilter, setFamilyFilter] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const filtered = useMemo(() => {
    let r = rows;
    if (familyFilter) r = r.filter((row) => row.top_l1_id === familyFilter);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      r = r.filter(
        (row) =>
          row.country.toLowerCase().includes(q) ||
          row.region.toLowerCase().includes(q) ||
          row.top_pattern_name.toLowerCase().includes(q)
      );
    }
    const sorted = [...r].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "rank") cmp = a.rank - b.rank;
      else if (sortKey === "country") cmp = a.country.localeCompare(b.country);
      else if (sortKey === "top_score") cmp = a.top_score - b.top_score;
      else if (sortKey === "region") cmp = a.region.localeCompare(b.region);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [rows, query, familyFilter, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir(key === "top_score" ? "desc" : "asc");
    }
  }

  return (
    <>
      {/* Responsive grid: sidebar collapses under table below 880px */}
      <style>{`
        .trajectory-ranking-grid {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 280px;
          gap: 20px;
          align-items: flex-start;
        }
        @media (max-width: 880px) {
          .trajectory-ranking-grid {
            grid-template-columns: 1fr;
          }
          .trajectory-ranking-grid aside {
            position: static !important;
          }
        }
      `}</style>
      <div
        className="trajectory-ranking-grid"
        style={
          {
            /* layout now via .trajectory-ranking-grid CSS */
          }
        }
      >
        <div>
          {/* Controls */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "12px",
              alignItems: "center",
              padding: "12px 14px",
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "6px",
              marginBottom: "12px",
            }}
          >
            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "6px 10px",
                background: "var(--qgi-bg)",
                border: "1px solid var(--qgi-border)",
                borderRadius: "4px",
                flex: "1 1 220px",
                minWidth: "180px",
              }}
            >
              <Search size={13} color="var(--qgi-text-dim)" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search country, region, or trend"
                style={{
                  flex: 1,
                  background: "transparent",
                  border: "none",
                  outline: "none",
                  color: "var(--qgi-text)",
                  fontSize: "12.5px",
                  fontFamily: "inherit",
                }}
                aria-label="Search ranking"
              />
            </label>

            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                flexWrap: "wrap",
              }}
            >
              <ListFilter size={12} color="var(--qgi-text-dim)" />
              <button
                type="button"
                onClick={() => setFamilyFilter(null)}
                style={chipBtnStyle(familyFilter === null)}
                aria-pressed={familyFilter === null}
              >
                All families
              </button>
              {families.map((f) => {
                const c = familyColor(f.id, f.color);
                return (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setFamilyFilter(familyFilter === f.id ? null : f.id)}
                    style={chipBtnStyle(familyFilter === f.id, c)}
                    aria-pressed={familyFilter === f.id}
                    aria-label={f.label}
                    title={f.label}
                  >
                    <span
                      style={{
                        width: "6px",
                        height: "6px",
                        borderRadius: "50%",
                        background: c,
                        marginRight: "5px",
                        display: "inline-block",
                        verticalAlign: "middle",
                      }}
                    />
                    {f.id}
                  </button>
                );
              })}
            </div>

            <span style={{ flex: 1 }} />
            <span
              style={{
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
                letterSpacing: "0.4px",
              }}
            >
              {filtered.length} of {rows.length} countries
            </span>
          </div>

          {/* Table — overflow-x:auto lets it scroll horizontally on narrow desktops */}
          <div
            style={{
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "6px",
              overflowX: "auto",
            }}
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "12.5px",
                tableLayout: "fixed",
              }}
            >
              <colgroup>
                <col style={{ width: "40px" }} />
                <col style={{ width: "auto" }} />
                <col style={{ width: "96px" }} />
                <col style={{ width: "auto" }} />
                <col style={{ width: "70px" }} />
                <col style={{ width: "auto" }} />
              </colgroup>
              <thead>
                <tr
                  style={{
                    background: "var(--qgi-bg)",
                    borderBottom: "1px solid var(--qgi-border)",
                  }}
                >
                  <Th
                    active={sortKey === "rank"}
                    dir={sortDir}
                    onClick={() => toggleSort("rank")}
                  >
                    #
                  </Th>
                  <Th
                    active={sortKey === "country"}
                    dir={sortDir}
                    onClick={() => toggleSort("country")}
                  >
                    Country
                  </Th>
                  <Th
                    active={sortKey === "region"}
                    dir={sortDir}
                    onClick={() => toggleSort("region")}
                  >
                    Region
                  </Th>
                  <Th>Top trajectory</Th>
                  <Th
                    active={sortKey === "top_score"}
                    dir={sortDir}
                    onClick={() => toggleSort("top_score")}
                    align="right"
                  >
                    Match
                  </Th>
                  <Th>Runner-up</Th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      style={{
                        padding: "32px 16px",
                        textAlign: "center",
                        color: "var(--qgi-text-dim)",
                        fontStyle: "italic",
                      }}
                    >
                      No countries match these filters.
                    </td>
                  </tr>
                )}
                {filtered.map((row, i) => {
                  const topColor = familyColor(row.top_l1_id, row.top_l1_color);
                  return (
                    <tr
                      key={row.country}
                      style={{
                        borderBottom:
                          i < filtered.length - 1
                            ? "1px solid var(--qgi-border)"
                            : "none",
                      }}
                    >
                      <td
                        style={{
                          padding: "11px 12px",
                          fontFamily: "ui-monospace, monospace",
                          fontSize: "11.5px",
                          color: "var(--qgi-text-dim)",
                        }}
                      >
                        {String(row.rank).padStart(2, "0")}
                      </td>
                      <td style={{ padding: "11px 12px" }}>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "8px",
                          }}
                        >
                          <FlagImg
                            emoji={flagFor(row.country)}
                            name={row.country}
                            width={20}
                            radius={2}
                          />
                          <span style={{ fontWeight: 600, color: "var(--qgi-text)" }}>
                            {row.country}
                          </span>
                        </span>
                      </td>
                      <td
                        style={{
                          padding: "11px 12px",
                          fontFamily: "ui-monospace, monospace",
                          fontSize: "10.5px",
                          color: "var(--qgi-text-muted)",
                          letterSpacing: "0.3px",
                        }}
                      >
                        {row.region}
                      </td>
                      <td style={{ padding: "11px 12px" }}>
                        <Link
                          href={`/trends/${row.top_pattern_id}/trajectory` as Route}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "8px",
                            color: "var(--qgi-text)",
                            textDecoration: "none",
                          }}
                        >
                          <span
                            style={{
                              width: "7px",
                              height: "7px",
                              borderRadius: "50%",
                              background: topColor,
                              flexShrink: 0,
                            }}
                          />
                          <span style={{ fontSize: "12.5px" }}>
                            {row.top_pattern_name}
                          </span>
                          <span
                            style={{
                              fontSize: "9.5px",
                              padding: "1px 5px",
                              border: `1px solid ${topColor}`,
                              color: topColor,
                              borderRadius: "3px",
                              fontFamily: "ui-monospace, monospace",
                              letterSpacing: "0.3px",
                            }}
                          >
                            {row.top_l1_id}
                          </span>
                        </Link>
                      </td>
                      <td style={{ padding: "11px 12px", textAlign: "right" }}>
                        <span
                          style={{
                            fontFamily: "ui-monospace, monospace",
                            fontWeight: 600,
                            fontSize: "14px",
                            color: topColor,
                          }}
                        >
                          {row.top_score.toFixed(0)}
                        </span>
                      </td>
                      <td style={{ padding: "11px 12px" }}>
                        <Link
                          href={`/trends/${row.runner_pattern_id}/trajectory` as Route}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "6px",
                            color: "var(--qgi-text-muted)",
                            textDecoration: "none",
                            fontSize: "11.5px",
                          }}
                        >
                          <span
                            style={{
                              width: "6px",
                              height: "6px",
                              borderRadius: "50%",
                              background: familyColor(
                                row.runner_l1_id,
                                row.runner_l1_color
                              ),
                              flexShrink: 0,
                              opacity: 0.7,
                            }}
                          />
                          <span>{row.runner_pattern_name}</span>
                          <span
                            style={{
                              fontFamily: "ui-monospace, monospace",
                              fontSize: "10.5px",
                              color: "var(--qgi-text-dim)",
                            }}
                          >
                            {row.runner_score.toFixed(0)}
                          </span>
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Honest footer (calm, not a red alarm box) */}
          <div
            style={{
              marginTop: "14px",
              padding: "12px 14px",
              border: "1px solid var(--qgi-border)",
              borderLeft: `3px solid ${CALM_SLATE_BLUE}`,
              background: "rgba(91,126,153,0.06)",
              borderRadius: "5px",
              fontSize: "12px",
              color: "var(--qgi-text-muted)",
              lineHeight: 1.55,
            }}
          >
            Scores in this table are similarity ranks from 0 to 100, not probabilities. A
            country at 90 resembles that trajectory closely; it is not 90% likely to see
            the event. No trend here is yet deployed for real decisions.
          </div>
        </div>

        {/* Side panel — how this differs from the Risk Board */}
        <aside
          style={{
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "6px",
            padding: "14px 16px",
            position: "sticky",
            top: "12px",
          }}
        >
          <h3
            style={{
              fontSize: "12px",
              letterSpacing: "1.2px",
              color: "var(--qgi-accent)",
              fontFamily: "ui-monospace, monospace",
              margin: "0 0 10px",
              textTransform: "uppercase",
            }}
          >
            How this differs from the Risk Board
          </h3>
          <p
            style={{
              fontSize: "12px",
              color: "var(--qgi-text-muted)",
              lineHeight: 1.6,
              margin: "0 0 10px",
            }}
          >
            This ranking sorts countries by shape similarity to any trajectory in the
            catalog, including trends still in review. It asks:{" "}
            <em>whose recent movement resembles something we have seen before?</em>
          </p>
          <p
            style={{
              fontSize: "12px",
              color: "var(--qgi-text-muted)",
              lineHeight: 1.6,
              margin: "0 0 10px",
            }}
          >
            The{" "}
            <Link href={"/risk-board" as Route} style={{ color: "var(--qgi-accent)" }}>
              Risk Board
            </Link>{" "}
            ranks only on deployed trends with their confidence bands. It asks:{" "}
            <em>where are we confident enough to put a number on the table?</em>
          </p>
          <p
            style={{
              fontSize: "11.5px",
              color: "var(--qgi-text-dim)",
              lineHeight: 1.55,
              margin: 0,
              fontStyle: "italic",
            }}
          >
            Use trajectories for structural exploration; use the Risk Board for
            decision-grade calls.
          </p>
        </aside>
      </div>
    </>
  );
}

function chipBtnStyle(active: boolean, accent?: string): React.CSSProperties {
  const color = accent ?? "var(--qgi-accent)";
  return {
    fontSize: "10.5px",
    padding: "4px 9px",
    background: active ? "rgba(56,189,248,0.1)" : "transparent",
    color: active ? color : "var(--qgi-text-muted)",
    border: `1px solid ${active ? color : "var(--qgi-border)"}`,
    borderRadius: "3px",
    cursor: "pointer",
    fontFamily: "ui-monospace, monospace",
    letterSpacing: "0.3px",
  };
}

function Th({
  children,
  active,
  dir,
  onClick,
  align = "left",
}: {
  children: React.ReactNode;
  active?: boolean;
  dir?: "asc" | "desc";
  onClick?: () => void;
  align?: "left" | "right";
}) {
  const isSortable = Boolean(onClick);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTableCellElement>) {
    if (onClick && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      onClick();
    }
  }

  return (
    <th
      scope="col"
      onClick={onClick}
      onKeyDown={isSortable ? handleKeyDown : undefined}
      tabIndex={isSortable ? 0 : undefined}
      // Intentionally NO role="button" — overriding the implicit
      // columnheader role would lose table semantics for screen readers.
      // scope="col" + aria-sort + tabIndex + onKeyDown provides full a11y.
      aria-sort={
        isSortable
          ? active
            ? dir === "asc"
              ? "ascending"
              : "descending"
            : "none"
          : undefined
      }
      style={{
        padding: "10px 12px",
        textAlign: align,
        fontSize: "9.5px",
        letterSpacing: "1.3px",
        textTransform: "uppercase",
        color: active ? "var(--qgi-accent)" : "var(--qgi-text-dim)",
        fontFamily: "ui-monospace, monospace",
        fontWeight: 600,
        cursor: isSortable ? "pointer" : "default",
        userSelect: "none",
        whiteSpace: "nowrap",
      }}
    >
      {children}
      {/* Active column: direction arrow */}
      {active && (
        <span style={{ marginLeft: "5px", fontSize: "9px" }}>
          {dir === "asc" ? "▲" : "▼"}
        </span>
      )}
      {/* Inactive sortable columns: neutral ↕ affordance at low opacity */}
      {isSortable && !active && (
        <span style={{ marginLeft: "4px", fontSize: "8px", opacity: 0.35 }} aria-hidden>
          ↕
        </span>
      )}
    </th>
  );
}
