import Link from "next/link";
import type { Route } from "next";
import type { Report } from "../_data/reports-manifest";
import { formatPublishedDate } from "../_data/reports-manifest";
import { ReportThumbnail } from "./Thumbnails";

type ReportCardProps = {
  report: Report;
  featured?: boolean;
};

function FormatChip({ format }: { format: Report["format"] }) {
  const isDeepDive = format === "deep-dive";
  return (
    <span
      className="inline-flex items-center text-[9px] tracking-widest uppercase font-data px-2 py-0.5 rounded"
      style={{
        color: isDeepDive ? "var(--qgi-accent)" : "#f59e0b",
        backgroundColor: isDeepDive
          ? "rgba(167, 139, 250, 0.08)"
          : "rgba(245, 158, 11, 0.08)",
        border: isDeepDive
          ? "1px solid rgba(167, 139, 250, 0.2)"
          : "1px solid rgba(245, 158, 11, 0.25)",
      }}
    >
      {isDeepDive ? "Deep Dive" : "Brief"}
    </span>
  );
}

function MetadataRow({ report }: { report: Report }) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <FormatChip format={report.format} />
      {report.clusterKey && (
        <span
          className="inline-flex items-center text-[9px] tracking-widest uppercase font-data px-2 py-0.5 rounded"
          style={{
            color: "var(--qgi-text-dim)",
            backgroundColor: "rgba(255, 255, 255, 0.04)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          From cluster
        </span>
      )}
      <span
        className="inline-flex items-center text-[10px] tracking-widest uppercase font-data px-2 py-1 rounded"
        style={{
          color: "var(--qgi-accent)",
          backgroundColor: "rgba(167, 139, 250, 0.08)",
          border: "1px solid rgba(167, 139, 250, 0.2)",
        }}
      >
        {report.category}
      </span>
      <span
        className="text-[10px] tracking-wider uppercase font-data ml-auto"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        {formatPublishedDate(report.publishedAt)}
      </span>
    </div>
  );
}

export function ReportCard({ report, featured = false }: ReportCardProps) {
  const titleSize = featured ? "text-xl" : "text-lg";

  const rawHref = report.href ?? `/reports/${report.slug}`;
  if (!rawHref.startsWith("/") && !rawHref.startsWith("https://")) {
    throw new Error(`Invalid report href: ${rawHref}`);
  }
  const href = rawHref as Route;

  return (
    <Link
      href={href}
      className="block h-full focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--qgi-bg)] rounded-lg hover:[&_article]:border-[var(--qgi-accent)]"
    >
      <article
        className="h-full flex flex-col rounded-lg border overflow-hidden transition-all duration-150 group"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <ReportThumbnail report={report} />
        <div className="flex flex-col flex-1 p-5">
          <MetadataRow report={report} />
          <h2
            className={`${titleSize} font-semibold leading-snug mb-2 transition-colors`}
            style={{ color: "var(--qgi-text)" }}
          >
            {report.title}
          </h2>
          <p
            className="text-sm leading-relaxed line-clamp-3"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            {report.summary}
          </p>
        </div>
      </article>
    </Link>
  );
}
