"use client";

import { useRouter } from "next/navigation";
import type { PatternRow } from "@/lib/types";

interface Props {
  patterns: PatternRow[];
}

export function Leaderboard({ patterns }: Props) {
  const router = useRouter();

  function navigate(p: PatternRow) {
    // country_a_id / country_b_id are typed `string | number` post-T2
    // widening — URLSearchParams only accepts strings, so coerce.
    // Falls back to country NAME if the id is missing (same behavior as
    // before, but the API will 400 on names — callers should prefer to
    // guard-skip rows without ids like BaseClient + PatternsClient do).
    const qs = new URLSearchParams({
      country_a: String(p.country_a_id ?? p.country_a),
      country_b: String(p.country_b_id ?? p.country_b),
      length: String(p.pattern_length),
      start_a: String(p.start_year_a),
      start_b: String(p.start_year_b),
    });
    router.push(`/patterns?${qs.toString()}`);
  }

  return (
    <div className="flex flex-col h-full">
      <div
        className="text-[9px] tracking-[0.2em] uppercase px-4 py-2 border-b flex gap-0"
        style={{ color: "var(--qgi-text-dim)", borderColor: "var(--qgi-border)" }}
      >
        <span className="flex-1">PREDICTOR</span>
        <span className="flex-1">FOLLOWING</span>
        <span
          className="w-16 text-right"
          title="Pattern strength: composite of correlation, persistence, and breadth"
        >
          SCORE
        </span>
        <span className="w-10 text-right" title="Years of pattern history">
          YRS
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {patterns.map((p, i) => (
          <button
            key={i}
            onClick={() => navigate(p)}
            className="w-full text-left flex items-center gap-0 px-4 py-2 border-b text-xs transition-colors hover:bg-[var(--qgi-surface-2)]"
            style={{ borderColor: "var(--qgi-border)" }}
          >
            <span
              className="flex-1 font-data truncate"
              style={{ color: "var(--qgi-country-a)" }}
            >
              {p.country_a}
            </span>
            <span
              className="flex-1 font-data truncate"
              style={{ color: "var(--qgi-country-b)" }}
            >
              {p.country_b}
            </span>
            <span
              className="w-16 text-right font-data font-semibold"
              style={{ color: "var(--qgi-amber)" }}
            >
              {p.pattern_power_score.toFixed(3)}
            </span>
            <span
              className="w-10 text-right font-data"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              {p.pattern_length}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
