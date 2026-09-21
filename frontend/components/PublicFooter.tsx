import Link from "next/link";
import { Wordmark } from "@/components/brand/Wordmark";

/**
 * Shared footer for every public-marketing page (landing, /about, /reports,
 * /methodology, /blog, /legal). Mirror of PublicNav. One footer vocabulary
 * across the whole public surface so the bottom of every page anchors the
 * visitor to the same set of onward destinations.
 *
 * Footer link order ratified by Sunita Krishnaswamy-Park (IA consult
 * 2026-05-23): About → Methodology → Reports → Blog → Contact → Privacy → Terms.
 * (Privacy + Terms deep-link into the /legal page sections.)
 * Footer scroll-through skews toward "context-seeking" so brand items
 * come first, reversing the discovery-first order of the top nav.
 *
 * Contact links to /contact (the fill-in form) so the destination is
 * consistent regardless of which page the user clicks from.
 */
export function PublicFooter() {
  return (
    <footer
      className="border-t"
      style={{
        borderColor: "var(--qgi-border)",
        backgroundColor: "var(--qgi-surface)",
      }}
    >
      <div className="mx-auto max-w-6xl px-6 py-10">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6 mb-6">
          <Wordmark variant="footer" href="/" title="Home" />
          <nav
            aria-label="Footer"
            className="flex flex-wrap items-center gap-x-6 gap-y-2"
          >
            <Link
              href="/about"
              className="text-[11px] tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              About
            </Link>
            <Link
              href="/methodology"
              className="text-[11px] tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Methodology
            </Link>
            <Link
              href="/reports"
              className="text-[11px] tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Reports
            </Link>
            <Link
              href="/blog"
              className="text-[11px] tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Blog
            </Link>
            <Link
              href="/contact"
              className="text-[11px] tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Contact
            </Link>
            <Link
              href="/legal#privacy-policy"
              className="text-[11px] tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Privacy
            </Link>
            <Link
              href="/legal#terms-of-service"
              className="text-[11px] tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Terms
            </Link>
          </nav>
        </div>
        <div
          className="border-t pt-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          <span
            className="text-[10px] tracking-wider"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            &copy; 2026 QG Intelligence. All rights reserved.
          </span>
          <span
            className="text-[10px] tracking-wider uppercase"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Pattern Recurrence Intelligence
          </span>
        </div>
      </div>
    </footer>
  );
}
