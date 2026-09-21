/**
 * MatchAlignmentPanel + CompositeOverlayPanel — the core visuals of the
 * (country x recipe) page.
 *
 * MatchAlignmentPanel (the founder's spec): per indicator, overlay the path
 * the recipe followed in the run-up to past cases (the family-colour band +
 * mean line, from the methodology bake) with how this country has actually
 * moved (white). Where the white line traces the band, the country is
 * following the recipe on that signal. Shapes are compared, not the calendar
 * (QGI scores movement shape) — so both series share a normalized run-up
 * axis. Real data: country path from fleet-run-1, canonical shape from the
 * methodology bake. Where no canonical shape exists for a recipe yet, the row
 * shows the country's own path and a "canonical shape pending" note.
 *
 * CompositeOverlayPanel: the country's overall composite path vs the real
 * paths of the historical cases it most resembles (the analogues).
 *
 * Server components: static SVG, no interactivity.
 */
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { MiniSparkline } from "@/components/countries-v4-1/MiniSparkline";
import type { MatchIndicator, MatchAnalogue } from "@/lib/te-mock/country-recipe-match";

const WHITE = "#FFFFFF";
const OFF_SHAPE = "#5B7E99";

function zoneTone(zone: string | null, familyColor: string): string {
  if (zone === "HIGH") return familyColor;
  if (zone === "MED") return "#7A8FA0";
  return "#5B7E99";
}

/* ─────────────────────────────────────────────────────────────────────────
 * Core: per-indicator canonical-vs-country overlay
 * ───────────────────────────────────────────────────────────────────────── */
export function MatchAlignmentPanel({
  familyColor,
  countryName,
  evalYear,
  zone,
  zoneLabel,
  indicators,
}: {
  familyColor: string;
  countryName: string;
  evalYear: number;
  zone: string | null;
  zoneLabel: string | null;
  indicators: MatchIndicator[];
}) {
  const anyCanon = indicators.some((i) => i.canonicalMean && i.canonicalMean.length > 0);

  return (
    <PanelShell
      title={`How ${countryName} is following this trend`}
      accent={familyColor}
      dataTour="match-alignment-panel"
      caption={
        anyCanon
          ? `For each of the trend's signals: the shape it typically traced in the run-up to past cases (the shaded band and line), beside how ${countryName}'s signal has actually moved recently (white). The overall resemblance is the score above; this panel lays the trend's run-up shape next to ${countryName}'s movement, signal by signal. Shapes are compared, not the calendar.`
          : `How each of the trend's signals has moved for ${countryName} over recent years. The trend's canonical shape for these signals is being computed for this release; the comparison line will appear here once it lands.`
      }
    >
      {zoneLabel && (
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            alignSelf: "flex-start",
            marginBottom: "16px",
            padding: "5px 12px",
            borderRadius: "4px",
            border: `1px solid ${zoneTone(zone, familyColor)}`,
            background: `${zoneTone(zone, familyColor)}1A`,
          }}
        >
          <span
            style={{
              fontSize: "12.5px",
              color: zoneTone(zone, familyColor),
              fontWeight: 600,
            }}
          >
            {countryName}&apos;s recent {zoneLabel}
          </span>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        {indicators.map((ind) => (
          <IndicatorOverlayRow key={ind.code} indicator={ind} familyColor={familyColor} />
        ))}
      </div>

      {anyCanon && (
        <footer
          style={{
            marginTop: "16px",
            paddingTop: "12px",
            borderTop: "1px dashed var(--qgi-border)",
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            letterSpacing: "0.3px",
            display: "flex",
            alignItems: "center",
            gap: "16px",
            flexWrap: "wrap",
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
            <span
              style={{
                width: "16px",
                height: "2.5px",
                background: WHITE,
                display: "inline-block",
              }}
            />
            {countryName}&apos;s recent path
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
            <span
              style={{
                width: "16px",
                height: "9px",
                background: familyColor,
                opacity: 0.18,
                border: `1px solid ${familyColor}55`,
                display: "inline-block",
              }}
            />
            the trend&apos;s run-up shape
          </span>
          <span style={{ marginLeft: "auto" }}>earlier &rarr; today ({evalYear})</span>
        </footer>
      )}
    </PanelShell>
  );
}

/** Linear-interpolate an N-point array at normalized position t in [0,1]. */
function interp(arr: number[], t: number): number {
  const N = arr.length;
  if (N === 0) return 0;
  if (N === 1) return arr[0];
  const pos = Math.max(0, Math.min(1, t)) * (N - 1);
  const i = Math.floor(pos);
  if (i >= N - 1) return arr[N - 1];
  return arr[i] * (1 - (pos - i)) + arr[i + 1] * (pos - i);
}

function IndicatorOverlayRow({
  indicator,
  familyColor,
}: {
  indicator: MatchIndicator;
  familyColor: string;
}) {
  const hasCanon = !!(indicator.canonicalMean && indicator.canonicalMean.length > 0);
  const z = indicator.zChange;
  const zStr = `${z > 0 ? "+" : ""}${Math.abs(z) < 10 ? z.toFixed(1) : z.toFixed(0)}z`;
  const dirWord =
    indicator.direction === "rising"
      ? "rose"
      : indicator.direction === "falling"
        ? "fell"
        : "held";
  const dirGlyph =
    indicator.direction === "rising"
      ? "▲"
      : indicator.direction === "falling"
        ? "▼"
        : "▬";

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(180px, 230px) 1fr",
        gap: "16px",
        alignItems: "center",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "9px",
            letterSpacing: "0.8px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            marginBottom: "2px",
            textTransform: "uppercase",
          }}
        >
          {indicator.provider}
        </div>
        <div
          style={{
            fontSize: "13px",
            color: "var(--qgi-text)",
            fontWeight: 600,
            lineHeight: 1.3,
            marginBottom: "6px",
          }}
          title={indicator.code}
        >
          {indicator.name}
        </div>
        <div
          style={{
            fontSize: "10.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
          title="How much this signal counts toward the score for this trend."
        >
          {indicator.weightPct.toFixed(0)}% of the signal
        </div>
        <div
          style={{
            fontSize: "10.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            marginTop: "4px",
          }}
          title="Standardized change over the visible window. Recent movement only, not a projection."
        >
          <span style={{ fontSize: "9px" }} aria-hidden>
            {dirGlyph}
          </span>{" "}
          {dirWord} {zStr}
        </div>
      </div>

      {hasCanon ? (
        <CanonOverlaySvg indicator={indicator} familyColor={familyColor} />
      ) : (
        <div>
          <MiniSparkline
            values={indicator.trajectory}
            color={WHITE}
            width={320}
            height={34}
            min={-Math.max(...indicator.trajectory.map((v) => Math.abs(v)), 1) - 0.3}
            max={Math.max(...indicator.trajectory.map((v) => Math.abs(v)), 1) + 0.3}
          />
          <div
            style={{
              fontSize: "9.5px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              fontStyle: "italic",
              marginTop: "2px",
            }}
          >
            canonical shape pending this release
          </div>
        </div>
      )}
    </div>
  );
}

function CanonOverlaySvg({
  indicator,
  familyColor,
}: {
  indicator: MatchIndicator;
  familyColor: string;
}) {
  const mean = indicator.canonicalMean!;
  const p25 = indicator.canonicalP25!;
  const p75 = indicator.canonicalP75!;
  const country = indicator.trajectory;

  const W = 520;
  const H = 92;
  const padT = 8;
  const padB = 14;
  const padL = 6;
  const padR = 6;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const all = [...mean, ...p25, ...p75, ...country];
  const absMax = Math.max(...all.map((v) => Math.abs(v)), 1);
  const maxY = absMax + 0.25;
  const minY = -absMax - 0.25;

  const xShape = (i: number) =>
    padL + (mean.length <= 1 ? innerW : (i / (mean.length - 1)) * innerW);
  const xCtry = (j: number) =>
    padL + (country.length <= 1 ? innerW : (j / (country.length - 1)) * innerW);
  const yFor = (v: number) => padT + innerH - ((v - minY) / (maxY - minY)) * innerH;

  const bandTop = p75
    .map((v, i) => `${xShape(i).toFixed(1)},${yFor(v).toFixed(1)}`)
    .join(" ");
  const bandBottom = p25
    .map((v, i) => `${xShape(i).toFixed(1)},${yFor(v).toFixed(1)}`)
    .reverse()
    .join(" ");
  const meanPath = mean
    .map((v, i) => `${i === 0 ? "M" : "L"} ${xShape(i).toFixed(1)} ${yFor(v).toFixed(1)}`)
    .join(" ");
  const ctryPath = country
    .map((v, i) => `${i === 0 ? "M" : "L"} ${xCtry(i).toFixed(1)} ${yFor(v).toFixed(1)}`)
    .join(" ");

  const driftDots = country
    .map((v, j) => {
      const t = country.length <= 1 ? 1 : j / (country.length - 1);
      const lo = Math.min(interp(p25, t), interp(p75, t));
      const hi = Math.max(interp(p25, t), interp(p75, t));
      return v < lo || v > hi ? { x: xCtry(j), y: yFor(v) } : null;
    })
    .filter((d): d is { x: number; y: number } => d !== null);

  const lastX = xCtry(country.length - 1);
  const lastY = yFor(country[country.length - 1]);

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`${indicator.name}: ${"country"} path over the trend's canonical run-up shape`}
      style={{ display: "block" }}
      preserveAspectRatio="none"
    >
      <line
        x1={padL}
        x2={padL + innerW}
        y1={yFor(0)}
        y2={yFor(0)}
        stroke="var(--qgi-border)"
        strokeDasharray="2 3"
        strokeWidth={0.6}
      />
      <polygon points={`${bandTop} ${bandBottom}`} fill={familyColor} opacity={0.16} />
      <path
        d={meanPath}
        fill="none"
        stroke={familyColor}
        strokeWidth={1.6}
        opacity={0.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {driftDots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={2} fill={OFF_SHAPE} opacity={0.7} />
      ))}
      <path
        d={ctryPath}
        fill="none"
        stroke={WHITE}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r={2.8} fill={WHITE} />
      <line
        x1={padL + innerW}
        x2={padL + innerW}
        y1={padT}
        y2={padT + innerH}
        stroke="var(--qgi-text-dim)"
        strokeDasharray="1 2"
        strokeWidth={0.6}
      />
    </svg>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
 * Secondary: overall composite path vs the historical cases it resembles
 * ───────────────────────────────────────────────────────────────────────── */
export function CompositeOverlayPanel({
  familyColor,
  countryName,
  windowYears,
  evalYear,
  composite,
  analogues,
}: {
  familyColor: string;
  countryName: string;
  windowYears: number;
  evalYear: number;
  composite: number[];
  analogues: MatchAnalogue[];
}) {
  const analoguePaths = analogues.filter((a) => a.path && a.path.length > 1);
  if (composite.length <= 1) return null;

  const W = 720;
  const H = 140;
  const padT = 10;
  const padB = 22;
  const padL = 8;
  const padR = 8;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const allPaths = [composite, ...analoguePaths.map((a) => a.path as number[])];
  const flat = allPaths.flat();
  const absMax = Math.max(...flat.map((v) => Math.abs(v)), 1);
  const maxY = absMax + 0.3;
  const minY = -absMax - 0.3;

  const xFor = (i: number, n: number) =>
    padL + (n <= 1 ? innerW : (i / (n - 1)) * innerW);
  const yFor = (v: number) => padT + innerH - ((v - minY) / (maxY - minY)) * innerH;
  const pathD = (arr: number[]) =>
    arr
      .map(
        (v, i) =>
          `${i === 0 ? "M" : "L"} ${xFor(i, arr.length).toFixed(1)} ${yFor(v).toFixed(1)}`
      )
      .join(" ");

  const lastX = xFor(composite.length - 1, composite.length);
  const lastY = yFor(composite[composite.length - 1]);

  return (
    <PanelShell
      title="Overall path vs the cases it resembles"
      accent={familyColor}
      caption={`${countryName}'s overall signal path over the last ${windowYears} years (white), with the real paths of the historical cases it most resembles (faint). Where the lines run together, ${countryName} is moving the way those cases moved.`}
    >
      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${countryName}'s composite path overlaid on the historical cases it resembles`}
        style={{ display: "block" }}
        preserveAspectRatio="none"
      >
        <line
          x1={padL}
          x2={padL + innerW}
          y1={yFor(0)}
          y2={yFor(0)}
          stroke="var(--qgi-border)"
          strokeDasharray="2 3"
          strokeWidth={0.6}
        />
        {analoguePaths.map((a) => (
          <path
            key={`${a.country}-${a.year}`}
            d={pathD(a.path as number[])}
            fill="none"
            stroke={familyColor}
            strokeWidth={1.4}
            opacity={0.4}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
        <path
          d={pathD(composite)}
          fill="none"
          stroke={WHITE}
          strokeWidth={2.4}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={lastX} cy={lastY} r={3} fill={WHITE} />
        <line
          x1={padL + innerW}
          x2={padL + innerW}
          y1={padT}
          y2={padT + innerH}
          stroke="var(--qgi-text-dim)"
          strokeDasharray="1 2"
          strokeWidth={0.6}
        />
        <text
          x={padL}
          y={H - 6}
          fontSize="9"
          fill="var(--qgi-text-dim)"
          fontFamily="ui-monospace, monospace"
        >
          {windowYears} years ago
        </text>
        <text
          x={padL + innerW}
          y={H - 6}
          fontSize="9"
          fill="var(--qgi-text-dim)"
          fontFamily="ui-monospace, monospace"
          textAnchor="end"
        >
          today ({evalYear})
        </text>
      </svg>
      <div
        style={{
          display: "flex",
          gap: "16px",
          flexWrap: "wrap",
          marginTop: "8px",
          fontFamily: "ui-monospace, monospace",
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          letterSpacing: "0.3px",
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              width: "16px",
              height: "2.5px",
              background: WHITE,
              display: "inline-block",
            }}
          />
          {countryName}
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              width: "16px",
              height: "2px",
              background: familyColor,
              opacity: 0.4,
              display: "inline-block",
            }}
          />
          {analoguePaths.length} historical case{analoguePaths.length === 1 ? "" : "s"} it
          resembles
        </span>
      </div>
    </PanelShell>
  );
}
