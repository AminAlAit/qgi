"use client";

/**
 * DataFreshness — small inline timestamp + freshness warning (#137).
 *
 * QGI's pipeline runs monthly. Without an explicit "data as of" stamp, users
 * naturally assume real-time signals (it's a website, after all). This
 * component closes that gap: every signals view shows when the data was
 * generated, escalating from a subtle gray "Updated 3 days ago" to an amber
 * "Updated 4 weeks ago — refresh due" once the data passes a freshness
 * threshold.
 *
 * Threshold: 21 days (3 weeks). The pipeline runs monthly so anything past
 * 3 weeks is approaching staleness; past 5 weeks is genuinely overdue.
 */

const FRESHNESS_THRESHOLDS = {
  stale_days: 21, // amber warning
  overdue_days: 35, // red warning
} as const;

export type FreshnessLevel = "fresh" | "stale" | "overdue" | "unknown";

export function getFreshnessLevel(
  generatedAt: string | null | undefined
): FreshnessLevel {
  if (!generatedAt) return "unknown";
  const generated = new Date(generatedAt).getTime();
  if (Number.isNaN(generated)) return "unknown";
  const ageMs = Date.now() - generated;
  const ageDays = ageMs / (1000 * 60 * 60 * 24);
  if (ageDays >= FRESHNESS_THRESHOLDS.overdue_days) return "overdue";
  if (ageDays >= FRESHNESS_THRESHOLDS.stale_days) return "stale";
  return "fresh";
}

export function formatRelativeTime(generatedAt: string | null | undefined): string {
  if (!generatedAt) return "unknown";
  const generated = new Date(generatedAt).getTime();
  if (Number.isNaN(generated)) return "unknown";
  const ageMs = Date.now() - generated;
  const minutes = Math.floor(ageMs / 60_000);
  const hours = Math.floor(ageMs / 3_600_000);
  const days = Math.floor(ageMs / 86_400_000);
  const weeks = Math.floor(days / 7);

  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  if (days < 14) return `${days} day${days === 1 ? "" : "s"} ago`;
  if (days < 60) return `${weeks} week${weeks === 1 ? "" : "s"} ago`;
  const months = Math.floor(days / 30);
  return `${months} month${months === 1 ? "" : "s"} ago`;
}

interface DataFreshnessProps {
  generatedAt: string | null | undefined;
  /** Optional label prefix, e.g. "Pipeline data" or "Live query". Defaults to "Updated". */
  label?: string;
}

export function DataFreshness({ generatedAt, label = "Updated" }: DataFreshnessProps) {
  const level = getFreshnessLevel(generatedAt);
  const relative = formatRelativeTime(generatedAt);

  const color =
    level === "overdue"
      ? "var(--qgi-danger)"
      : level === "stale"
        ? "var(--qgi-amber)"
        : level === "fresh"
          ? "var(--qgi-text-dim)"
          : "var(--qgi-text-dim)";

  const suffix =
    level === "overdue" ? ", refresh overdue" : level === "stale" ? ", refresh due" : "";

  // Tooltip with the absolute timestamp for users who want to know exactly
  const absolute = generatedAt
    ? new Date(generatedAt).toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "unknown";

  return (
    <span
      className="text-[10px] tracking-wider font-data inline-flex items-center gap-1.5"
      style={{ color }}
      title={`${label}: ${absolute}`}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label.toUpperCase()} {relative.toUpperCase()}
      {suffix.toUpperCase()}
    </span>
  );
}
