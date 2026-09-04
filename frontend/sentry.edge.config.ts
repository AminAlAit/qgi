/**
 * Sentry — edge runtime init (#451).
 *
 * Loaded by `instrumentation.ts` when `process.env.NEXT_RUNTIME === "edge"`.
 * QGI doesn't currently use the Edge runtime (everything is Node.js for
 * Athena SDK reasons), but Sentry's Next.js docs require this file to
 * exist so edge code paths are covered when we add them later
 * (middleware, Edge API routes for #448 auth-posture cleanup).
 */
import * as Sentry from "@sentry/nextjs";

if (process.env.SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.SENTRY_DSN,
    tracesSampleRate: 0.1,
    enabled: process.env.NODE_ENV === "production",
    debug: false,
  });
}
