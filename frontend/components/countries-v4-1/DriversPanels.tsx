/**
 * DriversPanels (P2 + P3) — the attribution/movement pair.
 *
 * These answer two DIFFERENT questions and must stay visibly separate
 * (Kwame, non-negotiable): P2 "why these scores" is how the model weighs
 * signals (model-internal); P3 "what's moving" is what is observably
 * shifting in the world. They share the top-lit family accent so the reader
 * sees they describe the same recipe, but carry different eyebrows and a
 * bridge tooltip. Conflating them would imply the model's weights ARE
 * real-world causes, which we forbid.
 */
import { PanelShell } from "./PanelShell";
import { MiniSparkline } from "./MiniSparkline";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import type {
  CountryDriverAttribution,
  CountryDriverMovement,
} from "@/lib/te-mock/countries-v4-data";

const BRIDGE =
  "Weight and movement are different. An indicator can weigh heavily while sitting still, " +
  "or move sharply while weighing little.";

/* ── P2 — Why these scores (attribution) ─────────────────────────────── */
export function WhyScoresPanel({
  accent,
  countryName,
  attribution,
}: {
  accent: string;
  countryName: string;
  attribution: CountryDriverAttribution[];
}) {
  const rows = [...attribution].sort((a, b) => b.signal_share_pct - a.signal_share_pct);

  return (
    <PanelShell
      title="Why these scores"
      accent={accent}
      tooltip={BRIDGE}
      caption={`Which of ${countryName}'s recent signals weigh most in its scoring. This is how the model reads the data, not a cause.`}
    >
      {rows.length === 0 ? (
        <p
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
            margin: 0,
          }}
        >
          Driver attribution available once the country is scored on at least one trend.
        </p>
      ) : (
        <>
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
            {rows.map((r, idx) => {
              // Round-2: direction_sign +1/-1 from shap_direction_signs on the card.
              const sign = r.direction_sign;
              const dirArrow = sign === 1 ? "↑" : sign === -1 ? "↓" : null;
              const dirColor =
                sign === 1
                  ? "#E68F29" // risk-increasing → amber warning
                  : sign === -1
                    ? "#3FBF8F" // risk-decreasing → green calming
                    : undefined;
              const isTop = idx === 0;
              return (
                // key uses indicator_name to keep raw provider codes out of the
                // SSR'd HTML stream — rule §3 (never the code; always the name).
                <li key={r.indicator_name}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "baseline",
                      gap: "10px",
                      marginBottom: "3px",
                    }}
                  >
                    <span
                      style={{
                        fontSize: isTop ? "13.5px" : "12.5px",
                        fontWeight: isTop ? 700 : undefined,
                        color: "var(--qgi-text)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={`${r.indicator_name} (${r.provider})${sign != null ? (sign === 1 ? " · risk-increasing" : " · risk-decreasing") : ""}`}
                    >
                      {r.indicator_name}
                      <span
                        style={{
                          fontSize: "9.5px",
                          color: "var(--qgi-text-dim)",
                          fontFamily: "ui-monospace, monospace",
                          marginLeft: "8px",
                          letterSpacing: "0.3px",
                        }}
                      >
                        {r.provider}
                      </span>
                    </span>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "5px",
                        fontFamily: "ui-monospace, monospace",
                        fontSize: "12px",
                        fontWeight: 700,
                        color: accent,
                        flexShrink: 0,
                      }}
                    >
                      {dirArrow && (
                        <span
                          style={{
                            fontSize: "11px",
                            color: dirColor,
                            fontWeight: 700,
                          }}
                          title={
                            sign === 1
                              ? "Risk-increasing direction"
                              : "Risk-decreasing direction"
                          }
                          aria-label={sign === 1 ? "risk-increasing" : "risk-decreasing"}
                        >
                          {dirArrow}
                        </span>
                      )}
                      {r.signal_share_pct.toFixed(0)}%
                    </span>
                  </div>
                  <div
                    style={{
                      height: "8px",
                      borderRadius: "2px",
                      background: "var(--qgi-bg)",
                      border: "1px solid var(--qgi-border)",
                      overflow: "hidden",
                    }}
                    aria-hidden
                  >
                    <div
                      style={{
                        width: `${r.signal_share_pct}%`,
                        height: "100%",
                        background: isTop ? accent : NEUTRAL_SLATE,
                        opacity: isTop ? 0.7 : 0.85,
                      }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
          <p
            style={{
              margin: "10px 0 0",
              fontSize: "10.5px",
              color: "var(--qgi-text-dim)",
              fontStyle: "italic",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.2px",
            }}
          >
            Weight is not movement. A signal can rank highly while barely shifting.
          </p>
        </>
      )}
    </PanelShell>
  );
}

/* ── P3 — What's moving (observed movement) ──────────────────────────── */
function DirectionGlyph({
  direction,
}: {
  direction: CountryDriverMovement["direction"];
}) {
  const g = direction === "rising" ? "▲" : direction === "falling" ? "▼" : "▬";
  return (
    <span
      style={{
        fontSize: "9px",
        color: "var(--qgi-text-dim)",
        fontFamily: "ui-monospace, monospace",
      }}
      aria-label={direction}
    >
      {g}
    </span>
  );
}

export function WhatsMovingPanel({
  accent,
  countryName,
  movement,
  compositeTrajectory,
}: {
  accent: string;
  countryName: string;
  movement: CountryDriverMovement[];
  /** Round-2: 12-pt composite z-score trajectory from bake (0..100 display scale). */
  compositeTrajectory?: number[];
}) {
  return (
    <PanelShell
      title="What's moving"
      accent={accent}
      tooltip={BRIDGE}
      caption={`How each indicator behind ${countryName}'s scores has actually shifted over the last 3 years. Recent movement only, not a projection.`}
    >
      {movement.length === 0 ? (
        <p
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
            margin: 0,
          }}
        >
          Indicator trajectories available with the next bake.
        </p>
      ) : (
        <>
          {/* Round-2: composite sparkline above the indicator list. */}
          {compositeTrajectory && compositeTrajectory.length > 1 && (
            <div style={{ marginBottom: "10px" }}>
              <div
                style={{
                  fontSize: "9px",
                  letterSpacing: "1px",
                  color: "var(--qgi-text-dim)",
                  fontFamily: "ui-monospace, monospace",
                  marginBottom: "4px",
                }}
              >
                COMPOSITE INDICATOR MOVEMENT (12Q)
              </div>
              <MiniSparkline
                values={compositeTrajectory}
                color={accent}
                width={220}
                height={32}
              />
            </div>
          )}
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "11px",
            }}
          >
            {movement.map((m) => {
              const z = m.z_score_change;
              // Round-2: raw delta line — "42.1% → 68.3% · +0.8z"
              const hasRaw =
                m.latest_raw_value != null && m.prior_raw_value != null && m.unit != null;
              const rawDeltaLine = hasRaw
                ? `${Number(m.prior_raw_value).toFixed(1)}${m.unit} → ${Number(m.latest_raw_value).toFixed(1)}${m.unit}`
                : null;
              return (
                <li
                  key={m.indicator_name}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(0, 1fr) auto auto",
                    alignItems: "center",
                    gap: "10px",
                  }}
                >
                  <span
                    style={{
                      fontSize: "12.5px",
                      color: "var(--qgi-text)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={`${m.indicator_name} (${m.provider})${rawDeltaLine ? ` · ${rawDeltaLine}` : ""}`}
                  >
                    {m.indicator_name}
                    <span
                      style={{
                        fontSize: "9.5px",
                        color: "var(--qgi-text-dim)",
                        fontFamily: "ui-monospace, monospace",
                        marginLeft: "8px",
                        letterSpacing: "0.3px",
                      }}
                    >
                      {m.provider}
                    </span>
                    {rawDeltaLine && (
                      <span
                        style={{
                          display: "block",
                          fontSize: "9.5px",
                          color: "var(--qgi-text-dim)",
                          fontFamily: "ui-monospace, monospace",
                          letterSpacing: "0.3px",
                          marginTop: "1px",
                        }}
                      >
                        {rawDeltaLine}
                      </span>
                    )}
                  </span>
                  <MiniSparkline
                    values={m.trajectory}
                    color={accent}
                    width={104}
                    height={26}
                  />
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "5px",
                      fontFamily: "ui-monospace, monospace",
                      fontSize: "11.5px",
                      color: "var(--qgi-text-muted)",
                      minWidth: "52px",
                      justifyContent: "flex-end",
                    }}
                  >
                    <DirectionGlyph direction={m.direction} />
                    {`${z > 0 ? "+" : ""}${Math.abs(z) < 1 ? z.toFixed(1) : z.toFixed(0)}`}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </PanelShell>
  );
}
