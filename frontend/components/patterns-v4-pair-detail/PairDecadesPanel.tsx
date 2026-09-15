/**
 * PairDecadesPanel -- §5 Decade-by-decade small multiples.
 *
 * 2-4 small-multiple panels (one per decade of the window).
 * Each: both countries' indicator-composite trajectory within that decade,
 * per-country family-colored lines.
 * Per-decade label: decade ("1990s") + one-word shape archetype.
 *
 * No phase-shift annotation. No arrow between lines. No "leads" copy.
 * Y-axis: not labeled (small-multiple context makes absolute values misleading).
 */
import type { DecadeBucket } from "@/lib/te-mock/patterns-v4-pair-detail-mock";
import { familyColor } from "@/lib/te-mock/l1-families";

const ARCHETYPE_LABEL: Record<DecadeBucket["archetype"], string> = {
  ramp: "Ramp",
  oscillation: "Oscillation",
  step: "Step",
  recovery: "Recovery",
  collapse: "Collapse",
};

interface PairDecadesPanelProps {
  decadeBuckets: DecadeBucket[];
  dominantFamilyAId: string;
  dominantFamilyBId: string;
}

const SM_W = 160;
const SM_H = 60;

function miniPath(
  series: number[],
  width: number,
  height: number,
  minY: number,
  maxY: number
): string {
  if (series.length < 2) return "";
  const range = maxY - minY || 1;
  return series
    .map((v, i) => {
      const x = (i / (series.length - 1)) * width;
      const y = height - ((v - minY) / range) * height;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

export function PairDecadesPanel({
  decadeBuckets,
  dominantFamilyAId,
  dominantFamilyBId,
}: PairDecadesPanelProps) {
  const colorA = familyColor(dominantFamilyAId);
  const colorB = familyColor(dominantFamilyBId);
  const sameFamily = dominantFamilyAId === dominantFamilyBId;

  // Only render buckets that have data (slice to max 6 for display)
  const visibleBuckets = decadeBuckets
    .filter((b) => b.seriesA.length >= 3 && b.seriesB.length >= 3)
    .slice(0, 6);

  return (
    <div
      data-tour="pair-decades"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginBottom: "20px",
      }}
    >
      <div
        style={{
          fontSize: "9px",
          letterSpacing: "1.6px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "4px",
          fontWeight: 600,
        }}
      >
        DECADE BY DECADE
      </div>
      <h2
        style={{
          fontSize: "15px",
          fontWeight: 700,
          margin: "0 0 16px",
          color: "var(--qgi-text)",
        }}
      >
        How the resemblance held across the window
      </h2>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        {visibleBuckets.map((bucket) => (
          <DecadeCard
            key={bucket.decade}
            bucket={bucket}
            colorA={colorA}
            colorB={colorB}
            sameFamily={sameFamily}
          />
        ))}
      </div>
    </div>
  );
}

function DecadeCard({
  bucket,
  colorA,
  colorB,
  sameFamily,
}: {
  bucket: DecadeBucket;
  colorA: string;
  colorB: string;
  sameFamily: boolean;
}) {
  const all = [...bucket.seriesA, ...bucket.seriesB];
  const minY = Math.min(...all);
  const maxY = Math.max(...all);
  const pathA = miniPath(bucket.seriesA, SM_W, SM_H, minY, maxY);
  const pathB = miniPath(bucket.seriesB, SM_W, SM_H, minY, maxY);

  return (
    <div
      style={{
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        padding: "12px",
        minWidth: "160px",
        flex: "0 0 auto",
      }}
    >
      {/* Decade + archetype */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          marginBottom: "8px",
        }}
      >
        <span
          style={{
            fontSize: "12px",
            fontWeight: 700,
            color: "var(--qgi-text)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {bucket.decade}
        </span>
        <span
          style={{
            fontSize: "9px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text-dim)",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "3px",
            padding: "1px 5px",
            letterSpacing: "0.5px",
          }}
        >
          {ARCHETYPE_LABEL[bucket.archetype]}
        </span>
      </div>

      {/* Mini chart */}
      <svg
        viewBox={`0 0 ${SM_W} ${SM_H}`}
        style={{ width: "100%", display: "block" }}
        aria-label={`${bucket.decade} shape: ${bucket.archetype}`}
        role="img"
      >
        {/* Series B (back) */}
        <path
          d={pathB}
          fill="none"
          stroke={colorB}
          strokeWidth={1.6}
          strokeOpacity={sameFamily ? 0.55 : 0.85}
          strokeDasharray={sameFamily ? "5 3" : undefined}
        />
        {/* Series A (front) */}
        <path
          d={pathA}
          fill="none"
          stroke={colorA}
          strokeWidth={1.6}
          strokeOpacity={0.9}
        />
      </svg>
    </div>
  );
}
