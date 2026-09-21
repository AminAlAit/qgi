"use client";

/**
 * Sanctions Simulator — interactive scenario bench (vision prototype).
 *
 * Pick a country + a sanctions hardness tier + a horizon; the page perturbs the
 * country's current state by a tier-scaled impact profile and shows, live, how
 * its indicators bend and which event trends it drifts toward. All figures are
 * ILLUSTRATIVE (the impact model is in R&D) and labeled as such; nothing here
 * is a forecast. See lib/sanctions-sim/model.ts.
 */
import { useState } from "react";
import {
  COUNTRIES,
  HORIZONS,
  INDICATORS,
  TIERS,
  type Horizon,
  type TierId,
  compositeEnd,
  compositeSeries,
  country,
  readout,
  tier,
  trendShifts,
} from "@/lib/sanctions-sim/model";
import { CompositeFan, IndicatorBend, TrendDumbbell } from "./charts";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

const PANEL: React.CSSProperties = {
  background: "var(--qgi-surface)",
  border: "1px solid var(--qgi-border)",
  borderRadius: 10,
  padding: "18px 20px",
};
const KICKER: React.CSSProperties = {
  fontSize: 9,
  letterSpacing: "2px",
  textTransform: "uppercase",
  color: "var(--qgi-text-dim)",
  fontFamily: "ui-monospace, monospace",
  fontWeight: 600,
};

export function SanctionsSimulator() {
  const [iso2, setIso2] = useState("ir");
  const [tierId, setTierId] = useState<TierId>("sectoral");
  const [horizon, setHorizon] = useState<Horizon>(5);

  const c = country(iso2);
  const t = tier(tierId);
  const shifts = trendShifts(c, tierId);
  const dumbbellRows = [...shifts].sort(
    (a, b) => Number(!!a.suppressed) - Number(!!b.suppressed) || b.sim - a.sim
  );
  const { topRise, topFall } = readout(c, tierId);
  const baseComposite = compositeSeries(c, tierId, horizon)[0].baseline;
  const endComposite = compositeEnd(c, tierId, horizon);
  const compositeDelta = Math.round(endComposite - baseComposite);

  const readoutText = (() => {
    const head = `${c.name} under ${t.label.toLowerCase()} sanctions, over a ${horizon}-year horizon`;
    if (!topRise && !topFall)
      return `${head}: resemblances hold close to today's baseline.`;
    const parts: string[] = [];
    if (topRise)
      parts.push(
        `resemblance shifts most toward ${topRise.label.toLowerCase()} (+${topRise.delta})`
      );
    if (topFall)
      parts.push(`and eases away from ${topFall.label.toLowerCase()} (${topFall.delta})`);
    return `${head}: ${parts.join(", ")}.`;
  })();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* ── Controls ── */}
      <div
        style={{
          ...PANEL,
          display: "grid",
          gridTemplateColumns: "minmax(220px, 280px) 1fr",
          gap: 20,
          alignItems: "stretch",
        }}
      >
        {/* Country */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span style={KICKER}>Country</span>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <FlagImg emoji={flagFor(c.name)} name={c.name} width={30} radius={3} />
            <select
              value={iso2}
              onChange={(e) => setIso2(e.target.value)}
              aria-label="Select a country"
              style={{
                flex: 1,
                background: "var(--qgi-bg)",
                color: "var(--qgi-text)",
                border: "1px solid var(--qgi-border)",
                borderRadius: 6,
                padding: "9px 10px",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {COUNTRIES.map((co) => (
                <option key={co.iso2} value={co.iso2}>
                  {co.name}
                </option>
              ))}
            </select>
          </div>
          <span style={{ fontSize: 11, color: "var(--qgi-text-dim)", lineHeight: 1.5 }}>
            {c.region} · current composite {Math.round(baseComposite)}/100
          </span>

          <span style={{ ...KICKER, marginTop: 8 }}>Horizon</span>
          <div style={{ display: "flex", gap: 4 }}>
            {HORIZONS.map((h) => {
              const on = h === horizon;
              return (
                <button
                  key={h}
                  type="button"
                  onClick={() => setHorizon(h)}
                  aria-pressed={on}
                  style={{
                    flex: 1,
                    padding: "7px 0",
                    fontSize: 12,
                    fontFamily: "ui-monospace, monospace",
                    fontWeight: 600,
                    borderRadius: 5,
                    cursor: "pointer",
                    border: `1px solid ${on ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
                    background: on ? "var(--qgi-accent)" : "transparent",
                    color: on ? "var(--qgi-bg)" : "var(--qgi-text-muted)",
                  }}
                >
                  {h}Y
                </button>
              );
            })}
          </div>
        </div>

        {/* Hardness tiers */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span style={KICKER}>Sanctions hardness</span>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 10,
              flex: 1,
            }}
          >
            {TIERS.map((tt) => {
              const on = tt.id === tierId;
              return (
                <button
                  key={tt.id}
                  type="button"
                  onClick={() => setTierId(tt.id)}
                  aria-pressed={on}
                  style={{
                    textAlign: "left",
                    cursor: "pointer",
                    borderRadius: 8,
                    borderTop: `1px solid ${on ? tt.color : "var(--qgi-border)"}`,
                    borderRight: `1px solid ${on ? tt.color : "var(--qgi-border)"}`,
                    borderBottom: `1px solid ${on ? tt.color : "var(--qgi-border)"}`,
                    borderLeft: `3px solid ${tt.color}`,
                    background: on ? `${tt.color}18` : "var(--qgi-bg)",
                    padding: "10px 12px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 5,
                    transition: "background 120ms, border-color 120ms",
                  }}
                >
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: 700,
                      color: on ? tt.color : "var(--qgi-text)",
                    }}
                  >
                    {tt.label}
                  </span>
                  <span
                    style={{
                      fontSize: 10.5,
                      color: "var(--qgi-text-muted)",
                      lineHeight: 1.45,
                    }}
                  >
                    {tt.blurb}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Scenario readout ── */}
      <div
        style={{
          background: "var(--qgi-surface)",
          borderRadius: 10,
          padding: "18px 20px",
          borderTop: "1px solid var(--qgi-border)",
          borderRight: "1px solid var(--qgi-border)",
          borderBottom: "1px solid var(--qgi-border)",
          borderLeft: `3px solid ${t.color}`,
        }}
      >
        <span style={KICKER}>Scenario</span>
        <p
          style={{
            fontSize: 16,
            lineHeight: 1.6,
            color: "var(--qgi-text)",
            margin: "8px 0 0",
            maxWidth: 880,
          }}
        >
          {readoutText}
        </p>
      </div>

      {/* ── Hero: composite fan + stats ── */}
      <div style={PANEL}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: 12,
            marginBottom: 8,
          }}
        >
          <div>
            <span style={KICKER}>Composite trajectory · modeled projection</span>
            <h2
              style={{
                fontSize: 15,
                fontWeight: 700,
                margin: "4px 0 0",
                color: "var(--qgi-text)",
              }}
            >
              How {c.name}&apos;s overall position bends after onset
            </h2>
          </div>
          <div style={{ display: "flex", gap: 18 }}>
            <Stat
              label="Composite, end"
              value={`${Math.round(endComposite)}`}
              sub={`${compositeDelta >= 0 ? "+" : ""}${compositeDelta} vs today`}
              color={t.color}
            />
            <Stat
              label="Indicators moved"
              value={`${INDICATORS.length}`}
              sub="featured channels"
              color="var(--qgi-text)"
            />
            <Stat
              label="Strongest drift"
              value={topRise ? `+${topRise.delta}` : "0"}
              sub={topRise ? topRise.label.split(" ")[0].toLowerCase() : "none"}
              color="#E64545"
            />
          </div>
        </div>
        <CompositeFan iso2={iso2} tierId={tierId} horizon={horizon} />
        {/* severity ladder */}
        <div
          style={{
            display: "flex",
            gap: 16,
            flexWrap: "wrap",
            marginTop: 6,
            paddingTop: 10,
            borderTop: "1px solid var(--qgi-border)",
          }}
        >
          <span
            style={{
              fontSize: 10,
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            SEVERITY LADDER (composite at +{horizon}y):
          </span>
          {TIERS.map((tt) => (
            <span
              key={tt.id}
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                color: tt.color,
                fontWeight: tt.id === tierId ? 700 : 400,
                opacity: tt.id === tierId ? 1 : 0.7,
              }}
            >
              {tt.label} {Math.round(compositeEnd(c, tt.id, horizon))}
            </span>
          ))}
          <span
            style={{ fontSize: 10.5, color: "var(--qgi-text-dim)", marginLeft: "auto" }}
          >
            {t.sampleNote}
          </span>
        </div>
      </div>

      {/* ── Indicators + trends ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.25fr) minmax(0, 1fr)",
          gap: 20,
          alignItems: "start",
        }}
      >
        {/* Indicator small-multiples */}
        <div style={PANEL}>
          <span style={KICKER}>How each indicator bends · modeled projection</span>
          <h2
            style={{
              fontSize: 15,
              fontWeight: 700,
              margin: "4px 0 4px",
              color: "var(--qgi-text)",
            }}
          >
            Eight sanctions-channel indicators
          </h2>
          <p
            style={{
              fontSize: 11.5,
              color: "var(--qgi-text-dim)",
              margin: "0 0 14px",
              lineHeight: 1.55,
              maxWidth: 560,
            }}
          >
            Muted line is today&apos;s baseline held flat. Colored line applies the{" "}
            {t.label.toLowerCase()} impact profile from year 0, with a band for historical
            spread. Each level is 0 to 100 (higher is healthier).
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
              gap: 12,
            }}
          >
            {INDICATORS.map((ind) => (
              <IndicatorBend
                key={ind.code}
                iso2={iso2}
                code={ind.code}
                tierId={tierId}
                horizon={horizon}
              />
            ))}
          </div>
        </div>

        {/* Trend dumbbell + analogues */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={PANEL}>
            <span style={KICKER}>Trend resemblance shift · now → simulated</span>
            <h2
              style={{
                fontSize: 15,
                fontWeight: 700,
                margin: "4px 0 4px",
                color: "var(--qgi-text)",
              }}
            >
              Which event trends it drifts toward
            </h2>
            <p
              style={{
                fontSize: 11.5,
                color: "var(--qgi-text-dim)",
                margin: "0 0 12px",
                lineHeight: 1.55,
              }}
            >
              Hollow dot is today, filled dot is the simulated level. Red is rising
              resemblance, green is easing.
            </p>
            <TrendDumbbell shifts={dumbbellRows} />
          </div>

          <div style={PANEL}>
            <span style={KICKER}>Closest historical precedents</span>
            <div
              style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}
            >
              {c.analogues.map((a) => (
                <div
                  key={`${a.iso2}-${a.period}`}
                  style={{
                    display: "flex",
                    gap: 10,
                    alignItems: "flex-start",
                    padding: "10px 12px",
                    background: "var(--qgi-bg)",
                    border: "1px solid var(--qgi-border)",
                    borderRadius: 8,
                  }}
                >
                  <FlagImg
                    emoji={flagFor(a.country)}
                    name={a.country}
                    width={22}
                    radius={2}
                  />
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 12.5,
                        fontWeight: 600,
                        color: "var(--qgi-text)",
                      }}
                    >
                      {a.country}, {a.period}
                    </div>
                    <div
                      style={{
                        fontSize: 11.5,
                        color: "var(--qgi-text-muted)",
                        lineHeight: 1.5,
                        marginTop: 2,
                      }}
                    >
                      {a.outcome}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── How to read ── */}
      <div style={{ ...PANEL, background: "var(--qgi-bg)" }}>
        <span style={KICKER}>How to read this</span>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: "10px 24px",
            marginTop: 10,
          }}
        >
          {[
            [
              "It is a scenario, not a forecast.",
              "The simulator identifies which historical sanctioned-country trajectories the current path most resembles after applying a tier impact profile. It does not project events, dates, or probabilities.",
            ],
            [
              "Figures are illustrative.",
              "Indicator paths and trend resemblances apply historical sanction-period averages to the current trajectory, not a calibrated causal model. Bands show spread, not confidence intervals.",
            ],
            [
              "Harder tiers are less certain.",
              "Comprehensive cases are historically rare, so their bands are wider and their direction is more trustworthy than their magnitude.",
            ],
            [
              "One trend is held fixed.",
              "Interstate conflict is often the reason a sanction was imposed, so its resemblance is held at baseline rather than shown as a sanction effect.",
            ],
          ].map(([h, b]) => (
            <div key={h}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  color: "var(--qgi-text)",
                  marginBottom: 3,
                }}
              >
                {h}
              </div>
              <div
                style={{
                  fontSize: 11.5,
                  color: "var(--qgi-text-muted)",
                  lineHeight: 1.55,
                }}
              >
                {b}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub: string;
  color: string;
}) {
  return (
    <div
      style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}
    >
      <span
        style={{
          fontSize: 24,
          fontWeight: 700,
          fontFamily: "ui-monospace, monospace",
          color,
          lineHeight: 1,
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontSize: 8.5,
          letterSpacing: "1px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
        }}
      >
        {label}
      </span>
      <span style={{ fontSize: 9.5, color: "var(--qgi-text-muted)" }}>{sub}</span>
    </div>
  );
}
