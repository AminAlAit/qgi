"use client";

/**
 * Light/dark toggle (2026-06-10). Understated per V4.1 — text-dim icon, no
 * border/fill, doesn't compete with the primary CTA. `variant="labeled"` adds a
 * short word for the expanded sidebar; `variant="icon"` is icon-only for the
 * top nav. suppressHydrationWarning covers the one-frame icon settle for users
 * who land in light mode (SSR renders the dark-default icon).
 */
import { Sun, Moon } from "lucide-react";
import { useTheme } from "@/lib/hooks/useTheme";

export function ThemeToggle({ variant = "icon" }: { variant?: "icon" | "labeled" }) {
  const { isDark, toggle } = useTheme();
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={!isDark}
      aria-label={label}
      title={label}
      suppressHydrationWarning
      className="inline-flex items-center gap-2 rounded p-1.5 transition-colors hover:bg-[var(--qgi-surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)]"
      style={{ color: "var(--qgi-text-muted)" }}
    >
      {isDark ? (
        <Sun size={16} strokeWidth={1.5} aria-hidden="true" />
      ) : (
        <Moon size={16} strokeWidth={1.5} aria-hidden="true" />
      )}
      {variant === "labeled" && (
        <span className="text-[10.5px] tracking-wider uppercase" suppressHydrationWarning>
          {isDark ? "Light" : "Dark"}
        </span>
      )}
    </button>
  );
}
