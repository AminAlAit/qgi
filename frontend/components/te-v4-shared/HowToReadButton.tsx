/**
 * HowToReadButton — ghost-chip button for the V4.1 page hero.
 *
 * Placed in the top-right of every V4.1 page hero, next to the vintage chip.
 * Opens a right-side HowToReadDrawer with page-aware 4-rule content.
 *
 * The button uses inline styles to stay consistent with the te-v4-shared
 * component pattern (no Tailwind, CSS modules, or external styling deps).
 */
"use client";

import { useState } from "react";
import { Info } from "lucide-react";
import { HowToReadDrawer } from "./HowToReadDrawer";
import { type RouteKey } from "@/lib/te-mock/how-to-read-content";

export interface HowToReadButtonProps {
  /** Which route's page-aware content to show in the drawer. */
  routeKey: RouteKey;
}

export function HowToReadButton({ routeKey }: HowToReadButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        data-tour="how-to-read-button"
        type="button"
        aria-label="How to read this page"
        onClick={() => setOpen(true)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          fontSize: "11.5px",
          padding: "5px 10px",
          border: "1px solid var(--qgi-border)",
          background: "var(--qgi-surface)",
          color: "var(--qgi-text-muted)",
          borderRadius: "4px",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
          cursor: "pointer",
          whiteSpace: "nowrap",
        }}
      >
        <Info size={12} strokeWidth={1.8} aria-hidden="true" />
        How to read this page
      </button>
      <HowToReadDrawer routeKey={routeKey} open={open} onClose={() => setOpen(false)} />
    </>
  );
}
