/**
 * Server instrumentation hooks (#451).
 *
 * `register()` runs once per Next.js server boot. Loads the runtime-
 * specific Sentry config (Node.js vs Edge) so we can have different
 * settings per runtime if needed later.
 *
 * `onRequestError` is the Next 16 hook for server-side errors caught
 * during request handling (API routes, Server Components, route
 * handlers). It feeds errors into Sentry with full request context.
 *
 * Reference: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/instrumentation.md
 */
import * as Sentry from "@sentry/nextjs";
import type { Instrumentation } from "next";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export const onRequestError: Instrumentation.onRequestError = (err, request, context) => {
  Sentry.captureRequestError(err, request, context);
};
