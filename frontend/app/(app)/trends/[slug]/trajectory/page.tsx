/**
 * /trends/[slug]/trajectory — Per-recipe trajectory deep-dive.
 *
 * Round-2 (2026-05-30): shape_points (12-float z-score series) is now emitted
 * by the bake. This page renders the canonical movement shape as a full-width
 * sparkline with quarter labels. Retrospective only (Kwame): the line ends at
 * the latest reading; no forward extension.
 *
 * Methodology note: shape_points is the normalised z-score composite across a
 * recipe's key indicators over the 12 quarters preceding a canonical event.
 * It is NOT a forecast — it describes what the data historically rhymes around.
 * The caption says so explicitly and the page is noindex-free now that it has
 * real content.
 */
import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { loadCardV3, FLEET_RUN_1_RECIPE_IDS } from "@/lib/te-data-contract/load";
import { cleanEmDashes } from "@/lib/clean-text";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export function generateStaticParams() {
  return FLEET_RUN_1_RECIPE_IDS.map((id) => ({ slug: id }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  return {
    title: `Trajectory · ${slug.replace(/_/g, " ")} · QG Intelligence`,
    description:
      "The canonical movement shape of a trend: the recurring indicator-composite arc its verified-positive history rhymes around.",
  };
}

/** Map a z-score to a 0–100 display scale (clamp ±3 range). */
function zToDisplay(z: number): number {
  return Math.max(0, Math.min(100, ((z + 3) / 6) * 100));
}

export default async function TrajectoryDeepDivePage({ params }: PageProps) {
  const { slug } = await params;

  // Load card — may throw if slug is not a fleet-run-1 recipe.
  let shapePoints: number[] | null = null;
  let shapeNote: string | null = null;
  try {
    const card = loadCardV3(slug);
    if (card.shape_points && card.shape_points.length > 1) {
      shapePoints = card.shape_points.map(zToDisplay);
    }
    // Use description if available for context.
    if ("description" in card && typeof card.description === "string") {
      shapeNote = cleanEmDashes(card.description);
    }
  } catch {
    // Recipe not in fleet-run-1 or card missing — show empty state.
  }

  const quarterLabels = Array.from({ length: 12 }, (_, i) => `Q${i + 1}`);

  return (
    <div style={{ background: "var(--qgi-bg)", color: "var(--qgi-text)" }}>
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "24px" }}>
        {/* Breadcrumb */}
        <nav
          aria-label="Breadcrumb"
          style={{
            fontSize: "11px",
            letterSpacing: "0.3px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            marginBottom: "16px",
          }}
        >
          <Link
            href={"/trends" as Route}
            style={{ color: "var(--qgi-text-muted)", textDecoration: "none" }}
          >
            ← Trends
          </Link>
          <span style={{ margin: "0 8px", opacity: 0.5 }}>/</span>
          <Link
            href={`/trends/${slug}` as Route}
            style={{ color: "var(--qgi-text-muted)", textDecoration: "none" }}
          >
            {slug.replace(/_/g, " ")}
          </Link>
          <span style={{ margin: "0 8px", opacity: 0.5 }}>/</span>
          <span style={{ color: "var(--qgi-text)" }}>Trajectory</span>
        </nav>

        {/* Page eyebrow */}
        <div
          style={{
            color: "var(--qgi-text-dim)",
            fontSize: "10px",
            letterSpacing: "4px",
            textTransform: "uppercase",
            fontFamily: "ui-monospace, monospace",
            marginBottom: "8px",
          }}
        >
          Trajectory
        </div>

        <h1
          style={{
            fontSize: "28px",
            fontWeight: 600,
            lineHeight: 1.15,
            margin: "0 0 8px",
            textTransform: "capitalize",
          }}
        >
          Canonical movement shape
        </h1>
        <p
          style={{
            fontSize: "13px",
            color: "var(--qgi-text-dim)",
            maxWidth: "72ch",
            lineHeight: 1.6,
            margin: "0 0 32px",
          }}
        >
          The normalised indicator-composite arc that this trend&apos;s verified-positive
          history rhymes around, measured over 12 quarters leading up to the canonical
          event. Retrospective only: this is what the model has seen in the past, not a
          forecast.
        </p>

        {shapePoints && shapePoints.length > 1 ? (
          <div
            style={{
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderLeft: "3px solid #7B5EE6",
              borderRadius: "6px",
              padding: "24px",
            }}
          >
            {/* Eyebrow */}
            <div
              style={{
                fontSize: "10px",
                letterSpacing: "1.5px",
                textTransform: "uppercase",
                fontFamily: "ui-monospace, monospace",
                color: "#7B5EE6",
                marginBottom: "16px",
              }}
            >
              {slug.replace(/_/g, " ")} · 12-quarter canonical arc
            </div>

            {/* SVG sparkline — full width, 80px tall */}
            <svg
              viewBox={`0 0 800 80`}
              preserveAspectRatio="none"
              style={{
                display: "block",
                width: "100%",
                height: "80px",
                overflow: "visible",
                marginBottom: "8px",
              }}
              role="img"
              aria-label={`Canonical movement shape for ${slug.replace(/_/g, " ")}, 12 quarters`}
            >
              {/* Midline (50 = z=0) */}
              <line
                x1={0}
                y1={40}
                x2={800}
                y2={40}
                stroke="var(--qgi-border)"
                strokeWidth={1}
                strokeDasharray="4 4"
              />
              {/* Shape line */}
              <polyline
                points={shapePoints
                  .map((v, i) => {
                    const x = (i / (shapePoints!.length - 1)) * 800;
                    const y = 80 - (v / 100) * 80;
                    return `${x.toFixed(1)},${y.toFixed(1)}`;
                  })
                  .join(" ")}
                fill="none"
                stroke="#7B5EE6"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {/* End dot */}
              {(() => {
                const lastIdx = shapePoints.length - 1;
                const lastX = 800;
                const lastY = 80 - (shapePoints[lastIdx] / 100) * 80;
                return <circle cx={lastX} cy={lastY} r={4} fill="#7B5EE6" />;
              })()}
            </svg>

            {/* Quarter axis */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginBottom: "16px",
              }}
            >
              {quarterLabels.map((q) => (
                <span
                  key={q}
                  style={{
                    fontSize: "9px",
                    fontFamily: "ui-monospace, monospace",
                    color: "var(--qgi-text-dim)",
                    letterSpacing: "0.3px",
                  }}
                >
                  {q}
                </span>
              ))}
            </div>

            {/* Chart footnotes — stack to one column below 480px (phones),
                side-by-side above. Pure Tailwind, no injected <style>. */}
            <div
              className="flex flex-col gap-1 min-[480px]:flex-row min-[480px]:justify-between min-[480px]:gap-0"
              style={{
                fontSize: "10.5px",
                fontFamily: "ui-monospace, monospace",
                color: "var(--qgi-text-dim)",
              }}
            >
              <span>Indicator composite z-score (display scale 0–100; 50 = z=0)</span>
              <span style={{ color: "var(--qgi-text-dim)", fontStyle: "italic" }}>
                Past only: line ends at canonical event
              </span>
            </div>

            {/* Description if available */}
            {shapeNote && (
              <p
                style={{
                  marginTop: "20px",
                  fontSize: "12px",
                  lineHeight: 1.6,
                  color: "var(--qgi-text-dim)",
                  maxWidth: "80ch",
                  fontStyle: "italic",
                }}
              >
                {shapeNote}
              </p>
            )}
          </div>
        ) : (
          /* Empty state — recipe not in fleet-run-1 or shape_points absent */
          <div
            style={{
              padding: "40px 24px",
              border: "1px dashed var(--qgi-border)",
              borderRadius: "6px",
              background: "rgba(91, 126, 153, 0.05)",
              textAlign: "center",
              maxWidth: "640px",
              margin: "40px auto",
            }}
          >
            <h2
              style={{
                fontSize: "16px",
                fontWeight: 600,
                marginBottom: "10px",
                color: "var(--qgi-text)",
              }}
            >
              Trajectory shape not yet available
            </h2>
            <p
              style={{
                color: "var(--qgi-text-muted)",
                fontSize: "13px",
                lineHeight: 1.6,
              }}
            >
              The shape series for this trend has not been emitted by the bake yet. This
              page will populate when the trajectory engine produces shape output for this
              trend.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
