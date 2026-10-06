/**
 * Dynamic sitemap (T19 #312).
 *
 * Enumerates every public route + every country-profile + category
 * drill-down from the baked country-risks.json. Regenerated on the page
 * revalidation cadence (hourly) so new countries + categories surface
 * within an hour of a pipeline run.
 */
import type { MetadataRoute } from "next";
import { loadCountryRisks } from "@/lib/country-risks";

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://qgintelligence.com";

// Revalidate hourly; this is cheap because loadCountryRisks() is in-process
// cached and the JSON is ~2.6 MB.
export const revalidate = 3600;

// Static top-level pages.
const STATIC_ROUTES: Array<{
  path: string;
  changeFrequency: "daily" | "weekly" | "monthly";
  priority: number;
}> = [
  { path: "/", changeFrequency: "weekly", priority: 1.0 },
  // V3 canonical family pages — public-facing landing surfaces.
  // PR-iii (2026-05-15): these URLs now serve the V3 (formerly -merged)
  // shells. Legacy V1 lives at `-v1` and is `Disallow`'d in robots.ts.
  //
  // NOTE: /dashboard intentionally NOT listed — current dashboard still
  // carries `robots: { index: false }` (transitional state until PR-vi
  // redesigns it as QGI's landing page). When PR-vi flips it to
  // indexable, add `{ path: "/dashboard", changeFrequency: "weekly", priority: 0.95 }`.
  // V4.1 canonical family pages (promoted 2026-05-28).
  // /signals and /precedents are deleted; /trends, /countries, /patterns
  // are now V4.1 canonical. /risk-board, /compare, /compound-risk,
  // /analogues are new surfaces added in the V4.1 promo.
  { path: "/dashboard", changeFrequency: "daily", priority: 0.95 },
  { path: "/trends", changeFrequency: "weekly", priority: 0.9 },
  { path: "/countries", changeFrequency: "daily", priority: 0.9 },
  // /patterns retired 2026-06-05 (308 → /analogues); removed from the
  // sitemap to avoid surfacing a redirecting URL.
  { path: "/risk-board", changeFrequency: "daily", priority: 0.8 },
  // /compound-risk taken down 2026-05-30; sitemap entry removed.
  // Redirect 308 → /risk-board.
  { path: "/compare", changeFrequency: "weekly", priority: 0.6 },
  { path: "/analogues", changeFrequency: "weekly", priority: 0.6 },
  // /recipe-tracker route deleted 2026-05-29 — folded into /trends via
  // the per-card Confidence badge. The status-board blog post lives at
  // /blog/trend-tracker (renamed 2026-06-05 from /blog/recipe-tracker).
  { path: "/methodology", changeFrequency: "monthly", priority: 0.8 },
  { path: "/methodology/indicators", changeFrequency: "monthly", priority: 0.6 },
  { path: "/methodology/events", changeFrequency: "monthly", priority: 0.6 },
  { path: "/contact", changeFrequency: "monthly", priority: 0.4 },
  { path: "/blog", changeFrequency: "weekly", priority: 0.6 },
  // Trend Tracker: continuously updated as trends move between tiers.
  {
    path: "/blog/trend-tracker",
    changeFrequency: "weekly",
    priority: 0.7,
  },
  // Ghana piece moved to /reports (2026-05-19); /blog/ghana-mauritania-mirror
  // 301-redirects via next.config.ts. Removed from sitemap to avoid
  // surfacing a redirecting URL.
  {
    path: "/blog/foreign-intervention-graduation",
    changeFrequency: "monthly",
    priority: 0.65,
  },
  {
    path: "/blog/burkina-faso-mali-car-precedent",
    changeFrequency: "monthly",
    priority: 0.5,
  },
  {
    path: "/blog/margin-over-persistence-trajectory",
    changeFrequency: "monthly",
    priority: 0.5,
  },
  {
    path: "/blog/cross-country-normalization",
    changeFrequency: "monthly",
    priority: 0.5,
  },
  {
    path: "/blog/curation-in-practice",
    changeFrequency: "monthly",
    priority: 0.5,
  },
  { path: "/reports", changeFrequency: "monthly", priority: 0.6 },
  // R8 podium pieces, published 2026-05-21.
  {
    path: "/reports/niger-burkina-divergence",
    changeFrequency: "monthly",
    priority: 0.65,
  },
  {
    path: "/reports/india-pakistan-mirror",
    changeFrequency: "monthly",
    priority: 0.65,
  },
  {
    path: "/reports/ukraine-bosnia-mirror",
    changeFrequency: "monthly",
    priority: 0.65,
  },
  // Ghana country analysis elevated from /blog (2026-05-19).
  {
    path: "/reports/ghana-mauritania-mirror",
    changeFrequency: "monthly",
    priority: 0.6,
  },
  // #430 (2026-04-24): FSI demo report re-added to sitemap. Agent 7 QA
  // audit confirmed it renders fully with proper metadata + print CSS.
  // Also re-linked from /reports index so it's reachable via normal nav.
  {
    path: "/reports/fsi-qgi-report",
    changeFrequency: "monthly",
    priority: 0.5,
  },
  { path: "/about", changeFrequency: "monthly", priority: 0.4 },
  { path: "/legal", changeFrequency: "monthly", priority: 0.3 },
];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const entries: MetadataRoute.Sitemap = STATIC_ROUTES.map((r) => ({
    url: `${BASE_URL}${r.path}`,
    lastModified: now,
    changeFrequency: r.changeFrequency,
    priority: r.priority,
  }));

  // Country-profile routes from the baked country-risks.json.
  //
  // 2026-06-01: the /precedents/{slug} and /signals/{...} emissions were
  // removed. Both route families were deleted in the V4.1 promotion (they
  // now redirect or 404), so listing them only fed search engines
  // redirecting/dead URLs. Recipes live at /trends; country profiles at
  // /countries/{id}, which is the only dynamic family still emitted here.
  try {
    const data = await loadCountryRisks();
    const lastMod = data.generated_at ? new Date(data.generated_at) : now;
    for (const [id, country] of Object.entries(data.countries)) {
      entries.push({
        url: `${BASE_URL}/countries/${id}`,
        lastModified: lastMod,
        changeFrequency: "weekly",
        priority: country.overall_risk_tier === "HIGH" ? 0.7 : 0.5,
      });
    }
  } catch {
    // If country-risks.json is unreachable at build time, ship just the
    // static routes rather than failing the sitemap entirely.
  }

  return entries;
}
