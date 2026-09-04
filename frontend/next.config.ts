import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

/**
 * Hard guard against the single worst auth foot-gun: SKIP_AUTH bypasses all
 * gating (dev pre-paywall posture), and the documented default in Vercel is
 * `true`. Nothing else stops that value from being set in the Production
 * environment scope by mistake, which would silently disable the login wall on
 * qgintelligence.com. This runs at build time on Vercel, so a prod build with
 * SKIP_AUTH=true fails loudly instead of shipping wide open. (Preview/dev are
 * unaffected — VERCEL_ENV is only "production" for prod deploys.)
 */
if (process.env.VERCEL_ENV === "production" && process.env.SKIP_AUTH === "true") {
  throw new Error(
    "SKIP_AUTH=true is not allowed in a production deploy — it disables the auth gate. Unset it in the Vercel Production environment."
  );
}

/**
 * #748 PR-3 (#751) — Retired precedent slugs (2026-05-17).
 *
 * These slugs used to 301-redirect to `/precedents`. That route is now
 * deleted as part of the V4.1 canonical promotion (2026-05-28). The list
 * is kept here for reference but is no longer used in redirects().
 *
 * RETIRED_PRECEDENT_SLUGS is unused; kept for audit trail.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const RETIRED_PRECEDENT_SLUGS = [
  "government_formation",
  "constitutional_change",
  "decentralization_and_federalism",
  "democratic_transition",
  "executive_power_consolidation",
  "military_coup",
  "coup_attempt_or_succession",
  "transitional_justice",
  "peacekeeping_and_peace_process",
  "constitutional_referendum",
  "interstate_war",
  "terrorist_attack",
  "foreign_intervention",
  "ethnic_and_communal_conflict",
  "political_violence",
  "ceasefire_agreement",
  "west_bank_violence",
  "israeli_military_operation",
  "rocket_attack",
  "political_repression",
  "political_corruption",
  "human_rights_violation",
  "human_rights_reform",
  "military_policy_and_reform",
  "currency_crisis",
  "banking_and_financial_crisis",
  "economic_recession",
  "fiscal_policy_change",
  "monetary_policy_change",
  "economic_liberalization",
  "economic_nationalization",
  "economic_recovery",
  "economic_growth_milestone",
  "economic_growth",
  "trade_agreement",
  "trade_dispute",
  "foreign_direct_investment",
  "industrial_policy",
  "sanctions_and_arms_embargo",
  "foreign_aid_and_development",
  "economic_struggle",
  "economic_crisi",
  "economic_reform",
  "mass_protest",
  "labor_action",
  "social_policy_reform",
  "public_health_reform",
  "poverty_and_inequality_crisis",
  "religious_and_social_movement",
  "migration_and_refugees",
  "political_unrest",
  "social_program",
  "diplomatic_rupture",
  "territorial_disputes",
  "regional_integration",
  "diplomatic_effort",
  "international_diplomacy",
  "earthquake",
  "flood_and_cyclone",
  "volcanic_eruption",
  "natural_disaster",
  "drought_and_famine",
  "epidemic_and_pandemic",
  "humanitarian_crisis",
  "water_crisis",
  "pandemic_response",
  "humanitarian_crisi",
  "energy_policy",
  "oil_and_gas",
  "renewable_energy",
  "environmental_policy",
  "climate_agreement",
  "resource_conflict",
  "infrastructure_project",
  "urban_development",
  "education_reform",
  "education_and_research",
  "digital_policy",
  "technology_breakthrough",
  "cyberattack",
  "cultural_and_heritage",
  "sport_and_international_event",
  "agricultural_policy",
  "environmental_effort",
  "infrastructure_development",
  "cultural_heritage",
];

/**
 * Next.js 16 config.
 *
 * T16 #309 (2026-04-19) — performance tuning:
 *  - `optimizePackageImports` rewrites `import * as Flags from "country-flag-icons/react/3x2"`
 *    so only the flag components actually referenced are bundled, instead of
 *    all 272 SVG components landing in every route that touches CountryFlag.
 *  - `echarts` similarly benefits — only the chart types the app uses ship.
 *  - AVIF/WebP image formats automatic for `next/image` usages.
 *  - `poweredByHeader: false` strips the `X-Powered-By: Next.js`
 *    fingerprint from responses (small security hygiene win).
 */
const nextConfig: NextConfig = {
  // #440: typed routes promote `<Link href="/...">` to a compile-time
  // contract. A typo in any internal route (or a stale link to a
  // deleted page) becomes a build failure instead of a silent runtime
  // 404 — same regression class #426 was triaging post-hoc; with this
  // on, those links would never have compiled. Stable in Next 16, no
  // longer behind `experimental`.
  typedRoutes: true,
  experimental: {
    optimizePackageImports: ["country-flag-icons", "echarts", "echarts-for-react"],
  },
  images: {
    formats: ["image/avif", "image/webp"],
  },
  poweredByHeader: false,
  /**
   * Keep the heavy committed STRUCTURAL data out of the news-terminal's
   * serverless bundle (perma-fix, 2026-06-14).
   *
   * The Live Pulse terminal renders only the news layer (hf-pulse / live-pulse
   * data). But it imports getCountryByIso for one back-link, which transitively
   * pulls in the entire te-mock fleet/analogue graph — ~280 MB of committed
   * JSON the terminal NEVER reads at runtime, traced into its function purely
   * as dead weight. That pushed the function past Vercel's 250 MB limit
   * (the #189 deploy failed on exactly this).
   *
   * These excludes drop that dead weight. They are GLOB patterns
   * (te-fleet-run-*, etc.), so they stay correct as the fleet grows — a new run
   * or score file is excluded automatically, no maintenance. Only files the
   * terminal provably does not read at runtime are listed; the data it does use
   * (hf-pulse-detail, hf-topics, live-pulse/*, country-index, recipe-tracker)
   * is untouched, and data-heavy routes keep full access.
   */
  outputFileTracingExcludes: {
    "**/live-pulse/**": [
      "data/te-fleet-run-*/**",
      "data/verified-events.json",
      "data/country-risks.json",
      // (analogues*/country-events/country-partners-index/structural-twins were
      // removed from git in the 2026-06-15 slim-down — no longer need excluding.)
    ],
  },
  /**
   * 2026-05-28 — V4.1 canonical promotion redirects.
   *
   * Only four redirect families remain after the V4.1 promo:
   *  1. /precedents-v4.1 → /trends (bookmark preservation)
   *  2. /trends/foreign_intervention → /blog (graduation article)
   *  3. /countries-merged → /countries (PR-iii legacy)
   *  4. /patterns-merged → /patterns (PR-iii legacy)
   *  5. /blog/ghana-mauritania-mirror → /reports (elevation redirect)
   *
   * All redirects that targeted deleted routes (/precedents, /signals,
   * /patterns-v1, /signals-v1, /patterns-v2a, /patterns-v2b, etc.) have
   * been removed — 404 is better than a redirect to a 404.
   */
  async redirects() {
    return [
      // 2026-06-05 (founder): /patterns retired from the public surface; the
      // Analogue is its replacement. The route files + SCDI/pattern code are
      // kept (saved), but every /patterns URL now redirects to /analogues.
      // Placed first so it supersedes the older /patterns/* rules below.
      {
        source: "/patterns",
        destination: "/analogues",
        permanent: true,
      },
      {
        source: "/patterns/:path*",
        destination: "/analogues",
        permanent: true,
      },
      // 2026-05-31 (founder): /landing-v2 promoted to the homepage "/".
      // Preserve any links to the old staging URL.
      {
        source: "/landing-v2",
        destination: "/",
        permanent: true,
      },
      // 2026-06-04 (founder): the /patterns/<slug> → /patterns redirect is
      // REMOVED. The per-pattern detail page is now real (renders from
      // getPairBySlug; no mock), so single-segment pattern slugs resolve to
      // their detail page again. The /patterns/pair/<slug> route stays retired.
      // 2026-05-30 — /compound-risk taken down. Page deleted; bookmarks
      // redirect to /risk-board (the most-overlapping live surface).
      // Components + data layer stay in tree (components/compound-risk/,
      // lib/te-mock/compound-risk-data.ts) for a future rejuvenation per
      // the Stats/ML trio paper (compound-negative-event-density path).
      {
        source: "/compound-risk",
        destination: "/risk-board",
        permanent: true,
      },

      // 2026-05-30 — /nearest-analog renamed to /analogues (British spelling,
      // founder-ratified). 308 preserves bookmarks and any external links.
      {
        source: "/nearest-analog",
        destination: "/analogues",
        permanent: true,
      },
      {
        source: "/nearest-analog/:path*",
        destination: "/analogues/:path*",
        permanent: true,
      },

      // 2026-05-29 — V4.1 round-3 amendment. The /recipe-tracker route
      // (catalog ledger) was deleted; its AUC column reborn as the per-card
      // Confidence badge on /trends. Bookmarks preserved here.
      // NOTE: /blog/recipe-tracker is a SEPARATE route (the audience-facing
      // status-board blog post) — it has its own exact redirect below; this
      // exact source string deliberately does not catch it.
      {
        source: "/recipe-tracker",
        destination: "/trends",
        permanent: true,
      },

      // 2026-06-05 (founder): the status-board blog post renamed to match
      // the site-wide Trends vocabulary — /blog/recipe-tracker is now
      // /blog/trend-tracker. Exact source; other /blog/* slugs unaffected.
      {
        source: "/blog/recipe-tracker",
        destination: "/blog/trend-tracker",
        permanent: true,
      },

      // 2026-06-04 (founder): the "Recipes" surface was renamed to "Trends"
      // site-wide; the route moved /recipes -> /trends. Preserve every old
      // /recipes link (the gallery and each detail page). These two rules are
      // deliberately scoped to the /recipes path only:
      //   - "/recipes"        — the gallery
      //   - "/recipes/:path*" — detail pages (e.g. /recipes/foreign_intervention)
      // They do NOT match /api/recipes (different prefix), /recipe-tracker,
      // or /blog/recipe-tracker (both handled above with exact sources).
      {
        source: "/recipes",
        destination: "/trends",
        permanent: true,
      },
      {
        source: "/recipes/:path*",
        destination: "/trends/:path*",
        permanent: true,
      },

      // 2026-05-28 — V4.1 canonical promotion. /precedents-v4.1 was the
      // pre-canonical URL for the Recipes surface; preserve bookmarks.
      {
        source: "/precedents-v4.1",
        destination: "/trends",
        permanent: true,
      },
      {
        source: "/precedents-v4.1/:path*",
        destination: "/trends/:path*",
        permanent: true,
      },

      // (Removed 2026-05-28) The previous redirect from
      // /trends/foreign_intervention → /blog/foreign-intervention-graduation
      // was retired when /recipes-v4.1/ was promoted to /trends/, because
      // foreign_intervention is now the canonical demo recipe slug for the
      // V4.1 detail page. The blog graduation article is still live at
      // /blog/foreign-intervention-graduation; visit it directly.

      // Old -merged URLs from the PR-iii (2026-05-15) V3 rename.
      // /countries and /patterns now serve V4.1 canonical routes.
      // /precedents and /signals are deleted; their -merged aliases
      // would 404 so they are not redirected.
      {
        source: "/countries-merged",
        destination: "/countries",
        permanent: true,
      },
      {
        source: "/countries-merged/:path*",
        destination: "/countries/:path*",
        permanent: true,
      },
      {
        source: "/patterns-merged",
        destination: "/analogues",
        permanent: true,
      },
      {
        source: "/patterns-merged/:slug*",
        destination: "/analogues",
        permanent: true,
      },

      // ─── 2026-05-19 — Ghana piece elevation from /blog to /reports ────
      {
        source: "/blog/ghana-mauritania-mirror",
        destination: "/reports/ghana-mauritania-mirror",
        permanent: true,
      },

      // 2026-06-04: the numeric /patterns/<numA>-<numB> redirect is REMOVED.
      // The catalogue's pattern slugs ARE numeric id-pairs ({country_a_id}-
      // {country_b_id}, e.g. 172-208), and the per-pattern detail page now
      // renders them for real (getPairBySlug). The old "numeric = legacy ->
      // /patterns" rule was intercepting every real pattern click. Unknown
      // slugs fall through to the page's notFound() (404), not a redirect.

      // ─── 2026-05-31 — pair-overview route retired ───────────────────────
      // 2-segment ISO-2 slugs (e.g. /patterns/gr-lb) used to serve a
      // pair-overview page. That view is removed; both the /pair/ subroute
      // and bare 2-segment slugs now redirect to /patterns.
      {
        source: "/patterns/pair/:slug",
        destination: "/patterns",
        permanent: true,
      },
      // 2-segment ISO-2 slug pattern: two lowercase 2-3 char codes with a dash.
      {
        source: "/patterns/:a([a-z]{2,3})-:b([a-z]{2,3})",
        destination: "/patterns",
        permanent: true,
      },
    ];
  },
};

/**
 * Sentry build-time integration (#451).
 *
 * Wraps the config so the Sentry webpack plugin runs on Vercel deploys:
 *  - Uploads source maps to Sentry (gated on SENTRY_AUTH_TOKEN; absent
 *    locally so dev builds aren't slowed by an auth call that 401s).
 *  - Tags releases with the git SHA Vercel injects.
 *  - Tunnels Sentry events through `/monitoring` to dodge ad blockers
 *    that would otherwise drop client-side error reports — common with
 *    finance/political analyst audiences who run aggressive blockers.
 *
 * `silent: true` so the build log doesn't get a wall of Sentry chatter.
 */
const sentryWebpackPluginOptions = {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  silent: true,
  // Tunnel Sentry events through /monitoring on our own domain. Bypasses
  // ad blockers + privacy extensions that block sentry.io directly.
  tunnelRoute: "/monitoring",
  // Don't fail the build if source-map upload fails (e.g. token rotation
  // mid-deploy). Errors still flow into Sentry; we just lose source-map
  // resolution for that release.
  errorHandler: (err: Error) => {
    console.warn("[sentry] source-map upload failed (non-fatal):", err.message);
  },
};

export default withSentryConfig(nextConfig, sentryWebpackPluginOptions);
