"use client";

import { useEffect } from "react";

/**
 * Global error boundary — the last line of defence, for errors thrown in the
 * root layout itself (where the normal error.tsx cannot mount). It must render
 * its own <html>/<body>, so styling is inline and minimal.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[global error boundary]", error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "#0F1923",
          color: "#E6EAF0",
          fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
          padding: "24px",
        }}
      >
        <div style={{ maxWidth: "420px", textAlign: "center" }}>
          <p
            style={{
              fontSize: "10px",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "#7A8696",
              marginBottom: "12px",
            }}
          >
            QG Intelligence
          </p>
          <h1 style={{ fontSize: "22px", fontWeight: 600, margin: "0 0 12px" }}>
            Something went wrong.
          </h1>
          <p
            style={{
              fontSize: "14px",
              lineHeight: 1.6,
              color: "#9aa4b2",
              marginBottom: "24px",
            }}
          >
            The site hit an unexpected error. Please try again.
          </p>
          <button
            onClick={() => reset()}
            style={{
              padding: "10px 20px",
              borderRadius: "6px",
              border: "none",
              backgroundColor: "#5BA8E8",
              color: "#0F1923",
              fontSize: "14px",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
          {error.digest ? (
            <p
              style={{
                marginTop: "20px",
                fontSize: "10px",
                color: "#7A8696",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              Reference: {error.digest}
            </p>
          ) : null}
        </div>
      </body>
    </html>
  );
}
