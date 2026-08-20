/**
 * Sentry — server runtime init (#451).
 *
 * Loaded by `instrumentation.ts` when `process.env.NEXT_RUNTIME === "nodejs"`.
 * Captures server errors from API routes, Server Components, and any code
 * paths reached from the Node.js runtime on Vercel.
 *
 * Init is gated on `SENTRY_DSN` so missing env (local dev, fork PRs without
 * secret access) is a quiet no-op rather than a crash on boot.
 */
import * as Sentry from "@sentry/nextjs";

if (process.env.SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.SENTRY_DSN,
    // Tracing samples — keep low until we have a feel for volume + cost.
    // Vercel Hobby tier free Sentry events are limited; 10% sample is a
    // reasonable starting point that we tune based on the dashboard.
    tracesSampleRate: 0.1,
    // Don't send errors from local dev (`NODE_ENV !== "production"`) — the
    // Vercel staging deploy is "production" enough; local should stay
    // out of the dashboard.
    enabled: process.env.NODE_ENV === "production",
    // Mute the Sentry SDK's own console output so build / runtime logs
    // stay readable. Real Sentry issues appear in the dashboard, not in
    // server logs.
    debug: false,
  });
}
