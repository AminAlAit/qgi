/**
 * Canonical QG Intelligence wordmark component.
 *
 * Server-component-safe — no hooks, no context, no "use client".
 *
 * Three visual variants:
 *   "nav"    — 26px QG / 13px Intelligence. Used in landing header, sidebar
 *              expanded, blog navbars, /not-found, /about, /contact.
 *   "report" — 18px QG / 10px Intelligence. Used in all /reports/* standalone
 *              page navbars.
 *   "footer" — 14px QG / 10px Intelligence. Used in PublicFooter.
 *
 * When `href` is provided, the component wraps itself in a Next.js <Link>.
 * When omitted, it renders as a plain <span> (useful when an ancestor already
 * owns the navigation, e.g. the expanded-sidebar Link).
 *
 * Colors resolve to CSS custom properties so they flip automatically in light
 * mode via the site's theme tokens:
 *   --qgi-accent      → electric blue (#38bdf8 dark / #0284c7 light)
 *   --qgi-text-muted  → steel muted  (#9ab0c4 dark / #475569 light)
 *
 * Font stack: Century Gothic (Windows) → CenturyGothic (alt name) → URW Gothic
 * (Linux) → AppleGothic (macOS legacy) → ITC Avant Garde Gothic → Jost via
 * var(--font-qg-brand) (next/font/google, guaranteed delivery) → sans-serif.
 */

import Link from "next/link";
import type { Route } from "next";

const FONT_STACK =
  "'Century Gothic', 'CenturyGothic', 'URW Gothic', 'AppleGothic', " +
  "'ITC Avant Garde Gothic', var(--font-qg-brand), sans-serif";

export type WordmarkVariant = "nav" | "report" | "footer";

interface SizeSpec {
  qgSize: number;
  qgTracking: string;
  intSize: number;
  intTracking: string;
  gap: number;
  marginRight: string;
}

const SIZES: Record<WordmarkVariant, SizeSpec> = {
  nav: {
    qgSize: 26,
    qgTracking: "0.04em",
    intSize: 13,
    intTracking: "0.2em",
    gap: 6,
    marginRight: "-0.05em",
  },
  report: {
    qgSize: 18,
    qgTracking: "0.04em",
    intSize: 10,
    intTracking: "0.2em",
    gap: 4,
    marginRight: "-0.05em",
  },
  footer: {
    qgSize: 14,
    qgTracking: "0.12em",
    intSize: 10,
    intTracking: "0.15em",
    gap: 3,
    marginRight: "-0.04em",
  },
};

export interface WordmarkProps {
  /** Visual size preset. Default: "nav". */
  variant?: WordmarkVariant;
  /**
   * When provided, wraps the wordmark in a Next.js <Link> to this href.
   * When omitted, renders as a plain <span> wrapper (useful inside an
   * existing <Link> or heading).
   */
  href?: Route | string;
  /** Additional className on the outer wrapper. */
  className?: string;
  /** title attribute for the link (accessibility). Default: "QG Intelligence — Home". */
  title?: string;
}

export function Wordmark({
  variant = "nav",
  href,
  className = "",
  title = "QG Intelligence — Home",
}: WordmarkProps) {
  const s = SIZES[variant];

  const inner = (
    <>
      <span
        style={{
          fontFamily: FONT_STACK,
          fontSize: s.qgSize,
          fontWeight: 700,
          letterSpacing: s.qgTracking,
          lineHeight: 1,
          color: "var(--qgi-accent)",
          marginRight: s.marginRight,
          flexShrink: 0,
        }}
      >
        QG
      </span>
      <span
        style={{
          fontFamily: FONT_STACK,
          fontSize: s.intSize,
          fontWeight: 500,
          letterSpacing: s.intTracking,
          lineHeight: 1,
          color: "var(--qgi-text-muted)",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        Intelligence
      </span>
    </>
  );

  const wrapperStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "baseline",
    gap: s.gap,
    textDecoration: "none",
    flexShrink: 0,
  };

  if (href != null) {
    return (
      <Link href={href as Route} className={className} style={wrapperStyle} title={title}>
        {inner}
      </Link>
    );
  }

  return (
    <span className={className} style={wrapperStyle}>
      {inner}
    </span>
  );
}
