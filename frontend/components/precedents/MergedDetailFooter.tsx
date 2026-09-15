import Link from "next/link";
import type { Route } from "next";

/**
 * Cross-family handoff footer for /precedents/[slug].
 *
 * Brief: docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-13.md
 *   section: "Cross-family handoffs"
 *
 * Renders BELOW the wrapped detail content (V1 PrecedentSlugClient or
 * V2 PrecedentsV2Detail). The wrapped components retain their own internal
 * cross-references; this footer adds the BRIEF-mandated cross-family links
 * that don't fit cleanly inside either existing component.
 *
 * PR-vii (2026-05-15) — sibling-link removal:
 *   Post-cutover, ML and STAT lineages share the same /precedents/{slug}
 *   URL; the page.tsx picks the template based on whether the slug is in
 *   the top-4 LOCKed set. The "sibling lineage" link from PR #2 was a
 *   pre-cutover artifact (it pointed at /precedents-v2b/{slug} for the
 *   STAT path and at /precedents/{slug} itself for the ML path — a
 *   circular self-link). Removed both. The lineage chip in the wrapped
 *   detail already communicates which lineage is rendering.
 */

export function MergedDetailFooter({ lineage }: { lineage: "ML" | "STAT" }) {
  return (
    <section
      className="max-w-3xl mx-auto px-6 lg:px-8 py-6 mt-4 border-t"
      style={{
        borderColor: "var(--qgi-border)",
      }}
      aria-label="Cross-family handoffs"
    >
      <div
        className="text-[10px] tracking-widest uppercase mb-3"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Related across QGI
      </div>
      <div className="flex flex-col gap-2 text-sm">
        <Link
          href={"/patterns?sort=loco_auc" as Route}
          className="hover:text-[var(--qgi-accent)] transition-colors"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          See related ranked patterns →
        </Link>
        <Link
          href={"/methodology" as Route}
          className="hover:text-[var(--qgi-accent)] transition-colors"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          How we validated this →
        </Link>
      </div>
      <p className="text-[10px] mt-4 font-data" style={{ color: "var(--qgi-text-dim)" }}>
        {lineage === "ML" ? "ML-adjudicated" : "Statistical screen"} lineage
      </p>
    </section>
  );
}
