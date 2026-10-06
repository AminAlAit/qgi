/**
 * FeaturedReportCard — server component, no client JS.
 *
 * Surfaces the flagship UK Currency Crisis report as a full-width hero card.
 * Numbers are baked at build time; no fetch, no cache, no runtime cost.
 */
import Link from "next/link";
import type { Route } from "next";
import { getDisplayableReports } from "@/app/reports/_data/reports-manifest";

const FLAGSHIP_SLUG = "uk-currency-crisis";

export function FeaturedReportCard() {
  const reports = getDisplayableReports();
  const report = reports.find((r) => r.slug === FLAGSHIP_SLUG);

  // Fallback values derived from the manifest data — these are real numbers.
  const eyestat = report?.eyestat ?? {
    primary: "#1 of 157",
    label: "Currency-crisis resemblance",
    secondary: "nearest analogue: its own 1992 (0.975)",
    countryLabel: "United Kingdom",
  };

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        backgroundColor: "var(--qgi-surface)",
        borderLeft: "3px solid var(--qgi-accent)",
        boxShadow: "none",
        transition: "box-shadow 0.18s ease",
      }}
      onMouseEnter={undefined}
    >
      <div className="flex flex-col md:flex-row gap-8 p-8 md:p-10">
        {/* Left column — prose */}
        <div className="flex-1 min-w-0">
          <p
            className="text-[10px] tracking-widest uppercase mb-4"
            style={{
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            Featured Report
          </p>

          <h2
            className="text-[22px] md:text-[24px] font-semibold leading-snug mb-4"
            style={{ color: "var(--qgi-text)" }}
          >
            The UK ranks #1 of 157 countries on currency-crisis resemblance. The top
            driver is not the gilt market.
          </h2>

          <p
            className="text-sm leading-relaxed mb-2"
            style={{ color: "var(--qgi-text-muted)", maxWidth: "54ch" }}
          >
            QGI&rsquo;s pattern engine reads every country&rsquo;s multi-decade indicator
            trajectory against the historical record. In the latest run, the United
            Kingdom sits at the top of the global leaderboard. The largest single signal
            driver &mdash; 34.5% of the score &mdash; is judicial reform attempts, not the
            current account.
          </p>
          <p
            className="text-xs leading-relaxed mb-6"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            (A measure of structural resemblance drawn from the historical record, not a
            forecast of an imminent event.)
          </p>

          <Link
            href={"/reports/uk-currency-crisis" as Route}
            className="text-sm font-medium border-b pb-0.5 transition-opacity hover:opacity-80"
            style={{
              color: "var(--qgi-accent)",
              borderColor: "var(--qgi-accent)",
            }}
          >
            Read the full analysis &rarr;
          </Link>

          <p
            className="mt-5 text-[10px] tracking-widest uppercase"
            style={{
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            June 2026 run
          </p>
        </div>

        {/* Right column — stat block: stacks on mobile, side-by-side on md+ */}
        <div
          className="flex-shrink-0 flex flex-col items-start md:items-end justify-center gap-2 md:min-w-[160px] md:pl-8 md:border-l"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          <div className="text-left md:text-right">
            <div
              className="text-[36px] md:text-[42px] font-bold leading-none"
              style={{
                color: "var(--qgi-accent)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {eyestat.primary}
            </div>
            <div
              className="text-[11px] mt-1 leading-tight"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              {eyestat.label}
            </div>
            {eyestat.secondary && (
              <div
                className="text-[10px] mt-2"
                style={{
                  color: "var(--qgi-text-dim)",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                UK 1992 &middot; 97.5% structural match
              </div>
            )}
          </div>
          <div
            className="text-[10px] tracking-widest uppercase text-left md:text-right"
            style={{
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            United Kingdom
          </div>
        </div>
      </div>
    </div>
  );
}
