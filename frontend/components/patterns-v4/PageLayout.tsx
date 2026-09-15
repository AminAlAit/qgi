/**
 * PageLayout — wrapper for /patterns main page.
 *
 * No L1 accent border, no recipe icon. Pairs are family-agnostic.
 * Standard V4.1 chrome: max-width 1280px, 24px padding.
 */
import type { ReactNode } from "react";

export function PageLayout({ children }: { children: ReactNode }) {
  return (
    <div
      style={{ minHeight: "100%", background: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "24px" }}>
        {children}
      </div>
    </div>
  );
}
