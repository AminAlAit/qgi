/**
 * DriversPanel — drivers in two distinct sub-sections per R&D reply §Q4
 * (docs-specs #169):
 *
 *   §A "Why this country scores high"  — SHAP signal_share_pct per
 *      indicator on the top-lit recipe. Bar visualization. Capability #14.
 *
 *   §B "What's moving in the panels"   — raw indicator z-trajectory +
 *      z_score_change. Mini sparkline per indicator. Capability #15
 *      (observable substrate side).
 *
 * The two sub-sections must NEVER be conflated in copy. SHAP attribution
 * tells you the model's reason; indicator movement tells you the raw
 * substrate. The honest distinction is the whole point of the split.
 */
import type {
  CountryDriverAttribution,
  CountryDriverMovement,
} from "@/lib/te-mock/countries-v4-data";
import { getRecipe } from "@/lib/te-mock/recipes";
import { iconForRecipe } from "@/lib/te-mock/icons";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { familyColor as resolveFamilyColor } from "@/lib/te-mock/l1-families";

interface Props {
  attribution: readonly CountryDriverAttribution[];
  movement: readonly CountryDriverMovement[];
}

export function DriversPanel({ attribution, movement }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      <AttributionSection attribution={attribution} />
      <MovementSection movement={movement} />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   §A — SHAP attribution
   ═══════════════════════════════════════════════════════════════════════════ */

function AttributionSection({
  attribution,
}: {
  attribution: readonly CountryDriverAttribution[];
}) {
  if (attribution.length === 0) {
    return (
      <SubSection
        letter="A"
        title="Why this country scores high"
        copy="SHAP signal share unavailable: country has no top-lit recipe at the current release."
      >
        <EmptyBox text="No attribution surface yet." />
      </SubSection>
    );
  }

  // All attribution rows share the same recipe_id (per buildAttribution).
  const recipeId = attribution[0].recipe_id;
  const recipe = getRecipe(recipeId);
  // Route through resolveFamilyColor so the F-family override (#9F7AEA →
  // #6C77E8) and any future re-hues apply here too — same discipline as
  // the rest of the V4.1 surfaces.
  const familyColor = resolveFamilyColor(recipe?.l1_id ?? "", recipe?.l1_color);

  return (
    <SubSection
      letter="A"
      title="Why this country scores high"
      copy={
        <>
          SHAP attribution on the top-lit recipe (
          <strong>{recipe?.label ?? recipeId}</strong>): the share each indicator
          contributes to the country&apos;s discrimination rank. Sums to 100. This is the
          model&apos;s &ldquo;reason,&rdquo; not the underlying substrate movement (see §B
          below).
        </>
      }
      headerRight={
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "3px 8px",
            border: `1px solid ${familyColor}`,
            borderRadius: "4px",
            color: familyColor,
            fontSize: "10px",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.4px",
          }}
        >
          <RecipeIcon recipeId={recipeId} size={12} strokeWidth={1.6} />
          {recipe?.label ?? recipeId}
        </span>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {attribution.map((row) => (
          <AttributionRow key={row.indicator_code} row={row} color={familyColor} />
        ))}
      </div>
    </SubSection>
  );
}

function AttributionRow({
  row,
  color,
}: {
  row: CountryDriverAttribution;
  color: string;
}) {
  const pct = Math.max(0, Math.min(100, row.signal_share_pct));
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(180px, 260px) minmax(0, 1fr) 56px",
        gap: "12px",
        alignItems: "center",
        padding: "8px 10px",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "5px",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "9.5px",
            letterSpacing: "0.8px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            marginBottom: "2px",
          }}
        >
          {row.provider}
        </div>
        <div
          style={{
            fontSize: "12.5px",
            color: "var(--qgi-text)",
            fontWeight: 600,
            lineHeight: 1.25,
          }}
        >
          {row.indicator_name}
        </div>
      </div>
      {/* SHAP bar */}
      <div
        style={{
          position: "relative",
          height: "14px",
          background: "rgba(255,255,255,0.04)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "3px",
          overflow: "hidden",
        }}
        aria-label={`SHAP signal share ${pct.toFixed(1)}%`}
      >
        <div
          style={{
            position: "absolute",
            inset: "0 auto 0 0",
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}AA 0%, ${color} 100%)`,
            opacity: 0.85,
          }}
        />
      </div>
      <div
        style={{
          fontSize: "13px",
          fontWeight: 600,
          fontFamily: "ui-monospace, monospace",
          color,
          textAlign: "right",
        }}
      >
        {pct.toFixed(1)}%
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   §B — Panel z-deltas / indicator movement
   ═══════════════════════════════════════════════════════════════════════════ */

function MovementSection({ movement }: { movement: readonly CountryDriverMovement[] }) {
  if (movement.length === 0) {
    return (
      <SubSection
        letter="B"
        title="What&rsquo;s moving in the panels"
        copy="No indicator movement surfaced at the current release."
      >
        <EmptyBox text="Movement panel empty." />
      </SubSection>
    );
  }

  return (
    <SubSection
      letter="B"
      title="What's moving in the panels"
      copy={
        <>
          Observed z-trajectory of each driver indicator over the visible 12-quarter
          window. These are <strong>observed shifts in raw input series</strong>, not
          attribution to any single recipe&apos;s outcome.
        </>
      }
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
          gap: "10px",
        }}
      >
        {movement.map((d) => (
          <MovementCard key={d.indicator_code} driver={d} />
        ))}
      </div>
    </SubSection>
  );
}

function MovementCard({ driver }: { driver: CountryDriverMovement }) {
  const direction = driver.direction;
  const arrow =
    direction === "rising"
      ? "↑"
      : direction === "falling"
        ? "↓"
        : direction === "volatile"
          ? "↕"
          : "→";
  const dirColor =
    direction === "rising"
      ? "#E68F29"
      : direction === "falling"
        ? "#5EE6C4"
        : direction === "volatile"
          ? "#a78bfa"
          : "var(--qgi-text-muted)";

  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "6px",
        padding: "12px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "8px",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: "10px",
              letterSpacing: "0.8px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {driver.provider}
          </div>
          <div
            style={{
              fontSize: "12.5px",
              color: "var(--qgi-text)",
              fontWeight: 600,
              lineHeight: 1.25,
              marginTop: "2px",
            }}
          >
            {driver.indicator_name}
          </div>
        </div>
        <span
          style={{
            fontSize: "16px",
            fontFamily: "ui-monospace, monospace",
            color: dirColor,
            fontWeight: 600,
            lineHeight: 1,
          }}
        >
          {arrow}
        </span>
      </div>
      <DriverSpark trajectory={driver.trajectory} color={dirColor} />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "10px",
          color: "var(--qgi-text-muted)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        <code>{driver.indicator_code}</code>
        <span title="Observed z-shift across the visible 12-quarter window, not a forecast.">
          Δz {driver.z_score_change > 0 ? "+" : ""}
          {driver.z_score_change.toFixed(1)}
        </span>
      </div>
    </div>
  );
}

function DriverSpark({
  trajectory,
  color,
}: {
  trajectory: readonly number[];
  color: string;
}) {
  const width = 200;
  const height = 36;
  const pad = 2;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const min = Math.min(...trajectory) - 2;
  const max = Math.max(...trajectory) + 2;
  const range = max - min || 1;
  const xScale = (i: number) => pad + (i / (trajectory.length - 1)) * innerW;
  const yScale = (v: number) => pad + innerH - ((v - min) / range) * innerH;
  const d = trajectory
    .map(
      (v, i) => `${i === 0 ? "M" : "L"} ${xScale(i).toFixed(1)} ${yScale(v).toFixed(1)}`
    )
    .join(" ");

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="12-quarter indicator z-trajectory sparkline"
      style={{ display: "block" }}
    >
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} opacity={0.9} />
      <circle
        cx={xScale(trajectory.length - 1)}
        cy={yScale(trajectory[trajectory.length - 1])}
        r={2.4}
        fill={color}
      />
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Shared helpers
   ═══════════════════════════════════════════════════════════════════════════ */

function SubSection({
  letter,
  title,
  copy,
  headerRight,
  children,
}: {
  letter: "A" | "B";
  title: React.ReactNode;
  copy: React.ReactNode;
  headerRight?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "12px",
          marginBottom: "8px",
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            letterSpacing: "1.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          §{letter}
        </span>
        <h3
          style={{
            fontSize: "14px",
            fontWeight: 600,
            margin: 0,
            color: "var(--qgi-text)",
            flex: 1,
          }}
        >
          {title}
        </h3>
        {headerRight}
      </div>
      <p
        style={{
          fontSize: "12px",
          color: "var(--qgi-text-muted)",
          marginTop: 0,
          marginBottom: "10px",
          maxWidth: "640px",
          lineHeight: 1.55,
        }}
      >
        {copy}
      </p>
      {children}
    </div>
  );
}

function EmptyBox({ text }: { text: string }) {
  return (
    <div
      style={{
        padding: "16px",
        border: "1px dashed var(--qgi-border)",
        borderRadius: "6px",
        textAlign: "center",
        fontSize: "12px",
        color: "var(--qgi-text-muted)",
        fontStyle: "italic",
      }}
    >
      {text}
    </div>
  );
}
