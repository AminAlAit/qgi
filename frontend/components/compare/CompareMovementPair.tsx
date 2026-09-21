/**
 * CompareMovementPair — two stacked panels, one per country.
 *
 * Each panel: country's top 3 fastest-moving indicators by |z_score_change|,
 * 12-quarter MiniSparkline, direction chip ("rising 18pp" / "falling 24pp").
 * "Shared mover" badge if both countries share an indicator in their top 3.
 *
 * Sparklines: NEUTRAL_SLATE.
 * Direction chips: green/amber muted, per direction.
 *
 * V4.1 bar: retrospective only, no forward projection.
 */
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { MiniSparkline } from "@/components/countries-v4-1/MiniSparkline";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import { topMovers, sharedMovers } from "@/lib/te-mock/compare-data";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";

const DIRECTION_COLOR: Record<string, string> = {
  rising: "#3FBF8F",
  falling: "#E64545",
  volatile: "#E68F29",
  flat: "#7A8FA0",
};

function DirectionChip({ direction, change }: { direction: string; change: number }) {
  const color = DIRECTION_COLOR[direction] ?? "#7A8FA0";
  const sign = change > 0 ? "+" : "";
  return (
    <span
      style={{
        fontSize: "9.5px",
        fontFamily: "ui-monospace, monospace",
        padding: "2px 6px",
        borderRadius: "3px",
        border: `1px solid ${color}55`,
        color,
        background: `${color}14`,
        whiteSpace: "nowrap",
        letterSpacing: "0.3px",
        opacity: 0.88,
      }}
    >
      {direction} {sign}
      {change.toFixed(0)}pp
    </span>
  );
}

function MovementCountryPanel({
  country,
  sharedCodes,
}: {
  country: CountryV4;
  sharedCodes: Set<string>;
}) {
  const movers = topMovers(country, 3);

  return (
    <div
      style={{
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "5px",
        padding: "12px 14px",
      }}
    >
      {/* Country header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginBottom: "12px",
        }}
      >
        <FlagImg emoji={country.flag_emoji} name={country.name} width={18} />
        <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--qgi-text)" }}>
          {country.name}
        </span>
        <span
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {country.iso} · top 3 movers
        </span>
      </div>

      {movers.map((d) => {
        const isShared = sharedCodes.has(d.indicator_code);
        return (
          <div
            key={d.indicator_code}
            style={{
              marginBottom: "12px",
              display: "flex",
              alignItems: "center",
              gap: "10px",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  marginBottom: "5px",
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    fontSize: "12px",
                    color: "var(--qgi-text)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={d.indicator_name}
                >
                  {d.indicator_name}
                </span>
                <DirectionChip direction={d.direction} change={d.z_score_change} />
                {isShared && (
                  <span
                    style={{
                      fontSize: "9px",
                      fontFamily: "ui-monospace, monospace",
                      padding: "1px 5px",
                      borderRadius: "3px",
                      color: "#E68F29",
                      border: "1px solid #E68F2955",
                      background: "#E68F2914",
                      letterSpacing: "0.3px",
                    }}
                  >
                    Shared
                  </span>
                )}
              </div>
              <MiniSparkline
                values={d.trajectory}
                color={NEUTRAL_SLATE}
                width={180}
                height={28}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function CompareMovementPair({
  countryA,
  countryB,
}: {
  countryA: CountryV4;
  countryB: CountryV4;
}) {
  const shared = sharedMovers(countryA, countryB);
  const sharedCodes = new Set(shared.map((s) => s.indicator_code));

  return (
    <PanelShell
      title="What is moving"
      accent={NEUTRAL_SLATE}
      dataTour="compare-movement"
      fullWidth
      caption="Top 3 fastest-moving indicators for each country over the last 12 quarters. A shared-mover badge marks indicators in both countries' top 3."
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "14px",
        }}
      >
        <MovementCountryPanel country={countryA} sharedCodes={sharedCodes} />
        <MovementCountryPanel country={countryB} sharedCodes={sharedCodes} />
      </div>
    </PanelShell>
  );
}
