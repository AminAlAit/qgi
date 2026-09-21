/**
 * Dev-only entry button into the admin control room.
 * Renders a fixed bottom-right pill ONLY under `next dev`
 * (NODE_ENV === "development"); returns null in any prod/preview build, so it
 * never ships publicly. Matches the localhost-only gate in app/(admin)/layout.
 */
import Link from "next/link";
import type { Route } from "next";

export function DevAdminButton() {
  if (process.env.NODE_ENV !== "development") return null;
  return (
    <Link
      href={"/admin" as Route}
      aria-label="Open admin control room (dev only)"
      style={{
        position: "fixed",
        right: "16px",
        bottom: "16px",
        zIndex: 1000,
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "8px 12px",
        fontSize: "12px",
        fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
        letterSpacing: "0.5px",
        color: "#cfe0ec",
        background: "rgba(91, 126, 153, 0.92)",
        border: "1px solid #5B7E99",
        borderRadius: "999px",
        textDecoration: "none",
        boxShadow: "0 2px 10px rgba(0,0,0,0.35)",
      }}
    >
      ⚙ ADMIN
    </Link>
  );
}
