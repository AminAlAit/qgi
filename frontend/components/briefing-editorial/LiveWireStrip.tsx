/**
 * LiveWireStrip — thin live-pulse ticker strip.
 *
 * Only renders when live.status !== "absent". Shows top 6 ACTIVE/SIGNAL
 * cells as horizontally scrollable pills.
 *
 * Server component — no "use client". Pills are static JSX.
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import type { PulseGlancePill } from "@/components/dashboard-v4-1/LivePulseGlance";

interface LiveWireStripProps {
  pills: PulseGlancePill[];
  isLive: boolean;
}

export function LiveWireStrip({ pills, isLive }: LiveWireStripProps) {
  if (!isLive || pills.length === 0) return null;

  return (
    <div
      style={{
        background: "rgba(224,92,92,0.06)",
        borderTop: "1px solid rgba(224,92,92,0.25)",
        borderBottom: "1px solid rgba(224,92,92,0.25)",
        padding: "0 0",
        marginBottom: "24px",
      }}
    >
      <style>{`
        @keyframes qgi-wire-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        .qgi-wire-pip { animation: qgi-wire-pulse 1.8s ease-in-out infinite; }
        .qgi-wire-scroll {
          display: flex;
          align-items: center;
          gap: 0 6px;
          padding: 10px 16px;
          overflow-x: auto;
          scrollbar-width: none;
        }
        .qgi-wire-scroll::-webkit-scrollbar { display: none; }
      `}</style>

      <div className="qgi-wire-scroll">
        {/* LIVE WIRE label */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            fontWeight: 600,
            letterSpacing: "4px",
            color: "#E05C5C",
            flexShrink: 0,
            marginRight: "10px",
          }}
        >
          <span
            className="qgi-wire-pip"
            style={{
              display: "inline-block",
              width: "5px",
              height: "5px",
              borderRadius: "50%",
              background: "var(--qgi-success)",
              flexShrink: 0,
            }}
          />
          LIVE WIRE
        </div>

        {/* Pills */}
        {pills.map((pill) => (
          <div
            key={`${pill.iso3}-${pill.topicLabel}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "5px",
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "20px",
              padding: "4px 10px",
              fontSize: "11px",
              color: "var(--qgi-text-muted)",
              fontFamily: "ui-monospace, monospace",
              whiteSpace: "nowrap",
              flexShrink: 0,
            }}
          >
            <FlagImg
              emoji={flagFor(pill.countryName)}
              name={pill.countryName}
              width={12}
              radius={2}
            />
            <span style={{ color: "var(--qgi-text)", fontWeight: 600 }}>
              {pill.countryName}
            </span>
            <span>·</span>
            <span>{pill.topicLabel}</span>
            <span
              style={{
                color: pill.verdict === "ACTIVE" ? "#E05C5C" : "var(--qgi-amber)",
                fontWeight: 700,
              }}
            >
              {Math.round(pill.pulse)}/100
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
