/**
 * CompareMatrix — the editorial center of /compare.
 *
 * Rows: union of A's and B's lit recipes, sorted by max score descending.
 * Each row: 3px left-edge stripe, recipe label, L1 family chip, parallel rank
 * bars for A and B, gap column, tracker status chip.
 *
 * Rows where only one country is in play: dashed "not in play" placeholder.
 * Rows where status is "walked_no_graduation" or vacated: 50% opacity + muted note.
 *
 * Marcus mitigation 3: closing lede sentence about muted rows.
 * Gap cell `title` attribute: rank difference framing.
 *
 * V4.1 bar: NEUTRAL_SLATE bars, familyColor() stripes, no em-dashes.
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { familyColor } from "@/lib/te-mock/l1-families";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";
import type { CompareGapRow } from "@/lib/te-mock/compare-data";

/** V4.1 §4 vocabulary — four audience buckets, no methodology jargon. */
function StatusChip({ status }: { status: string | null }) {
  if (!status) return null;
  const map: Record<string, { label: string; color: string }> = {
    graduated: { label: "Validated", color: "#3FBF8F" },
    in_progress: { label: "In play", color: "#5B7E99" },
    walked_no_graduation: { label: "In play", color: "#5B7E99" },
    live_legacy: { label: "Prior version", color: "#7A8FA0" },
    queued: { label: "Coming soon", color: "#7A8FA0" },
  };
  const entry = map[status] ?? { label: status, color: "#7A8FA0" };
  return (
    <span
      style={{
        fontSize: "9px",
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.4px",
        padding: "2px 6px",
        border: `1px solid ${entry.color}66`,
        borderRadius: "3px",
        color: entry.color,
        background: `${entry.color}14`,
        whiteSpace: "nowrap",
        textTransform: "uppercase",
      }}
    >
      {entry.label}
    </span>
  );
}

// Rank bar cell: 0..100 bar in NEUTRAL_SLATE on faint track.
function RankBar({ score, muted }: { score: number | null; muted: boolean }) {
  if (score === null) {
    return (
      <div
        style={{
          flex: 1,
          border: "1px dashed var(--qgi-border)",
          borderRadius: "3px",
          height: "24px",
          display: "flex",
          alignItems: "center",
          paddingLeft: "8px",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            fontStyle: "italic",
          }}
        >
          not in play
        </span>
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: "8px",
        opacity: muted ? 0.5 : 1,
      }}
    >
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "12px",
          fontWeight: 700,
          color: "var(--qgi-text)",
          width: "28px",
          textAlign: "right",
          flexShrink: 0,
        }}
      >
        {score.toFixed(0)}
      </span>
      <div
        style={{
          flex: 1,
          height: "6px",
          background: "var(--qgi-border)",
          borderRadius: "3px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${score}%`,
            height: "100%",
            background: NEUTRAL_SLATE,
            borderRadius: "3px",
          }}
        />
      </div>
    </div>
  );
}

function isMutedStatus(status: string | null): boolean {
  return status === "walked_no_graduation";
}

export function CompareMatrix({
  countryA,
  countryB,
  rows,
}: {
  countryA: CountryV4;
  countryB: CountryV4;
  rows: CompareGapRow[];
}) {
  const hasAnyMuted = rows.some(
    (r) => isMutedStatus(r.status_a) || isMutedStatus(r.status_b)
  );

  return (
    <section
      data-tour="compare-matrix"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "6px",
        overflow: "hidden",
      }}
    >
      {/* Table header */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "3px 1fr 90px 90px 52px 72px",
          gap: "0 10px",
          alignItems: "center",
          padding: "8px 14px 8px 0",
          borderBottom: "1px solid var(--qgi-border)",
          background: "var(--qgi-bg)",
        }}
      >
        <div />
        <div
          style={{
            fontSize: "9px",
            letterSpacing: "0.7px",
            textTransform: "uppercase",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            paddingLeft: "14px",
          }}
        >
          Trend
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "5px",
            fontSize: "9px",
            letterSpacing: "0.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            textTransform: "uppercase",
          }}
        >
          <FlagImg emoji={countryA.flag_emoji} name={countryA.name} width={12} />
          {countryA.iso}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "5px",
            fontSize: "9px",
            letterSpacing: "0.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            textTransform: "uppercase",
          }}
        >
          <FlagImg emoji={countryB.flag_emoji} name={countryB.name} width={12} />
          {countryB.iso}
        </div>
        <div
          style={{
            fontSize: "9px",
            letterSpacing: "0.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            textTransform: "uppercase",
            textAlign: "center",
          }}
        >
          Gap
        </div>
        <div
          style={{
            fontSize: "9px",
            letterSpacing: "0.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            textTransform: "uppercase",
          }}
        >
          Status
        </div>
      </div>

      {/* Rows */}
      {rows.map((row) => {
        const color = familyColor(row.l1_id, row.l1_color);
        const mutedA = isMutedStatus(row.status_a);
        const mutedB = isMutedStatus(row.status_b);
        const rowMuted = mutedA || mutedB;

        return (
          <div
            key={row.recipe_id}
            style={{
              display: "grid",
              gridTemplateColumns: "3px 1fr 90px 90px 52px 72px",
              gap: "0 10px",
              alignItems: "center",
              padding: "10px 14px 10px 0",
              borderBottom: "1px solid var(--qgi-border)",
              opacity: rowMuted ? 0.65 : 1,
            }}
          >
            {/* 3px family color stripe */}
            <div
              style={{
                width: "3px",
                height: "32px",
                background: color,
                borderRadius: "0 2px 2px 0",
                flexShrink: 0,
              }}
            />

            {/* Recipe label + family chip + "Both" chip */}
            <div
              style={{
                paddingLeft: "14px",
                display: "flex",
                flexDirection: "column",
                gap: "4px",
                minWidth: 0,
              }}
            >
              <span
                style={{
                  fontSize: "12.5px",
                  color: "var(--qgi-text)",
                  fontWeight: 500,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={row.label}
              >
                {row.label}
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                {/* Recipe-specific icon (Rule 1: chip is per-recipe; use the
                    recipe's canonical icon, never the family letter glyph). */}
                <span
                  title={`${row.label} (${row.l1_id} · ${row.l1_label})`}
                  aria-label={`${row.label}, ${row.l1_label} family`}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "20px",
                    height: "20px",
                    border: `1px solid ${color}99`,
                    borderRadius: "3px",
                    color,
                    background: `${color}14`,
                    flexShrink: 0,
                  }}
                >
                  <RecipeIcon recipeId={row.recipe_id} size={13} strokeWidth={1.8} />
                </span>
                {row.shared && (
                  <span
                    style={{
                      fontSize: "9px",
                      fontFamily: "ui-monospace, monospace",
                      padding: "1px 5px",
                      borderRadius: "3px",
                      color,
                      border: `1px solid ${color}55`,
                      background: `${color}12`,
                      letterSpacing: "0.3px",
                    }}
                  >
                    Both
                  </span>
                )}
                {rowMuted && (
                  <span
                    style={{
                      fontSize: "9px",
                      fontFamily: "ui-monospace, monospace",
                      color: "var(--qgi-text-dim)",
                      fontStyle: "italic",
                    }}
                  >
                    tested
                  </span>
                )}
              </div>
            </div>

            {/* Rank bar A */}
            <RankBar score={row.score_a} muted={mutedA} />

            {/* Rank bar B */}
            <RankBar score={row.score_b} muted={mutedB} />

            {/* Gap column */}
            <div
              title="Rank difference, not a probability difference. Both countries sit on the same trend distribution."
              style={{
                textAlign: "center",
                fontFamily: "ui-monospace, monospace",
                fontSize: "11px",
                fontWeight: 600,
                color:
                  row.gap === null
                    ? "var(--qgi-text-dim)"
                    : row.gap > 0
                      ? "#3FBF8F"
                      : row.gap < 0
                        ? "#E64545"
                        : "var(--qgi-text-muted)",
              }}
            >
              {row.gap === null
                ? "--"
                : row.gap > 0
                  ? `+${row.gap.toFixed(0)}`
                  : row.gap.toFixed(0)}
            </div>

            {/* Status chip */}
            <div>
              <StatusChip status={row.status_a ?? row.status_b} />
            </div>
          </div>
        );
      })}

      {/* Muted rows explanation — V4.1 §0 + §4: confidence-first framing.
          "Did not hold up" language replaced by active-rotation framing. */}
      {hasAnyMuted && (
        <div
          style={{
            padding: "10px 14px",
            fontSize: "11px",
            lineHeight: 1.5,
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            fontStyle: "italic",
            borderTop: "1px solid var(--qgi-border)",
          }}
        >
          Muted rows are trends In Play: in active rotation on the risk board while the
          next validation pass completes.
        </div>
      )}
    </section>
  );
}
