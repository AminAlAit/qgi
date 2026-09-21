/**
 * Sanctions Simulator — charts (pure, deterministic from props).
 *
 * Inline SVG / HTML, no chart library, dark theme. Rendered inside the client
 * SanctionsSimulator but use no hooks themselves.
 *
 * Color semantics: a resemblance RISING / a level FALLING = red (deteriorating
 * or drifting toward); the opposite = green; near-flat = slate. Tier color
 * (amber -> red -> deep red) carries hardness on the indicator + composite views.
 */
import {
  COUNTRIES,
  INDICATORS,
  LEAD_IN,
  TIERS,
  type TierId,
  type TrendShift,
  compositeSeries,
  country,
  indicatorSeries,
  tier,
} from "@/lib/sanctions-sim/model";

const MUTED = "var(--qgi-text-muted)";
const DIM = "var(--qgi-text-dim)";
const BORDER = "var(--qgi-border)";
const RISE = "#E64545"; // resemblance rising / level deteriorating
const FALL = "#3FBF8F"; // resemblance falling / improvement
const FLAT = "#5B7E99";

void COUNTRIES; // referenced for type locality; data accessed via country()

function dirColor(delta: number): string {
  if (Math.abs(delta) < 3) return FLAT;
  return delta > 0 ? RISE : FALL;
}

/* ─────────────────────────── Composite divergence fan ─────────────────── */

export function CompositeFan({
  iso2,
  tierId,
  horizon,
}: {
  iso2: string;
  tierId: TierId;
  horizon: number;
}) {
  const c = country(iso2);
  const W = 720;
  const H = 320;
  const pad = { t: 26, r: 104, b: 36, l: 30 };
  const x0 = -LEAD_IN;
  const x1 = horizon;
  const sx = (t: number) => pad.l + ((t - x0) / (x1 - x0)) * (W - pad.l - pad.r);
  const sy = (v: number) => pad.t + (1 - v / 100) * (H - pad.t - pad.b);

  const selected = compositeSeries(c, tierId, horizon);
  const baseV = selected[0].baseline;
  const tiers = TIERS.map((t) => ({ def: t, s: compositeSeries(c, t.id, horizon) }));

  const line = (s: { t: number; sim: number }[]) =>
    s
      .map(
        (p, i) => `${i === 0 ? "M" : "L"} ${sx(p.t).toFixed(1)} ${sy(p.sim).toFixed(1)}`
      )
      .join(" ");
  const bandPath = (s: { t: number; lo: number; hi: number }[]) => {
    const top = s.map((p) => `${sx(p.t).toFixed(1)} ${sy(p.hi).toFixed(1)}`);
    const bot = s
      .slice()
      .reverse()
      .map((p) => `${sx(p.t).toFixed(1)} ${sy(p.lo).toFixed(1)}`);
    return `M ${top.join(" L ")} L ${bot.join(" L ")} Z`;
  };

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      role="img"
      aria-label="Composite trajectory under sanctions"
      style={{ display: "block" }}
    >
      {/* y gridlines */}
      {[0, 25, 50, 75, 100].map((g) => (
        <g key={g}>
          <line
            x1={pad.l}
            x2={W - pad.r}
            y1={sy(g)}
            y2={sy(g)}
            stroke={BORDER}
            strokeWidth={0.5}
            opacity={0.5}
          />
          <text
            x={pad.l - 6}
            y={sy(g) + 3}
            fontSize={8}
            fill={DIM}
            textAnchor="end"
            fontFamily="ui-monospace, monospace"
          >
            {g}
          </text>
        </g>
      ))}

      {/* pre-onset shading */}
      <rect
        x={sx(x0)}
        y={pad.t}
        width={sx(0) - sx(x0)}
        height={H - pad.t - pad.b}
        fill="rgba(255,255,255,0.015)"
      />
      {/* onset marker */}
      <line
        x1={sx(0)}
        x2={sx(0)}
        y1={pad.t}
        y2={H - pad.b}
        stroke={DIM}
        strokeWidth={0.8}
        strokeDasharray="3 3"
      />
      <text
        x={sx(0)}
        y={pad.t - 8}
        fontSize={8.5}
        fill={DIM}
        textAnchor="middle"
        fontFamily="ui-monospace, monospace"
      >
        ONSET
      </text>

      {/* today reference */}
      <line
        x1={pad.l}
        x2={W - pad.r}
        y1={sy(baseV)}
        y2={sy(baseV)}
        stroke={MUTED}
        strokeWidth={0.8}
        strokeDasharray="1 3"
        opacity={0.6}
      />

      {/* selected tier band */}
      <path d={bandPath(selected)} fill={tier(tierId).color} opacity={0.1} />

      {/* baseline (no sanctions) flat line */}
      <path
        d={line(selected.map((p) => ({ t: p.t, sim: p.baseline })))}
        fill="none"
        stroke={MUTED}
        strokeWidth={1.4}
        opacity={0.55}
      />

      {/* tier lines: others dashed thin, selected thick solid */}
      {tiers.map(({ def, s }) => {
        const isSel = def.id === tierId;
        return (
          <g key={def.id}>
            <path
              d={line(s)}
              fill="none"
              stroke={def.color}
              strokeWidth={isSel ? 2.6 : 1.1}
              strokeDasharray={isSel ? undefined : "4 3"}
              opacity={isSel ? 1 : 0.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <circle
              cx={sx(s[s.length - 1].t)}
              cy={sy(s[s.length - 1].sim)}
              r={isSel ? 3.4 : 2.2}
              fill={def.color}
              opacity={isSel ? 1 : 0.6}
            />
            <text
              x={W - pad.r + 8}
              y={sy(s[s.length - 1].sim) + 3}
              fontSize={isSel ? 10 : 8.5}
              fill={def.color}
              fontWeight={isSel ? 700 : 400}
              fontFamily="ui-monospace, monospace"
              opacity={isSel ? 1 : 0.75}
            >
              {def.label} {Math.round(s[s.length - 1].sim)}
            </text>
          </g>
        );
      })}

      {/* baseline end label */}
      <text
        x={W - pad.r + 8}
        y={sy(baseV) + 3}
        fontSize={8.5}
        fill={MUTED}
        fontFamily="ui-monospace, monospace"
        opacity={0.7}
      >
        Baseline {Math.round(baseV)}
      </text>

      {/* x labels */}
      {Array.from({ length: x1 - x0 + 1 }, (_, i) => x0 + i)
        .filter((t) => t === x0 || t === 0 || t === x1 || t % 1 === 0)
        .map((t) => (
          <text
            key={t}
            x={sx(t)}
            y={H - pad.b + 14}
            fontSize={8}
            fill={DIM}
            textAnchor="middle"
            fontFamily="ui-monospace, monospace"
          >
            {t === 0 ? "0" : t > 0 ? `+${t}` : t}
          </text>
        ))}
      <text
        x={(pad.l + (W - pad.r)) / 2}
        y={H - 3}
        fontSize={8}
        fill={DIM}
        textAnchor="middle"
        fontFamily="ui-monospace, monospace"
      >
        years from sanctions onset
      </text>
    </svg>
  );
}

/* ─────────────────────────── Indicator bend tile ──────────────────────── */

export function IndicatorBend({
  iso2,
  code,
  tierId,
  horizon,
}: {
  iso2: string;
  code: string;
  tierId: TierId;
  horizon: number;
}) {
  const c = country(iso2);
  const def = INDICATORS.find((i) => i.code === code)!;
  const s = indicatorSeries(c, code, tierId, horizon);
  const color = tier(tierId).color;
  const W = 200;
  const H = 70;
  const pad = { t: 8, r: 8, b: 10, l: 8 };
  const x0 = -LEAD_IN;
  const x1 = horizon;
  const sx = (t: number) => pad.l + ((t - x0) / (x1 - x0)) * (W - pad.l - pad.r);
  const sy = (v: number) => pad.t + (1 - v / 100) * (H - pad.t - pad.b);
  const line = (sel: (p: (typeof s)[number]) => number) =>
    s
      .map(
        (p, i) => `${i === 0 ? "M" : "L"} ${sx(p.t).toFixed(1)} ${sy(sel(p)).toFixed(1)}`
      )
      .join(" ");
  const bandPath = () => {
    const top = s.map((p) => `${sx(p.t).toFixed(1)} ${sy(p.hi).toFixed(1)}`);
    const bot = s
      .slice()
      .reverse()
      .map((p) => `${sx(p.t).toFixed(1)} ${sy(p.lo).toFixed(1)}`);
    return `M ${top.join(" L ")} L ${bot.join(" L ")} Z`;
  };
  const end = s[s.length - 1];
  const delta = Math.round(end.sim - end.baseline);

  return (
    <div
      style={{
        background: "var(--qgi-bg)",
        border: `1px solid ${BORDER}`,
        borderRadius: 8,
        padding: "10px 12px 8px",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--qgi-text)" }}>
          {def.short}
        </span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            fontFamily: "ui-monospace, monospace",
            color,
          }}
        >
          {delta} pts
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        preserveAspectRatio="none"
        style={{ height: 44 }}
        aria-hidden="true"
      >
        <line
          x1={sx(0)}
          x2={sx(0)}
          y1={pad.t}
          y2={H - pad.b}
          stroke={DIM}
          strokeWidth={0.6}
          strokeDasharray="2 2"
          opacity={0.5}
        />
        <path d={bandPath()} fill={color} opacity={0.12} />
        <path
          d={line((p) => p.baseline)}
          fill="none"
          stroke={MUTED}
          strokeWidth={1.3}
          opacity={0.55}
        />
        <path
          d={line((p) => p.sim)}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle cx={sx(end.t)} cy={sy(end.sim)} r={2.4} fill={color} />
      </svg>
      <span
        style={{
          fontSize: 8.5,
          color: DIM,
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        {def.category} · level 0–100
      </span>
    </div>
  );
}

/* ─────────────────────────── Trend dumbbell ───────────────────────────── */

export function TrendDumbbell({ shifts }: { shifts: TrendShift[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {shifts.map((row) => {
        const suppressed = !!row.suppressed;
        const color = suppressed ? FLAT : dirColor(row.delta);
        const lo = Math.min(row.current, row.sim);
        const hi = Math.max(row.current, row.sim);
        return (
          <div
            key={row.id}
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 150px) 1fr 42px",
              gap: 10,
              alignItems: "center",
              padding: "6px 2px",
              borderBottom: `1px solid ${BORDER}`,
              opacity: suppressed ? 0.5 : 1,
            }}
            title={suppressed ? row.note : undefined}
          >
            <span
              style={{
                fontSize: 11,
                color: suppressed ? DIM : "var(--qgi-text-muted)",
                fontFamily: "ui-monospace, monospace",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {row.label}
              {suppressed && <span style={{ marginLeft: 5, fontSize: 8.5 }}>held</span>}
            </span>

            {/* track */}
            <div style={{ position: "relative", height: 16 }}>
              <div
                style={{
                  position: "absolute",
                  top: 7.5,
                  left: 0,
                  right: 0,
                  height: 1,
                  background: BORDER,
                }}
              />
              {!suppressed && (
                <div
                  style={{
                    position: "absolute",
                    top: 6.5,
                    left: `${lo}%`,
                    width: `${hi - lo}%`,
                    height: 3,
                    background: color,
                    borderRadius: 2,
                  }}
                />
              )}
              {/* current (hollow) */}
              <div
                style={{
                  position: "absolute",
                  top: 3,
                  left: `${row.current}%`,
                  transform: "translateX(-50%)",
                  width: 9,
                  height: 9,
                  borderRadius: "50%",
                  border: `1.5px solid ${MUTED}`,
                  background: "var(--qgi-bg)",
                }}
              />
              {/* simulated (filled) */}
              {!suppressed && (
                <div
                  style={{
                    position: "absolute",
                    top: 2,
                    left: `${row.sim}%`,
                    transform: "translateX(-50%)",
                    width: 11,
                    height: 11,
                    borderRadius: "50%",
                    background: color,
                    boxShadow: "0 0 0 2px var(--qgi-surface)",
                  }}
                />
              )}
            </div>

            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                fontFamily: "ui-monospace, monospace",
                color,
                textAlign: "right",
              }}
            >
              {suppressed ? "—" : `${row.delta > 0 ? "+" : ""}${row.delta}`}
            </span>
          </div>
        );
      })}
    </div>
  );
}
