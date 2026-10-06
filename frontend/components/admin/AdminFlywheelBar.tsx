"use client";

/**
 * AdminFlywheelBar — client component for the Flywheel Score header.
 * Renders the big score + a stacked segmented bar of the 5 components.
 * Receives plain serializable props from the server page.
 */

interface Component {
  key: string;
  label: string;
  value: number;
  weight: number;
  contribution: number;
}

const SEG_COLORS: Record<string, string> = {
  trained: "#38bdf8",
  curation: "#34d399",
  auc: "#f59e0b",
  coverage: "#a78bfa",
  posts: "#fb923c",
};

export function AdminFlywheelBar({
  score,
  components,
}: {
  score: number;
  components: Component[];
}) {
  const scoreColor =
    score >= 70
      ? "var(--qgi-success)"
      : score >= 45
        ? "var(--qgi-warning)"
        : "var(--qgi-danger)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Score + label row */}
      <div style={{ display: "flex", alignItems: "baseline", gap: "16px" }}>
        <span
          className="font-data"
          style={{ fontSize: "52px", fontWeight: 700, color: scoreColor, lineHeight: 1 }}
        >
          {score.toFixed(1)}
        </span>
        <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              letterSpacing: "0.8px",
              textTransform: "uppercase",
              color: "var(--qgi-text-muted)",
            }}
          >
            / 100 · QGI Flywheel Score
          </span>
          <span style={{ fontSize: "11px", color: "var(--qgi-text-dim)" }}>
            North-star composite — how complete, validated &amp; live is the intelligence
            engine?
          </span>
        </div>
      </div>

      {/* Stacked bar */}
      <div>
        <div
          style={{
            display: "flex",
            height: "18px",
            borderRadius: "4px",
            overflow: "hidden",
            background: "var(--qgi-surface-2)",
            gap: "1px",
          }}
        >
          {components.map((c) => (
            <div
              key={c.key}
              title={`${c.label}: ${(c.value * 100).toFixed(0)}% → +${c.contribution.toFixed(1)} pts (weight ${(c.weight * 100).toFixed(0)}%)`}
              style={{
                flex: c.contribution,
                background: SEG_COLORS[c.key] ?? "#38bdf8",
                opacity: 0.88,
                minWidth: c.contribution > 0 ? "2px" : "0",
                transition: "flex 0.4s ease",
              }}
            />
          ))}
          {/* grey remainder */}
          <div
            style={{ flex: Math.max(0, 100 - score), background: "var(--qgi-surface-2)" }}
          />
        </div>

        {/* Legend */}
        <div
          style={{
            display: "flex",
            gap: "20px",
            marginTop: "10px",
            flexWrap: "wrap",
          }}
        >
          {components.map((c) => (
            <div
              key={c.key}
              style={{ display: "flex", alignItems: "center", gap: "6px" }}
            >
              <div
                style={{
                  width: "10px",
                  height: "10px",
                  borderRadius: "2px",
                  background: SEG_COLORS[c.key] ?? "#38bdf8",
                  flexShrink: 0,
                }}
              />
              <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
                <span style={{ fontSize: "11px", color: "var(--qgi-text-muted)" }}>
                  {c.label}
                </span>
                <span
                  className="font-data"
                  style={{ fontSize: "13px", fontWeight: 600, color: "var(--qgi-text)" }}
                >
                  {(c.value * 100).toFixed(0)}%
                  <span
                    style={{
                      fontSize: "10px",
                      color: "var(--qgi-text-dim)",
                      fontWeight: 400,
                    }}
                  >
                    {" "}
                    → +{c.contribution.toFixed(1)}
                  </span>
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
