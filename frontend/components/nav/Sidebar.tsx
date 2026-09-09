"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Route } from "next";
import {
  LayoutDashboard,
  ScrollText,
  Globe,
  Gauge,
  Columns2,
  Telescope,
  ShieldAlert,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import { Wordmark } from "@/components/brand/Wordmark";

// Navigation items.
// History:
// - 2026-04-13: Patterns→Precedents, Recipes→Signals (#121).
// - 2026-04-16: Dashboard renamed to BASE and promoted to the top slot (#248).
// - 2026-04-17: Unicode placeholder icons replaced with inline SVGs (#icon-redesign).
// - 2026-05-15: Flat 5-entry restructure (PR-i of resurfacing cutover).
// - 2026-05-28: V4.1 canonical promotion. TE Mockup group merged into the
//   top-level list as 9 standalone PRIMARY entries. All legacy entries
//   (Dashboard/Recipes/Countries/Signals/Patterns pointing at deleted routes)
//   removed. Inline SVG icon components removed; lucide-react used directly.
// - 2026-05-29: Collapsible sidebar (§10 UX rules). localStorage persistence,
//   smooth 220ms transition, icon-only collapsed mode with tooltips.

// ─────────────────────────────────────────────────────────────────────────────

// #440: `href: Route` so typed-routes pre-validates every nav target at
// build time. A typo in any internal route becomes a build failure instead
// of a silent runtime 404.

/** Nav badge type. PRIMARY = canonical post-cutover surface. */
type NavBadge = "LIVE" | "PREVIEW" | "PRIMARY";

interface NavItem {
  label: string;
  href: Route;
  badge: NavBadge;
  /** Optional per-item icon rendered next to the label inside a group. */
  icon?: React.ReactNode;
}

interface NavGroup {
  /** Group header label (sentence-case, never tracked uppercase). */
  label: string;
  icon: React.ReactNode;
  items: ReadonlyArray<NavItem>;
}

interface NavStandalone {
  type: "standalone";
  label: string;
  href: Route;
  icon: React.ReactNode;
  badge: NavBadge;
  /** When true, render a small "Coming soon" chip after the label so the
   *  user knows the destination is a locked preview before they click. */
  comingSoon?: boolean;
}

type NavEntry = NavGroup | NavStandalone;

/**
 * 2026-05-28 — V4.1 canonical promotion.
 *
 * The legacy 5-entry top-level list (Dashboard/Recipes/Countries/Signals/
 * Patterns pointing at deleted V3 routes) and the TE Mockup group (9 V4.1
 * routes behind a beaker section header) collapse into ONE flat list of
 * 9 PRIMARY canonical entries. Labels drop the "V4" / "V4.1" suffixes.
 * Icons: lucide-react throughout — no inline SVGs needed.
 */
const NAV_STRUCTURE: ReadonlyArray<NavEntry> = [
  {
    type: "standalone",
    label: "Briefing",
    href: "/dashboard",
    icon: <LayoutDashboard size={16} strokeWidth={1.5} aria-hidden="true" />,
    badge: "PRIMARY",
  },
  // Risk Board promoted to slot #2 (2026-05-29) per founder ratification.
  // Sits directly under Dashboard so the present-tense scan-pattern
  // ("who's hot right now") is the first user surface after the showroom.
  {
    type: "standalone",
    label: "Risk Board",
    href: "/risk-board",
    icon: <Gauge size={16} strokeWidth={1.5} aria-hidden="true" />,
    badge: "PRIMARY",
  },
  {
    type: "standalone",
    label: "Trends",
    href: "/trends",
    icon: <ScrollText size={16} strokeWidth={1.5} aria-hidden="true" />,
    badge: "PRIMARY",
  },
  {
    type: "standalone",
    label: "Countries",
    href: "/countries",
    icon: <Globe size={16} strokeWidth={1.5} aria-hidden="true" />,
    badge: "PRIMARY",
  },
  // Compound Risk entry removed 2026-05-30. The route was a polycrisis
  // leaderboard; the founder elected to take it down and revisit later
  // on different hypotheses (the Stats/ML trio paper at
  // docs/specs/internal/ops/te-fleet-run-1-... documents the rejuvenation
  // path: hand-tag recipe polarity, then ship as
  // 'Compound Negative-Event Density'). Components + data live on in
  // components/compound-risk/ + lib/te-mock/compound-risk-data.ts so
  // the rebuild starts from scaffolding, not from scratch.
  {
    type: "standalone",
    label: "Analogues",
    href: "/analogues",
    icon: <Telescope size={16} strokeWidth={1.5} aria-hidden="true" />,
    badge: "PRIMARY",
  },
  // Compare is bottom-slotted (2026-05-29) — it's the only locked surface,
  // and demoting it to the foot of the nav keeps the live surfaces dense
  // up top. comingSoon chip explains the lockdown without a separate click.
  {
    type: "standalone",
    label: "Compare",
    href: "/compare",
    icon: <Columns2 size={16} strokeWidth={1.5} aria-hidden="true" />,
    badge: "PRIMARY",
  },
  // Sanctions Simulator (2026-06-04) — Phase-0 teaser. Impact model in R&D;
  // ships as a coming-soon surface while the counterfactual work runs.
  // Slotted after Compare so both locked/R&D surfaces sit at the foot of the list.
  {
    type: "standalone",
    label: "Sanctions Simulator",
    href: "/sanctions-simulator",
    icon: <ShieldAlert size={16} strokeWidth={1.5} aria-hidden="true" />,
    badge: "PRIMARY",
  },
  // /recipe-tracker entry removed 2026-05-29 — the route itself was deleted
  // as part of the V4.1 round-3 amendment (2-bucket vocabulary). The catalog
  // ledger view is folded into /trends; the AUC column reborn as the per-
  // card "Confidence" badge. The status-board blog post is unaffected
  // (different route; /blog/trend-tracker since 2026-06-05).
];

/** Flatten the structure to the leaf-route list — used by the
 *  longest-prefix-wins active-state algorithm so a deep pathname like
 *  /trends/foreign_intervention highlights the right item. */
function collectNavItems(): NavItem[] {
  const all: NavItem[] = [];
  for (const entry of NAV_STRUCTURE) {
    if ("type" in entry) {
      all.push({ label: entry.label, href: entry.href, badge: entry.badge });
    } else {
      all.push(...entry.items);
    }
  }
  return all;
}

const FLAT_NAV_ITEMS = collectNavItems();

const STORAGE_KEY = "qgi-sidebar-collapsed";

/** Read the persisted collapsed state from localStorage without touching
 *  React state — safe to call only on the client (in useEffect / event
 *  handlers). Returns false (expanded) when the key is absent. */
function readStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function Sidebar({ dataVintage }: { dataVintage?: string }) {
  const pathname = usePathname();

  // T14 #307 HIGH fix (2026-04-19): mobile hamburger + off-canvas sidebar.
  // Desktop behavior is unchanged — sidebar is always visible at md+ via
  // static positioning. On <md viewports the sidebar slides in from the
  // left as a fixed overlay, with a backdrop that dismisses on click,
  // Escape closes, and body scroll-lock while open.
  const [mobileOpen, setMobileOpen] = useState(false);

  // Collapsible desktop sidebar (§10 UX rules, 2026-05-29).
  // Initialise to false (expanded) on the server — we'll sync from
  // localStorage on mount to avoid SSR hydration mismatch.
  const [collapsed, setCollapsed] = useState(false);
  // Track whether we've hydrated yet so SSR and first-paint agree on `false`.
  const hydrated = useRef(false);

  // Sync collapsed state from localStorage on mount (client-only).
  // Defer the setState past the current render via requestAnimationFrame —
  // the react-hooks/set-state-in-effect lint blocks the synchronous-in-effect
  // pattern, and the rAF call lets first paint settle before we flip state.
  useEffect(() => {
    hydrated.current = true;
    const stored = readStoredCollapsed();
    if (!stored) return;
    const raf = requestAnimationFrame(() => setCollapsed(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  // Auto-collapse the sidebar at viewport widths ≤ 900px (tablet portrait)
  // so the main content area gains back ~170px. Restores the user's stored
  // preference when the viewport expands again. Desktop-only: mobile uses
  // the hamburger overlay and is unaffected by this logic.
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const handler = (e: MediaQueryListEvent | MediaQueryList) => {
      if (e.matches) {
        setCollapsed(true);
      } else {
        // Restore stored pref on expand (may be collapsed by user choice).
        setCollapsed(readStoredCollapsed());
      }
    };
    // Run immediately for the current state.
    handler(mq);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // localStorage blocked (private browsing etc.) — in-memory only.
      }
      return next;
    });
  }

  // Close the drawer when the user taps a nav link. We used to do this
  // via a `useEffect(() => setMobileOpen(false), [pathname])` effect, but
  // react-hooks/set-state-in-effect flags the unconditional setState as
  // an anti-pattern (cascading renders). The event-handler path is the
  // React-preferred way to close a controlled UI surface on navigation.
  const closeOnNavigate = () => setMobileOpen(false);

  // Escape to dismiss mobile drawer.
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  // Keyboard shortcut: [ / ] toggles the collapsed state on desktop.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Skip when focus is inside an input / textarea to avoid hijacking typing.
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "[" || e.key === "]") {
        toggleCollapsed();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Lock background scroll while the mobile drawer is open.
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (mobileOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [mobileOpen]);

  return (
    <>
      {/* Mobile hamburger — only visible <md. Fixed top-left, above the
          drawer's own z-index so it's always tappable. */}
      <button
        type="button"
        aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
        aria-expanded={mobileOpen}
        aria-controls="qgi-sidebar-drawer"
        onClick={() => setMobileOpen((v) => !v)}
        className="md:hidden fixed top-3 left-3 z-[60] p-2 rounded border"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
          color: "var(--qgi-text-muted)",
        }}
      >
        {mobileOpen ? (
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path
              d="M3 3L13 13M13 3L3 13"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <line
              x1="2.5"
              y1="4"
              x2="13.5"
              y2="4"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
            <line
              x1="2.5"
              y1="8"
              x2="13.5"
              y2="8"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
            <line
              x1="2.5"
              y1="12"
              x2="13.5"
              y2="12"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
          </svg>
        )}
      </button>

      {/* Backdrop — only visible <md when drawer is open. */}
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation menu"
          tabIndex={-1}
          onClick={() => setMobileOpen(false)}
          className="md:hidden fixed inset-0 z-40 bg-black/60 animate-in fade-in duration-150"
        />
      )}

      {/* PR-vii (2026-05-15) — aria-label="Site navigation" on the
          landmark wrapper. Pointer-events guard during the slide-in
          transition prevents a click on the hamburger from passing
          through to the link beneath while the drawer is translating
          in (was navigating users to /trends on mobile tap).

          2026-05-29 — collapsible desktop sidebar (§10). The aside uses a
          CSS transition on `width` (220ms ease-in-out). The `data-collapsed`
          attribute drives the width via inline style so we can interpolate
          precisely. `overflow-hidden` on the aside clips text as it shrinks.
          The main column is flex-1 — it absorbs the freed width automatically
          with no JS needed on the layout side (Approach A). */}
      <aside
        id="qgi-sidebar-drawer"
        aria-label="Site navigation"
        data-collapsed={collapsed ? "true" : "false"}
        className={`flex flex-col shrink-0 border-r fixed md:static inset-y-0 left-0 z-50 transition-transform duration-200 md:translate-x-0 overflow-hidden ${
          mobileOpen
            ? "translate-x-0 pointer-events-auto"
            : "-translate-x-full md:translate-x-0 pointer-events-none md:pointer-events-auto"
        }`}
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
          // Width transition: 240px expanded → 56px collapsed.
          // Only animate on md+; on mobile the drawer is full-height overlay
          // and width is irrelevant (it's always 224px / w-56).
          width: collapsed ? "56px" : "224px",
          transition: "width 220ms ease-in-out",
          // On mobile, restore the w-56 fixed width regardless of collapsed
          // state. The collapse feature is desktop-only.
        }}
      >
        {/* Wordmark row — QG (always visible) + Intelligence (hides when
            collapsed). The toggle button sits to the right of the wordmark
            area and is always visible on desktop.

            On collapsed, the Link only shows "QG" (overflow-hidden clips
            the rest). The toggle sits at the right of the header row. */}
        <div
          className="flex items-center border-b"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          {collapsed ? (
            /* Collapsed: only the "QG" wordmark shows. Hovering it swaps the
               wordmark for an expand icon in place; clicking expands the nav.
               No separate toggle button in the collapsed rail. */
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-label="Expand sidebar"
              aria-expanded={false}
              title="Expand sidebar  ( [ or ] )"
              className="group relative flex items-center justify-center w-full px-5 py-6 transition-colors hover:bg-[var(--qgi-surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)]"
            >
              <span
                className="transition-opacity duration-150 group-hover:opacity-0"
                style={{
                  fontSize: "26px",
                  lineHeight: 1,
                  letterSpacing: "0.04em",
                  color: "var(--qgi-accent)",
                  fontFamily:
                    "'Century Gothic', 'CenturyGothic', 'URW Gothic', 'AppleGothic', 'ITC Avant Garde Gothic', var(--font-qg-brand), sans-serif",
                  fontWeight: 700,
                }}
              >
                QG
              </span>
              {/* Expand icon — revealed in place of "QG" on hover/focus. */}
              <span
                aria-hidden="true"
                className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-150 group-hover:opacity-100"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                <PanelLeft size={18} strokeWidth={1.5} />
              </span>
            </button>
          ) : (
            <>
              <Link
                href="/dashboard"
                onClick={closeOnNavigate}
                className="flex items-center px-5 py-6 transition-colors hover:bg-[var(--qgi-surface-2)] min-w-0 flex-1 overflow-hidden"
                title="Go to Briefing (command center)"
              >
                <Wordmark variant="nav" />
              </Link>

              {/* Desktop-only collapse toggle (expanded state). Hidden on mobile
                  (the hamburger handles mobile open/close). */}
              <button
                type="button"
                aria-label="Collapse sidebar"
                aria-expanded={true}
                onClick={toggleCollapsed}
                title="Collapse sidebar  ( [ or ] )"
                className="hidden md:flex items-center justify-center shrink-0 p-2 mr-2 rounded transition-colors hover:bg-[var(--qgi-surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                <PanelLeftClose size={15} strokeWidth={1.5} aria-hidden="true" />
              </button>
            </>
          )}
        </div>

        {/* Navigation
          GH#250: longest-prefix-wins active state. Without this, RECIPE-TRACKER
          (/recipe-tracker) could mis-activate RECIPES (/trends) because a naive
          startsWith() would match both. `isActiveRoute` picks the deepest leaf
          href that the current pathname matches.
          2026-05-28: all 9 entries are standalone; NavGroupSection is still
          supported by the renderer for future use but not currently in the
          structure. */}
        <nav
          aria-label="Main navigation"
          className="flex flex-col gap-3 px-2 pt-4 flex-1 overflow-y-auto overflow-x-hidden"
        >
          {NAV_STRUCTURE.map((entry) => {
            if ("type" in entry) {
              return (
                <NavLeafLink
                  key={entry.href}
                  label={entry.label}
                  href={entry.href}
                  icon={entry.icon}
                  badge={entry.badge}
                  comingSoon={entry.comingSoon}
                  pathname={pathname}
                  onClick={closeOnNavigate}
                  collapsed={collapsed}
                />
              );
            }
            return (
              <NavGroupSection
                key={entry.label}
                group={entry}
                pathname={pathname}
                onLinkClick={closeOnNavigate}
              />
            );
          })}
        </nav>

        {/* Theme toggle + sign-out moved to the top-right account menu
            (components/auth/UserMenu.tsx) — the sidebar no longer carries them. */}

        {/* Tour re-trigger button. Hides gracefully when collapsed
            (overflow-hidden clips it; the icon-only mode has no space). */}
        {!collapsed && (
          <button
            type="button"
            onClick={() => {
              if (typeof window === "undefined") return;
              window.localStorage.setItem("qgi-tour-launch", "manual");
              window.location.reload();
            }}
            className="mx-3 mb-2 mt-1 px-3 py-2 rounded text-[10.5px] tracking-widest uppercase font-semibold border transition-colors text-left cursor-pointer hover:border-[var(--qgi-accent)] hover:text-[var(--qgi-text)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
              backgroundColor: "transparent",
            }}
          >
            ✨ Take the tour
          </button>
        )}

        {/* V4.1 §2 — one canonical "Data Last Updated" stamp per session.
            Lives directly below "Take the tour" so every page sees it once
            and only once. Hides when sidebar collapses (the chip wouldn't
            fit in the 56px rail and the date is already on the user's
            mental model once they've seen it).

            Round-3.4 (2026-05-29): two-line layout — "Data Last Updated"
            on top, YYYY-MM on the bottom. The day is dropped from the
            display because the audience scans by month, not by day; the
            granularity matches how the bake actually cadences (weekly→
            monthly). */}
        {!collapsed && dataVintage && (
          <div
            className="mx-3 mb-3 px-3 py-1.5 text-[10.5px] tracking-[0.1em] uppercase font-medium leading-[1.35]"
            style={{
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            <div>Data Last Updated</div>
            <div>{dataVintage.slice(0, 7)}</div>
          </div>
        )}

        {/* Footer — shows text when expanded; hides when collapsed. */}
        {!collapsed && (
          <div
            className="px-5 py-3 border-t text-[10.5px] tracking-wider shrink-0"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-dim)",
              overflow: "hidden",
              lineHeight: 1.3,
            }}
          >
            QUANTITATIVE
            <br />
            GEOPOLITICAL
            <br />
            INTELLIGENCE
          </div>
        )}
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Longest-prefix-wins active-state check (per-leaf, group-unaware). */
function isActiveRoute(pathname: string, href: Route): boolean {
  if (pathname === href) return true;
  if (!pathname.startsWith(href + "/")) return false;
  // A deeper leaf in the same family wins (e.g. /trends/foreign_intervention
  // outranks /trends when the user is on a recipe detail page).
  return !FLAT_NAV_ITEMS.some(
    (other) =>
      other.href !== href &&
      other.href.length > href.length &&
      (pathname === other.href || pathname.startsWith(other.href + "/"))
  );
}

/** Top-level nav link (icon + label). Used for all 9 canonical entries.
 *  When `collapsed=true` the label is hidden and a native `title` tooltip
 *  carries the accessible label. */
function NavLeafLink({
  label,
  href,
  icon,
  pathname,
  onClick,
  collapsed,
  comingSoon,
}: {
  label: string;
  href: Route;
  icon: React.ReactNode;
  badge: NavBadge;
  pathname: string;
  onClick: () => void;
  collapsed: boolean;
  comingSoon?: boolean;
}) {
  const active = isActiveRoute(pathname, href);
  // Long labels (>14 chars) get a smaller, tighter font so they sit on ONE
  // line in the 224px rail instead of wrapping. Short labels keep the
  // standard 12px tracking-widest treatment.
  const isLongLabel = label.length > 14;
  return (
    <Link
      href={href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? `${label}${comingSoon ? " (coming soon)" : ""}` : undefined}
      title={collapsed ? `${label}${comingSoon ? ": Coming soon" : ""}` : undefined}
      className="flex items-center gap-2.5 px-3 py-2.5 rounded text-xs tracking-widest transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--qgi-surface)]"
      style={{
        color: active ? "var(--qgi-accent)" : "var(--qgi-text-muted)",
        backgroundColor: active ? "var(--qgi-accent-glow)" : "transparent",
        // Centre the icon when collapsed; left-align when expanded.
        justifyContent: collapsed ? "center" : "flex-start",
        paddingLeft: collapsed ? "0" : undefined,
        paddingRight: collapsed ? "0" : undefined,
      }}
    >
      <span className="flex items-center justify-center w-4 h-4 shrink-0">{icon}</span>
      {/* Label — rendered ONLY when expanded, so it consumes no row width when
          collapsed and the icon centers cleanly in the rail. */}
      {!collapsed && (
        <span
          className="flex-1 uppercase overflow-hidden"
          style={{
            whiteSpace: "nowrap",
            lineHeight: 1.3,
            ...(isLongLabel ? { fontSize: "11px", letterSpacing: "0" } : {}),
          }}
        >
          {label}
        </span>
      )}
      {/* "Coming soon" chip — kept to the RIGHT of the label, only when flagged
          AND expanded. Rendered on two lines ("coming" / "soon") so the chip
          stays narrow and leaves the label its full width. Calm slate-dim. */}
      {comingSoon && !collapsed && (
        <span
          aria-hidden="true"
          className="shrink-0 text-center px-1 py-0.5 rounded text-[9px] font-semibold normal-case"
          style={{
            color: "var(--qgi-text-dim)",
            border: "1px solid var(--qgi-border)",
            background: "var(--qgi-bg)",
            letterSpacing: "0.5px",
            lineHeight: 1.15,
          }}
        >
          coming
          <br />
          soon
        </span>
      )}
    </Link>
  );
}

/** Family section header + child links. Non-collapsible — clean visual
 *  grouping without state cost. Kept for future use; not in current
 *  NAV_STRUCTURE after the V4.1 canonical promotion. */
function NavGroupSection({
  group,
  pathname,
  onLinkClick,
}: {
  group: NavGroup;
  pathname: string;
  onLinkClick: () => void;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      {/* Group header — small uppercase tracked, dim. Icon at left. */}
      <div
        className="flex items-center gap-3 px-3 py-1.5"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        <span className="flex items-center justify-center w-4 h-4 shrink-0">
          {group.icon}
        </span>
        <span className="text-[10px] tracking-widest uppercase font-semibold">
          {group.label}
        </span>
      </div>
      {/* Indented item rows — per-item icon rendered when present. */}
      <div className="flex flex-col gap-0.5">
        {group.items.map((item) => {
          const active = isActiveRoute(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onLinkClick}
              className="flex items-center gap-2 pl-10 pr-3 py-1.5 rounded text-xs tracking-wide transition-colors"
              style={{
                color: active ? "var(--qgi-accent)" : "var(--qgi-text-muted)",
                backgroundColor: active ? "var(--qgi-accent-glow)" : "transparent",
              }}
            >
              {item.icon && (
                <span className="flex items-center justify-center w-[14px] h-[14px] shrink-0">
                  {item.icon}
                </span>
              )}
              <span className="flex-1 truncate">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
