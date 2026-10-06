"use client";
/**
 * InteractiveLandscapeWrapper — dynamic import with ssr:false so ECharts
 * never runs on the server. Must be a Client Component in Next.js 16.
 */
import dynamic from "next/dynamic";
import type { ScatterPoint } from "@/components/briefing-signal/QuadrantSection";

// Lazy-load the actual chart; ssr:false avoids ECharts SSR hydration issues.
const InteractiveLandscape = dynamic(
  () =>
    import("./InteractiveLandscape").then((m) => ({
      default: m.InteractiveLandscape,
    })),
  { ssr: false }
);

interface Props {
  points: ScatterPoint[];
  activeCount: number;
  inPlayCount: number;
  silentAlarmCount: number;
}

export function InteractiveLandscapeWrapper(props: Props) {
  return <InteractiveLandscape {...props} />;
}
