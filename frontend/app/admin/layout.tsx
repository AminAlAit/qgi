/**
 * Admin route-group chrome.
 *
 * LOCALHOST-ONLY: this whole route group 404s unless NODE_ENV === "development"
 * (i.e. it renders under `next dev` but never in a Vercel production/preview
 * build). No auth gate is needed and proxy.ts is untouched — the founder asked
 * for a no-login button straight in for now; when user-auth ships, swap this
 * gate for a NextAuth session check + a proxy matcher entry.
 */
import { notFound } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import type { ReactNode } from "react";
import { loadVintage, loadRunIndex } from "@/lib/admin/admin-data";

const NAV: Array<{ href: string; label: string }> = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/trends", label: "Trends" },
  { href: "/admin/content", label: "Content" },
  { href: "/admin/signals", label: "Signals" },
  { href: "/admin/system", label: "System" },
];

export const metadata = {
  title: "QGI Admin · Control Room",
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: { children: ReactNode }) {
  if (process.env.NODE_ENV !== "development") notFound();

  const vintage = loadVintage();
  const runIndex = loadRunIndex();

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--qgi-bg)",
        color: "var(--qgi-text)",
      }}
    >
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 20,
          display: "flex",
          alignItems: "center",
          gap: "20px",
          height: "48px",
          padding: "0 24px",
          background: "var(--qgi-surface)",
          borderBottom: "1px solid var(--qgi-border)",
        }}
      >
        <span
          className="font-data"
          style={{
            fontSize: "12px",
            letterSpacing: "2px",
            color: "#5B7E99",
            fontWeight: 700,
          }}
        >
          QGI · CONTROL ROOM
        </span>
        <nav style={{ display: "flex", gap: "4px" }}>
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href as Route}
              style={{
                fontSize: "12px",
                color: "var(--qgi-text-muted)",
                textDecoration: "none",
                padding: "4px 10px",
                borderRadius: "5px",
              }}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <span
          className="font-data"
          style={{ marginLeft: "auto", fontSize: "11px", color: "var(--qgi-text-dim)" }}
          title="Active fleet vintage"
        >
          run-{runIndex} · {vintage.slice(0, 10)}
        </span>
      </header>
      <main style={{ maxWidth: "1480px", margin: "0 auto", padding: "20px 24px 64px" }}>
        {children}
      </main>
    </div>
  );
}
