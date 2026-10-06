"use client";

import { useEffect } from "react";
import Link from "next/link";
import type { Route } from "next";

/**
 * Root error boundary. Catches uncaught render/data errors on any route and
 * shows a calm, branded recovery screen instead of a crash. Logs to the
 * console (Sentry picks it up in production); never echoes raw error text to
 * the user beyond a digest reference.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[app error boundary]", error);
  }, [error]);

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <div className="max-w-md text-center">
        <p
          className="text-[10px] tracking-widest uppercase mb-3"
          style={{ color: "var(--qgi-text-dim)", fontFamily: "ui-monospace, monospace" }}
        >
          Something went wrong
        </p>
        <h1 className="text-2xl font-semibold mb-4" style={{ color: "var(--qgi-text)" }}>
          This page hit an unexpected error.
        </h1>
        <p
          className="text-sm leading-relaxed mb-8"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          It is not you. Try again in a moment, or head back home. If it keeps happening,
          let us know.
        </p>
        <div className="flex flex-wrap gap-2 justify-center">
          <button
            onClick={() => reset()}
            className="px-5 py-2.5 rounded text-sm font-medium tracking-wide transition-all hover:brightness-110"
            style={{ backgroundColor: "var(--qgi-accent)", color: "var(--qgi-bg)" }}
          >
            Try again
          </button>
          <Link
            href={"/" as Route}
            className="px-5 py-2.5 rounded text-sm tracking-wide border transition-colors hover:bg-[var(--qgi-surface-2)]"
            style={{ borderColor: "var(--qgi-border)", color: "var(--qgi-text-muted)" }}
          >
            Back home
          </Link>
        </div>
        {error.digest ? (
          <p
            className="mt-6 text-[10px]"
            style={{
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            Reference: {error.digest}
          </p>
        ) : null}
      </div>
    </div>
  );
}
