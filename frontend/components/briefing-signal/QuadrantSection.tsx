"use client";
/**
 * QuadrantSection — client wrapper: passes scatter data + insight counts as props.
 * Renders QuadrantChart (lazy, ssr:false) + InsightCallouts. Must be a Client
 * Component because the ssr:false dynamic import is disallowed in Server
 * Components in Next.js 16. Receives serializable props from the server page.
 */
import dynamic from "next/dynamic";
import type { HfCell, HfVerdict } from "@/lib/hf/topics-data";
import { InsightCallouts } from "./InsightCallouts";

// Dynamic import: ssr:false avoids ECharts SSR issues.
const QuadrantChart = dynamic(
  () => import("./QuadrantChart").then((m) => m.QuadrantChart),
  { ssr: false }
);

export interface ScatterPoint {
  struct: number;
  pulse: number;
  countryName: string;
  topicLabel: string;
  verdict: HfVerdict;
}

interface Props {
  points: ScatterPoint[];
  activeCount: number;
  silentAlarmCount: number;
  inPlayCount: number;
}

export function QuadrantSection({
  points,
  activeCount,
  silentAlarmCount,
  inPlayCount,
}: Props) {
  return (
    <section>
      <style>{`
        .qgi-quadrant-grid {
          display: grid;
          grid-template-columns: 60% 40%;
          gap: 16px;
          align-items: stretch;
        }
        @media (max-width: 767px) {
          .qgi-quadrant-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>

      {/* Section header */}
      <div style={{ marginBottom: "14px" }}>
        <h2
          style={{
            fontSize: "20px",
            fontWeight: 600,
            margin: "0 0 4px",
            letterSpacing: "-0.2px",
          }}
        >
          Signal landscape
        </h2>
        <p
          style={{
            fontSize: "13px",
            color: "var(--qgi-text-muted)",
            margin: 0,
            lineHeight: 1.5,
          }}
        >
          Every country × topic cell plotted by structure vs. news pulse. Quadrant
          position reveals what the board knows that the news cycle hasn&apos;t confirmed
          yet.
        </p>
      </div>

      <div className="qgi-quadrant-grid">
        {/* Left: scatter chart */}
        <div
          style={{
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "10px",
            padding: "16px",
            minHeight: "370px",
          }}
        >
          <QuadrantChart points={points} />
        </div>

        {/* Right: insight callouts */}
        <InsightCallouts
          activeCount={activeCount}
          silentAlarmCount={silentAlarmCount}
          inPlayCount={inPlayCount}
        />
      </div>
    </section>
  );
}
