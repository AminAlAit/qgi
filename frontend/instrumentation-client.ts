/**
 * Client-side instrumentation (#451) — runs before the app becomes interactive.
 *
 * Captures browser-side runtime errors that the server-side `onRequestError`
 * hook can't see (post-hydration React errors, async fetch failures from
 * dashboard widgets, ECharts render exceptions, etc).
 *
 * Init is gated on `NEXT_PUBLIC_SENTRY_DSN` (must be the public-facing
 * variant — server `SENTRY_DSN` isn't exposed to the browser bundle).
 * The DSN is safe to ship publicly: it identifies the project to send
 * events to, but Sentry rate-limits + filters by origin server-side.
 *
 * Reference: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/instrumentation-client.md
 */
import * as Sentry from "@sentry/nextjs";

if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    // Lower client trace sample — page navigation traces are expensive
    // and noisy. Server traces are the bulk of useful signal.
    tracesSampleRate: 0.05,
    // Replays disabled until we explicitly want them (free tier quota
    // is small and one bad page can chew through it overnight).
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    // Same prod-only gate as the server config.
    enabled: process.env.NODE_ENV === "production",
    debug: false,
  });
}

// Next 16 router-transition hook (currently a no-op; reserved for when we
// want to track navigation timing in Sentry breadcrumbs).
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
