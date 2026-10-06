/**
 * /trends/trajectory-ranking — Trajectory strength ranking.
 *
 * MOCK ELIMINATION — 2026-05-30
 * getRanking() built its rows from patterns-v4-data.ts synthesised
 * current_top_matches (buildCurrentMatches, lines 661-721). Entire
 * data set was synthesised from recipe mock country lists — zero fleet data.
 * The trajectory-ranking concept is real and the bake could carry it, but
 * it doesn't yet. Verdict: honest empty state.
 * Gap logged to C:\tmp\backend-gaps\patterns-trajectory.md
 *
 * Route remains alive so the "Trajectory strength ranking" link on recipe
 * pages does not 404.
 */
import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";

export const metadata: Metadata = {
  title: "Trajectory strength ranking · QG Intelligence",
  description:
    "Top countries ranked by how closely their current movement resembles any trend trajectory.",
};

export default function TrajectoryRankingPage() {
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
          <span style={{ color: "var(--qgi-text)" }}>Trajectory strength ranking</span>
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
          Trajectory strength ranking
        </div>

        <h1
          style={{
            fontSize: "30px",
            fontWeight: 600,
            lineHeight: 1.15,
            margin: "0 0 12px",
          }}
        >
          Countries ranked by trajectory match
        </h1>

        {/* Honest empty state */}
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
            Trajectory ranking not yet available
          </h2>
          <p
            style={{
              color: "var(--qgi-text-muted)",
              fontSize: "13px",
              lineHeight: 1.6,
            }}
          >
            The trajectory strength ranking lists countries whose current indicator
            movement most closely resembles a trend&apos;s canonical shape. This ranking
            is a real concept the bake will carry, but per-country trajectory alignment
            scores are not yet emitted by the bake. The table will populate here when the
            trajectory engine begins scoring countries against each trend shape.
          </p>
        </div>
      </div>
    </div>
  );
}
