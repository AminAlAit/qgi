"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";
import type { EventData, Step } from "react-joyride";
import { TOUR_STEPS, type QgiTourStep } from "@/lib/tour-steps";

/**
 * QGI in-product tour provider.
 *
 * Wired in at `app/(app)/layout.tsx` so every authenticated route gets the
 * tour. Behavior:
 *   - **Auto-fire** on first authenticated visit (cookie-persisted dismiss).
 *   - **Manual re-trigger** via the "Take the tour" sidebar link, which sets
 *     `localStorage['qgi-tour-launch'] = 'manual'` and reloads the page.
 *   - **Per-route segmentation** — Joyride drives only the steps whose
 *     `page` matches the current pathname. Navigating to another route while
 *     the tour is active picks up the next segment cleanly.
 *
 * Tour content authored from the 5-persona convergence walkthrough
 * (2026-05-18). See `docs/specs/internal/testing/tour-design/`.
 *
 * Dynamically imported with `ssr: false` because react-joyride uses the
 * DOM API at module load — must not run during the server-render pass.
 */
// react-joyride v3 ships a named export, not a default. We dynamic-import
// with ssr:false so the DOM-touching module never executes during SSR.
const Joyride = dynamic(() => import("react-joyride").then((m) => m.Joyride), {
  ssr: false,
});

const COOKIE_NAME = "qgi-tour-dismissed";
const COOKIE_VALUE = "1";
const COOKIE_MAX_AGE_DAYS = 365;

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&") + "=([^;]*)")
  );
  return match ? decodeURIComponent(match[1]) : null;
}

function writeCookie(name: string, value: string, maxAgeDays: number): void {
  if (typeof document === "undefined") return;
  const expires = new Date();
  expires.setDate(expires.getDate() + maxAgeDays);
  document.cookie =
    `${name}=${encodeURIComponent(value)}; expires=${expires.toUTCString()}; ` +
    `path=/; samesite=lax`;
}

export function TourProvider() {
  const pathname = usePathname();
  const [run, setRun] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);

  // Steps for the current page only — Joyride's `steps` array drives a
  // single page's segment at a time.
  const pageSteps: Step[] = useMemo(() => {
    return TOUR_STEPS.filter((s: QgiTourStep) => s.page === pathname);
  }, [pathname]);

  // Decide whether to run the tour on first mount or navigation:
  //   1. Manual trigger from sidebar link → always run, regardless of cookie.
  //   2. Auto-fire on first visit only if (a) cookie absent AND (b) current
  //      page has tour steps.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const manualLaunch = window.localStorage.getItem("qgi-tour-launch") === "manual";
    if (manualLaunch) {
      window.localStorage.removeItem("qgi-tour-launch");
      // QA review F2: zero-step routes (e.g., /blog/foo) silently
      // failed before — clicking "Take the tour" set run=true but the
      // early-return at the bottom of the function meant Joyride never
      // rendered. Guard here so the state stays consistent.
      if (pageSteps.length === 0) return;
      // Defer state updates by a tick so we don't trigger a cascading
      // render inside the effect body (react-hooks/set-state-in-effect).
      const t = window.setTimeout(() => {
        setRun(true);
        setStepIndex(0);
      }, 0);
      return () => window.clearTimeout(t);
    }
    const dismissed = readCookie(COOKIE_NAME) === COOKIE_VALUE;
    if (dismissed) return;
    if (pageSteps.length === 0) return;
    // Don't AUTO-fire the tour on phone/tablet: Joyride anchors its popovers
    // over the dense hero/cards and the tooltip ends up overlapping the very
    // surface it describes on narrow viewports (#26/#37). The tour stays fully
    // available at any width via the sidebar "Take the tour" link (manual
    // launch above is unaffected by this guard). Boundary is inclusive so
    // iPad landscape (exactly 1024px) does not auto-fire either.
    if (window.innerWidth <= 1024) return;
    // Small delay so the page hydrates before Joyride tries to anchor.
    const t = window.setTimeout(() => {
      setRun(true);
      setStepIndex(0);
    }, 600);
    return () => window.clearTimeout(t);
  }, [pathname, pageSteps.length]);

  const handleCallback = useCallback((data: EventData) => {
    const { status, type, action, index } = data;
    // Joyride status constants are string literals; use them directly to
    // avoid pulling in the STATUS object at runtime.
    if (status === "finished" || status === "skipped") {
      writeCookie(COOKIE_NAME, COOKIE_VALUE, COOKIE_MAX_AGE_DAYS);
      setRun(false);
      setStepIndex(0);
      return;
    }
    // Closing the popover via the X button or Esc.
    if (action === "close" && (type === "step:after" || type === "tour:end")) {
      writeCookie(COOKIE_NAME, COOKIE_VALUE, COOKIE_MAX_AGE_DAYS);
      setRun(false);
      setStepIndex(0);
      return;
    }
    // Standard prev/next progression.
    if (type === "step:after") {
      setStepIndex(index + (action === "prev" ? -1 : 1));
    }
  }, []);

  if (pageSteps.length === 0) return null;
  // QA sweep 2026-06-11: with run=false Joyride stays mounted and its portal
  // (#react-joyride-portal + spotlight SVG) lingers in the DOM intercepting
  // pointer events over its bounding rect — dead clicks on the legend and
  // quadrant after dismissing the tour. Unmount it entirely when idle.
  if (!run) return null;

  return (
    <Joyride
      steps={pageSteps}
      run={run}
      stepIndex={stepIndex}
      continuous
      onEvent={handleCallback}
      locale={{
        back: "Back",
        close: "Close",
        last: "Done",
        next: "Next",
        skip: "Skip tour",
      }}
      // v3 — per-step defaults live in `options`. Colors, button visibility,
      // skip/progress flags moved here from the v2 top-level props.
      // QA review F1: v3's default `buttons` array omits 'skip'; without
      // it the locale.skip entry is dead and `status === "skipped"` is
      // unreachable. Re-add 'skip' so users have an escape hatch besides
      // the X close (per the convergence spec's intent).
      options={{
        arrowColor: "var(--qgi-surface)",
        backgroundColor: "var(--qgi-surface)",
        overlayColor: "rgba(0, 0, 0, 0.55)",
        primaryColor: "var(--qgi-accent)",
        textColor: "var(--qgi-text)",
        zIndex: 9999,
        showProgress: true,
        buttons: ["back", "skip", "close", "primary"],
      }}
      styles={{
        tooltip: {
          fontSize: "0.875rem",
          borderRadius: 8,
        },
        buttonPrimary: {
          fontSize: "0.8rem",
          borderRadius: 6,
        },
        buttonBack: {
          fontSize: "0.8rem",
        },
      }}
    />
  );
}
