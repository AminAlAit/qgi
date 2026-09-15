/**
 * PairHandoffsFooter -- §7 Cross-family handoffs footer.
 *
 * Narrow strip:
 *   <- Back to Patterns V4 catalogue
 *   /countries/{a-iso}
 *   /countries/{b-iso}
 *   /trends
 *
 * Monospace 12px. No pair-to-pair links.
 */
import Link from "next/link";
import type { Route } from "next";

interface PairHandoffsFooterProps {
  countryA: string;
  countryB: string;
  iso2A: string;
  iso2B: string;
}

export function PairHandoffsFooter({
  countryA,
  countryB,
  iso2A,
  iso2B,
}: PairHandoffsFooterProps) {
  const linkStyle: React.CSSProperties = {
    color: "var(--qgi-accent)",
    textDecoration: "none",
    fontFamily: "ui-monospace, monospace",
    fontSize: "12px",
    letterSpacing: "0.2px",
  };

  const sepStyle: React.CSSProperties = {
    color: "var(--qgi-text-dim)",
    fontFamily: "ui-monospace, monospace",
    fontSize: "12px",
    userSelect: "none",
  };

  return (
    <footer
      data-tour="pair-handoffs"
      style={{
        marginTop: "32px",
        paddingTop: "16px",
        borderTop: "1px solid var(--qgi-border)",
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "8px 14px",
      }}
    >
      <Link href={"/patterns" as Route} style={linkStyle}>
        &larr; Back to Patterns catalogue
      </Link>
      <span style={sepStyle}>/</span>
      <Link href={`/countries/${iso2A}` as Route} style={linkStyle}>
        {countryA} profile
      </Link>
      <span style={sepStyle}>/</span>
      <Link href={`/countries/${iso2B}` as Route} style={linkStyle}>
        {countryB} profile
      </Link>
      <span style={sepStyle}>/</span>
      <Link href={"/trends" as Route} style={linkStyle}>
        Trends catalogue
      </Link>
    </footer>
  );
}
