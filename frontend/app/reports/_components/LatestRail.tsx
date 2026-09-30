import type { Report } from "../_data/reports-manifest";
import { ReportCard } from "./ReportCard";

type LatestRailProps = {
  reports: Report[];
};

export function LatestRail({ reports }: LatestRailProps) {
  if (reports.length === 0) return null;
  const featured = reports.slice(0, 2);

  return (
    <section
      aria-labelledby="recent-rail-label"
      className="mb-10 pb-10"
      style={{ borderBottom: "1px solid var(--qgi-border)" }}
    >
      <div className="flex items-center gap-3 mb-5">
        <h2
          id="recent-rail-label"
          className="text-[11px] tracking-[0.25em] uppercase font-data font-semibold"
          style={{ color: "var(--qgi-accent)" }}
        >
          Recent
        </h2>
        <span
          className="h-px flex-1"
          style={{ backgroundColor: "var(--qgi-border)" }}
          aria-hidden="true"
        />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {featured.map((report) => (
          <ReportCard key={report.slug} report={report} featured />
        ))}
      </div>
    </section>
  );
}
