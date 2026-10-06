import { Sidebar } from "@/components/nav/Sidebar";
import { PresentationWrapper } from "@/components/nav/PresentationWrapper";
import { TourProvider } from "@/components/tour/TourProvider";
import { UserMenu } from "@/components/auth/UserMenu";
import manifest from "@/data/te-fleet-run-2/MANIFEST.json";

/**
 * V4.1 §2 — one canonical vintage stamp per session. Lives in the sidebar
 * (below the "Take the tour" button) so every page sees it once and only
 * once. Sourced server-side from the current vintage MANIFEST (te-fleet-run-2)
 * so a new bake lifts the chip automatically; passed as a prop to the Sidebar
 * to keep the sidebar bundle from importing the heavy load.ts module.
 */
const dataVintage = (manifest as { produced_at_utc: string }).produced_at_utc;

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <PresentationWrapper>
      {/* T14 #307 HIGH fix (2026-04-19): overflow-x-hidden stops
          horizontal scroll bleed from the fixed-width sidebar at <768px
          until the full mobile hamburger redesign lands.
          T15 #308: skip-to-content anchor for keyboard/screen-reader users. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:px-3 focus:py-2 focus:bg-[var(--qgi-accent)] focus:text-[var(--qgi-bg)] focus:rounded"
      >
        Skip to content
      </a>
      <div className="flex h-full overflow-x-hidden">
        <Sidebar dataVintage={dataVintage} />
        {/* pt-14 on mobile reserves a clear gutter (~56px, ~10px below the
            fixed top-left hamburger button) so page chrome — breadcrumbs,
            eyebrows, the Briefing command bar wordmark — never renders under it
            on phones. Desktop (md+) shows the static sidebar and needs no offset.
            NOTE: the `md` breakpoint here must stay matched to the Sidebar
            hamburger's `md:hidden` (both 768px) — if that hamburger breakpoint
            ever changes, change this `md:pt-0` to match. This pt-14 only pushes
            NORMAL-FLOW content clear of the hamburger; any `position:fixed` /
            `position:sticky` element rendered inside a page must add its OWN
            top offset on mobile (≈ top: 56px below md) — the layout padding
            cannot move fixed/sticky descendants out from under the hamburger.
            `min-w-0` lets this flex child shrink below its content's intrinsic
            width, so internal horizontal-scroll containers (e.g. the risk-board
            and topic-board matrices' overflow-x:auto wrappers) actually scroll
            instead of forcing the column wider. */}
        <main
          id="main-content"
          className="flex-1 min-w-0 overflow-y-auto pt-14 md:pt-0"
          tabIndex={-1}
        >
          {children}
        </main>
      </div>
      {/* Top-right account menu (avatar → dropdown with Settings + Sign out).
          Fixed/floating so it sits above page content on every gated page. */}
      <UserMenu />
      {/* Tour-design 2026-05-18 — auto-fire on first visit (cookie-persisted),
          manual re-trigger from the sidebar "Take the tour" link. Content
          authored from 5-persona convergence. */}
      <TourProvider />
    </PresentationWrapper>
  );
}
