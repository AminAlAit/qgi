"use client";

import { useEffect, useRef, useState } from "react";
import { useSession, signOut } from "next-auth/react";
import Link from "next/link";
import type { Route } from "next";
import { LogOut, Settings, Sun, Moon } from "lucide-react";
import { useTheme } from "@/lib/hooks/useTheme";

/**
 * Top-right account menu for the authenticated app shell. Shows the user's
 * Google picture (or the first letter of their email as a fallback avatar);
 * clicking opens a short dropdown with the identity, a Settings entry point,
 * and Sign out.
 *
 * Rendered in app/(app)/layout.tsx as a fixed floating control so it sits above
 * page content on every gated page. Renders nothing while the session is
 * loading or when signed out (gated pages redirect signed-out users to /login
 * anyway, so on these pages a session is normally present).
 */
export function UserMenu() {
  const { data: session, status } = useSession();
  const { isDark, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (status === "loading") return null;
  const email = session?.user?.email ?? null;
  if (!email) return null;

  const image = session?.user?.image ?? null;
  const initial = email.trim().charAt(0).toUpperCase() || "?";
  const provider = session?.user?.provider;
  const providerLabel =
    provider === "google" ? "Signed in with Google" : "Signed in with email";

  return (
    <div ref={rootRef} className="fixed top-2.5 right-3 z-50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        title={email}
        className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-full border text-sm font-semibold transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--qgi-bg)]"
        style={{
          borderColor: "var(--qgi-border)",
          background: image ? "var(--qgi-surface)" : "var(--qgi-accent)",
          color: image ? "var(--qgi-text)" : "var(--qgi-bg)",
        }}
      >
        {image ? (
          // Plain <img> (not next/image) so no remote-domain config is needed;
          // falls back to the letter avatar if the Google image fails to load.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={image}
            alt=""
            referrerPolicy="no-referrer"
            className="h-full w-full object-cover"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <span aria-hidden="true">{initial}</span>
        )}
      </button>

      {open && (
        <>
          {/* Click-outside backdrop (transparent). */}
          <div
            className="fixed inset-0 z-40"
            aria-hidden="true"
            onClick={() => setOpen(false)}
          />
          <div
            role="menu"
            aria-label="Account"
            className="absolute right-0 z-50 mt-2 w-60 overflow-hidden rounded-lg border shadow-lg"
            style={{
              background: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            {/* Identity header */}
            <div className="flex items-center gap-3 px-3.5 py-3">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full text-sm font-semibold"
                style={{
                  background: image ? "var(--qgi-bg)" : "var(--qgi-accent)",
                  color: image ? "var(--qgi-text)" : "var(--qgi-bg)",
                }}
              >
                {image ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={image}
                    alt=""
                    referrerPolicy="no-referrer"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <span aria-hidden="true">{initial}</span>
                )}
              </span>
              <span className="min-w-0">
                <span
                  className="block truncate text-[13px] font-medium"
                  style={{ color: "var(--qgi-text)" }}
                  title={email}
                >
                  {email}
                </span>
                <span
                  className="block text-[11px]"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  {providerLabel}
                </span>
              </span>
            </div>

            <div style={{ height: 1, background: "var(--qgi-border)" }} />

            {/* Theme toggle — stays open so the change is visible in place. */}
            <button
              type="button"
              role="menuitem"
              onClick={() => toggle()}
              suppressHydrationWarning
              className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] transition-colors hover:bg-[var(--qgi-surface-2)] focus-visible:outline-none focus-visible:bg-[var(--qgi-surface-2)]"
              style={{
                color: "var(--qgi-text)",
                background: "transparent",
                border: "none",
                cursor: "pointer",
              }}
            >
              {isDark ? (
                <Sun size={15} strokeWidth={1.75} aria-hidden="true" />
              ) : (
                <Moon size={15} strokeWidth={1.75} aria-hidden="true" />
              )}
              <span suppressHydrationWarning>{isDark ? "Light mode" : "Dark mode"}</span>
            </button>

            <Link
              href={"/settings" as Route}
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-3.5 py-2.5 text-[13px] transition-colors hover:bg-[var(--qgi-surface-2)] focus-visible:outline-none focus-visible:bg-[var(--qgi-surface-2)]"
              style={{ color: "var(--qgi-text)" }}
            >
              <Settings size={15} strokeWidth={1.75} aria-hidden="true" />
              Settings
            </Link>

            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                signOut({ callbackUrl: "/" });
              }}
              className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] transition-colors hover:bg-[var(--qgi-surface-2)] focus-visible:outline-none focus-visible:bg-[var(--qgi-surface-2)]"
              style={{
                color: "var(--qgi-text)",
                background: "transparent",
                border: "none",
                cursor: "pointer",
              }}
            >
              <LogOut size={15} strokeWidth={1.75} aria-hidden="true" />
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
