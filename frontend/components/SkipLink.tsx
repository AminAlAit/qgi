/**
 * Visible-on-focus "Skip to content" anchor for WCAG 2.4.1 Bypass Blocks
 * (level A) compliance. Single source of truth for the skip-link pattern
 * used across every public-marketing page (landing, /about, /reports,
 * /methodology, /blog, /legal).
 *
 * Each public page renders <SkipLink /> as the first child of its root
 * wrapper, paired with a downstream <main id="main-content" tabIndex={-1}>
 * landmark that is the skip target.
 *
 * Extracted 2026-05-24 from inline duplicates noted in PR #155 review.
 */
export function SkipLink({ targetId = "main-content" }: { targetId?: string }) {
  return (
    <a
      href={`#${targetId}`}
      className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:px-3 focus:py-2 focus:bg-[var(--qgi-accent)] focus:text-[var(--qgi-bg)] focus:rounded"
    >
      Skip to content
    </a>
  );
}
