/**
 * ScopeFooter — bottom monospace scope strip.
 * Server component.
 */
import type { HeroCounts41 } from "@/lib/te-mock/dashboard-v4-1-data";

interface Props {
  counts: HeroCounts41;
  familyCount: number;
}

export function ScopeFooter({ counts, familyCount }: Props) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "14px 18px",
        borderTop: "1px solid var(--qgi-border)",
        background: "var(--qgi-surface)",
        borderRadius: "0 0 8px 8px",
        fontFamily: "ui-monospace, monospace",
        fontSize: "11px",
        color: "var(--qgi-text-dim)",
        letterSpacing: "0.3px",
      }}
    >
      180+ countries
      <Dot />
      {counts.recipes_total} trends
      <Dot />
      {familyCount} risk families
      <Dot />
      {counts.indicators_tracked} signals tracked
      <Dot />
      quarterly refresh
    </div>
  );
}

function Dot() {
  return (
    <span aria-hidden style={{ color: "var(--qgi-border)", margin: "0 10px" }}>
      ·
    </span>
  );
}
