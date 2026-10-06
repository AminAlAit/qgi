/**
 * BoardTeaser — compact 6×4 mini-grid teaser of the HF board.
 *
 * Shows the 6 countries with the most ACTIVE/SIGNAL cells,
 * across the 4 topics that appear most often in those verdicts.
 * Links the whole grid to /risk-board.
 *
 * Server component — BoardTeaserCell is also server.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { PanelBase } from "@/components/dashboard-v4-1/PanelBase";
import { BoardTeaserCell } from "./BoardTeaserCell";
import type { HfBoard, HfCell } from "@/lib/hf/topics-data";

interface BoardTeaserProps {
  board: HfBoard;
  cells: Record<string, HfCell>;
}

export function BoardTeaser({ board, cells }: BoardTeaserProps) {
  // ── Select the 6 most-active countries ────────────────────────────────────
  const countrySignalCount: Record<string, number> = {};
  for (const [key, cell] of Object.entries(cells)) {
    if (cell.verdict !== "ACTIVE" && cell.verdict !== "SIGNAL") continue;
    const iso3 = key.split("|")[0];
    if (!iso3) continue;
    countrySignalCount[iso3] = (countrySignalCount[iso3] ?? 0) + 1;
  }
  const topCountries = board.countries
    .filter((c) => countrySignalCount[c.iso3] != null)
    .sort((a, b) => (countrySignalCount[b.iso3] ?? 0) - (countrySignalCount[a.iso3] ?? 0))
    .slice(0, 6);

  // ── Select the 4 most-active topics ───────────────────────────────────────
  const topicSignalCount: Record<string, number> = {};
  for (const [key, cell] of Object.entries(cells)) {
    if (cell.verdict !== "ACTIVE" && cell.verdict !== "SIGNAL") continue;
    const topicId = key.split("|")[1];
    if (!topicId) continue;
    topicSignalCount[topicId] = (topicSignalCount[topicId] ?? 0) + 1;
  }
  const topTopics = board.topics
    .filter((t) => topicSignalCount[t.id] != null)
    .sort((a, b) => (topicSignalCount[b.id] ?? 0) - (topicSignalCount[a.id] ?? 0))
    .slice(0, 4);

  if (topCountries.length === 0 || topTopics.length === 0) return null;

  const rightSlot = (
    <Link
      href={"/risk-board" as Route}
      style={{
        fontFamily: "ui-monospace, monospace",
        fontSize: "11px",
        color: "var(--qgi-accent)",
        textDecoration: "none",
      }}
    >
      → Full board
    </Link>
  );

  return (
    <PanelBase
      title="The Board · Top Signals"
      accent="#5B7E99"
      caption={`The board's hottest cells — where structural resemblance and live news coverage are both elevated. ${topCountries.length} countries with the most active signals this release.`}
      rightSlot={rightSlot}
    >
      <style>{`
        .qgi-board-teaser-grid {
          display: grid;
          grid-template-columns: 80px repeat(${topTopics.length}, 60px);
          gap: 2px;
          overflow-x: auto;
        }
        @media (max-width: 639px) {
          .qgi-board-teaser-grid {
            grid-template-columns: 72px repeat(2, 60px);
          }
        }
      `}</style>

      <Link
        href={"/risk-board" as Route}
        style={{ textDecoration: "none", color: "inherit", display: "block" }}
      >
        <div className="qgi-board-teaser-grid">
          {/* Header row: empty corner + topic labels */}
          <div style={{ height: "24px" }} />
          {topTopics.map((topic) => (
            <div
              key={topic.id}
              title={topic.label}
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                textTransform: "uppercase",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                height: "24px",
                display: "flex",
                alignItems: "flex-end",
                paddingBottom: "2px",
              }}
            >
              {topic.label}
            </div>
          ))}

          {/* Data rows */}
          {topCountries.map((country) => (
            <>
              {/* Row header */}
              <div
                key={`row-${country.iso3}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "5px",
                  fontSize: "11px",
                  color: "var(--qgi-text)",
                  overflow: "hidden",
                  whiteSpace: "nowrap",
                  paddingRight: "4px",
                }}
              >
                <FlagImg
                  emoji={flagFor(country.name)}
                  name={country.name}
                  width={14}
                  radius={1}
                />
                <span
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {country.name.length > 8 ? country.name.slice(0, 8) : country.name}
                </span>
              </div>

              {/* Cells */}
              {topTopics.map((topic) => {
                const cellKey = `${country.iso3}|${topic.id}`;
                const cell = cells[cellKey];
                return (
                  <BoardTeaserCell
                    key={`${country.iso3}-${topic.id}`}
                    struct={cell?.struct ?? null}
                    pulse={cell?.pulse ?? 0}
                    verdict={
                      cell
                        ? (cell.verdict as "ACTIVE" | "SIGNAL" | "LATENT" | "QUIET")
                        : "EMPTY"
                    }
                  />
                );
              })}
            </>
          ))}
        </div>
      </Link>
    </PanelBase>
  );
}
