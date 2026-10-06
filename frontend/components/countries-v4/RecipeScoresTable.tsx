/**
 * RecipeScoresTable — the top-N recipe table for a country detail page.
 *
 * Each row: L1 colored bar + recipe icon + label + L1 chip + score bar
 *           + score number. Links to /trends/<recipe_id>.
 *
 * Per M8-R5: scores are discrimination ranks, surfaced as bars + number
 * on a 0..100 axis. No probability framing anywhere.
 */
import Link from "next/link";
import type { Route } from "next";
import { iconForRecipe } from "@/lib/te-mock/icons";
import type { CountryTopRecipe } from "@/lib/te-mock/countries-v4-data";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";

export function RecipeScoresTable({ rows }: { rows: readonly CountryTopRecipe[] }) {
  if (rows.length === 0) {
    return (
      <div
        style={{
          padding: "20px",
          border: "1px dashed var(--qgi-border)",
          borderRadius: "6px",
          textAlign: "center",
          fontSize: "13px",
          color: "var(--qgi-text-muted)",
          fontStyle: "italic",
        }}
      >
        No recipes currently lit for this country.
      </div>
    );
  }

  return (
    <div
      style={{
        border: "1px solid var(--qgi-border)",
        background: "var(--qgi-surface)",
        borderRadius: "8px",
        overflow: "hidden",
      }}
    >
      {rows.map((row, idx) => (
        <Row key={row.recipe_id} row={row} isLast={idx === rows.length - 1} />
      ))}
    </div>
  );
}

function Row({ row, isLast }: { row: CountryTopRecipe; isLast: boolean }) {
  const fillPct = Math.max(0, Math.min(100, row.score));
  const statusMeta = STATUS_META[row.status] ?? STATUS_META.queued;

  return (
    <Link
      href={`/trends/${row.recipe_id}` as Route}
      style={{ textDecoration: "none", color: "inherit", display: "block" }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "36px minmax(180px, 1.4fr) 110px minmax(120px, 1fr) 64px",
          alignItems: "center",
          gap: "12px",
          padding: "10px 12px",
          borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
          borderLeft: `3px solid ${row.l1_color}`,
        }}
      >
        <div
          style={{
            width: "28px",
            height: "28px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: row.l1_color,
            background: `${row.l1_color}1A`,
            border: `1px solid ${row.l1_color}`,
            borderRadius: "5px",
            flexShrink: 0,
          }}
        >
          <RecipeIcon recipeId={row.recipe_id} size={16} strokeWidth={1.7} />
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              lineHeight: 1.25,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {row.label}
          </div>
          <div
            style={{
              fontSize: "10px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
              marginTop: "2px",
            }}
          >
            {row.l1_id} · {row.l1_label}
          </div>
        </div>
        <span
          style={{
            fontSize: "9.5px",
            padding: "2px 7px",
            borderRadius: "10px",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
            background: statusMeta.bgAlpha,
            color: statusMeta.color,
            border: `1px solid ${statusMeta.color}`,
            whiteSpace: "nowrap",
            justifySelf: "start",
          }}
        >
          {statusMeta.label}
        </span>
        <div
          style={{
            position: "relative",
            height: "8px",
            background: "var(--qgi-bg)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "4px",
            overflow: "hidden",
          }}
          role="img"
          aria-label={`Discrimination rank: ${row.score} of 100`}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              width: `${fillPct}%`,
              background: row.l1_color,
              opacity: 0.45 + 0.5 * (row.score / 100),
              borderRadius: "3px",
            }}
          />
        </div>
        <div style={{ textAlign: "right" }}>
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "15px",
              fontWeight: 600,
              color: row.l1_color,
              lineHeight: 1,
            }}
          >
            {row.score.toFixed(1)}
          </span>
          <div
            style={{
              fontSize: "9px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
              marginTop: "2px",
            }}
            title="Discrimination rank on the recipe's canonical movement shape, not a probability."
          >
            rank
          </div>
        </div>
      </div>
    </Link>
  );
}

const STATUS_META: Record<string, { label: string; color: string; bgAlpha: string }> = {
  graduated: { label: "Validated", color: "#3FBF8F", bgAlpha: "rgba(63,191,143,0.15)" },
  walked_no_graduation: {
    label: "Walked-failed",
    color: "#E68F29",
    bgAlpha: "rgba(230,143,41,0.15)",
  },
  in_progress: {
    label: "In flight",
    color: "#a78bfa",
    bgAlpha: "rgba(167,139,250,0.15)",
  },
  live_legacy: {
    label: "Legacy ML-1",
    color: "#7A8FA0",
    bgAlpha: "rgba(122,143,160,0.15)",
  },
  queued: { label: "Queued", color: "#64748b", bgAlpha: "rgba(100,116,139,0.15)" },
};
