import Link from "next/link";

/**
 * In-shell 404 fallback for unknown URLs inside the `(app)` route group.
 *
 * PR-vii (2026-05-15) — added so that mistyped or stale URLs preserve the
 * Dashboard/sidebar shell rather than dropping the user onto Next.js's
 * default white-background 404 page. The shell stays; only the main
 * content area renders the error + a route back home.
 */
export default function NotFound() {
  return (
    <div className="p-8 lg:p-12 max-w-2xl mx-auto">
      <p
        className="text-[10px] tracking-widest uppercase mb-3"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        404 · Not found
      </p>
      <h1
        className="text-2xl font-semibold leading-snug mb-3"
        style={{ color: "var(--qgi-text)" }}
      >
        This page doesn&apos;t exist.
      </h1>
      <p
        className="text-sm leading-relaxed mb-6 max-w-[60ch]"
        style={{ color: "var(--qgi-text-muted)" }}
      >
        The URL you tried isn&apos;t one of QGI&apos;s routes. If you arrived from a
        bookmark, the page may have moved. Check the sidebar or jump back to the Dashboard
        below.
      </p>
      <div className="flex flex-wrap gap-2">
        <Link
          href="/dashboard"
          className="px-3 py-2 rounded text-[11px] tracking-widest uppercase border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
          style={{ borderColor: "var(--qgi-accent)", color: "var(--qgi-accent)" }}
        >
          ← Back to Dashboard
        </Link>
        <Link
          href="/trends"
          className="px-3 py-2 rounded text-[11px] tracking-widest uppercase border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
          style={{ borderColor: "var(--qgi-border)", color: "var(--qgi-text-muted)" }}
        >
          Trends
        </Link>
        <Link
          href="/countries"
          className="px-3 py-2 rounded text-[11px] tracking-widest uppercase border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
          style={{ borderColor: "var(--qgi-border)", color: "var(--qgi-text-muted)" }}
        >
          Countries
        </Link>
        <Link
          href="/risk-board"
          className="px-3 py-2 rounded text-[11px] tracking-widest uppercase border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
          style={{ borderColor: "var(--qgi-border)", color: "var(--qgi-text-muted)" }}
        >
          Risk Board
        </Link>
        <Link
          href="/patterns"
          className="px-3 py-2 rounded text-[11px] tracking-widest uppercase border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
          style={{ borderColor: "var(--qgi-border)", color: "var(--qgi-text-muted)" }}
        >
          Patterns
        </Link>
      </div>
    </div>
  );
}
