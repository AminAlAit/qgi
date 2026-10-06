"use client";

import Link from "next/link";
import type { Route } from "next";
import { useEffect, useState } from "react";
import { ThemeToggle } from "@/components/ThemeToggle";

/**
 * Shared top nav for every public-marketing page (landing, /about, /reports,
 * /methodology, /blog, /legal). One nav vocabulary across the whole public
 * surface: Reports, Methodology, About, Blog, Contact, Open Dashboard.
 *
 * - currentPage highlights the active link in --qgi-accent.
 * - Contact points to /contact (the fill-in form), consistent from every
 *   page. (Previously a /#contact anchor on the old landing.)
 * - Mobile (<md): Reports + Blog + Contact collapse into a hamburger menu;
 *   Methodology + About + Open Dashboard remain visible (same pattern as
 *   the prior LandingHeaderNav).
 */

export type PublicPage = "reports" | "methodology" | "about" | "blog" | "legal" | null;

type PublicNavProps = {
  currentPage?: PublicPage;
};

export function PublicNav({ currentPage = null }: PublicNavProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const closeOnNav = () => setOpen(false);

  const baseClass =
    "text-[10px] sm:text-xs tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]";
  const colorFor = (page: PublicPage) =>
    page !== null && page === currentPage ? "var(--qgi-accent)" : "var(--qgi-text-muted)";

  // Top-nav order ratified by Sunita Krishnaswamy-Park (UX Research, IA)
  // consultation 2026-05-23: Reports → Blog → Methodology → About → Contact.
  // Reasoning: returning-analyst scan optimises for "what's new" (Reports +
  // Blog) before "how does it work" (Methodology) before "who is this"
  // (About). Contact is a utility endpoint adjacent to the CTA.
  return (
    <nav className="flex items-center gap-3 sm:gap-6 relative pl-4 lg:pl-8">
      <Link
        href={"/reports" as Route}
        className={`hidden md:inline-flex ${baseClass}`}
        style={{ color: colorFor("reports") }}
      >
        Reports
      </Link>
      <Link
        href={"/blog" as Route}
        className={`hidden md:inline-flex ${baseClass}`}
        style={{ color: colorFor("blog") }}
      >
        Blog
      </Link>
      <Link
        href={"/methodology" as Route}
        className={`hidden md:inline-flex ${baseClass}`}
        style={{ color: colorFor("methodology") }}
      >
        Methodology
      </Link>
      <Link
        href={"/about" as Route}
        className={`hidden md:inline-flex ${baseClass}`}
        style={{ color: colorFor("about") }}
      >
        About
      </Link>
      <Link
        href={"/contact" as Route}
        className={`hidden md:inline-flex ${baseClass}`}
        style={{ color: "var(--qgi-text-muted)" }}
      >
        Contact
      </Link>

      <ThemeToggle variant="icon" />

      <Link
        href={"/dashboard" as Route}
        className="inline-flex items-center justify-center min-h-[44px] text-[10px] sm:text-xs tracking-wider uppercase px-2 sm:px-4 py-1.5 sm:py-2 rounded transition-colors whitespace-nowrap"
        style={{
          backgroundColor: "var(--qgi-accent)",
          color: "var(--qgi-bg)",
        }}
      >
        {/* Single text node ("Open Dashboard") kept intact for the nav-label
            tests; phone compactness comes from the reduced px-2 / text-[10px]
            above rather than from shortening the words. */}
        Open Dashboard
      </Link>

      <button
        type="button"
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        aria-controls="public-mobile-menu"
        onClick={() => setOpen((o) => !o)}
        className="md:hidden inline-flex items-center justify-center w-10 h-10 rounded border transition-colors hover:bg-[var(--qgi-surface-2)] mr-1"
        style={{
          borderColor: "var(--qgi-border)",
          color: "var(--qgi-text-muted)",
        }}
      >
        {open ? (
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        ) : (
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="3" y1="6" x2="21" y2="6"></line>
            <line x1="3" y1="12" x2="21" y2="12"></line>
            <line x1="3" y1="18" x2="21" y2="18"></line>
          </svg>
        )}
      </button>

      {open && (
        <div
          id="public-mobile-menu"
          role="navigation"
          aria-label="Mobile menu"
          className="md:hidden absolute top-full right-0 mt-2 min-w-[180px] rounded border shadow-lg py-2 z-50"
          style={{
            backgroundColor: "var(--qgi-surface)",
            borderColor: "var(--qgi-border)",
          }}
        >
          {/* Mobile hamburger: full nav order — Reports → Blog → Methodology → About → Contact. */}
          <Link
            href={"/reports" as Route}
            onClick={closeOnNav}
            className="block px-4 py-3 text-sm tracking-wider uppercase transition-colors hover:bg-[var(--qgi-surface-2)]"
            style={{ color: colorFor("reports") }}
          >
            Reports
          </Link>
          <Link
            href={"/blog" as Route}
            onClick={closeOnNav}
            className="block px-4 py-3 text-sm tracking-wider uppercase transition-colors hover:bg-[var(--qgi-surface-2)]"
            style={{ color: colorFor("blog") }}
          >
            Blog
          </Link>
          <Link
            href={"/methodology" as Route}
            onClick={closeOnNav}
            className="block px-4 py-3 text-sm tracking-wider uppercase transition-colors hover:bg-[var(--qgi-surface-2)]"
            style={{ color: colorFor("methodology") }}
          >
            Methodology
          </Link>
          <Link
            href={"/about" as Route}
            onClick={closeOnNav}
            className="block px-4 py-3 text-sm tracking-wider uppercase transition-colors hover:bg-[var(--qgi-surface-2)]"
            style={{ color: colorFor("about") }}
          >
            About
          </Link>
          <Link
            href={"/contact" as Route}
            onClick={closeOnNav}
            className="block px-4 py-3 text-sm tracking-wider uppercase transition-colors hover:bg-[var(--qgi-surface-2)]"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            Contact
          </Link>
        </div>
      )}
    </nav>
  );
}
