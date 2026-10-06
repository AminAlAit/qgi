/**
 * HowToReadDrawer — right-side slide-in drawer (420px) for the
 * "How to read this page" pattern.
 *
 * Opened by HowToReadButton. Displays the page-aware 4-rule content from
 * HOW_TO_READ_CONTENT keyed by routeKey.
 *
 * Behavior:
 * - ESC closes
 * - Click on the backdrop closes
 * - Body scroll is locked while open
 * - No internal "Next / OK" buttons — reader dismisses when done
 *
 * Animation (2026-05-28): the drawer slides in from the right over 500ms
 * and slides out symmetrically. To support BOTH directions cleanly we keep
 * the drawer mounted for the full close-transition before unmounting:
 *
 *   open=true  → mount → next-frame visible=true  → transform animates in
 *   open=false → visible=false → transform animates out → wait 500ms → unmount
 *
 * The backdrop is a <button> (not a <div>) so keyboard users can dismiss
 * without hunting for the close button. Its label makes the intent clear.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { HOW_TO_READ_CONTENT, type RouteKey } from "@/lib/te-mock/how-to-read-content";

const CALM_SLATE_BLUE = "#5B7E99";
const ANIM_MS = 500;
const EASING = "cubic-bezier(0.16, 1, 0.3, 1)";

export interface HowToReadDrawerProps {
  routeKey: RouteKey;
  open: boolean;
  onClose: () => void;
}

export function HowToReadDrawer({ routeKey, open, onClose }: HowToReadDrawerProps) {
  // `mounted` tracks whether the DOM is present. `visible` drives the
  // transform/opacity transition. Two-stage so we can animate in (mount,
  // then next-frame flip visible to trigger CSS transition) AND animate
  // out (flip visible off, wait for transition, then unmount).
  //
  // All state mutations happen inside async callbacks (requestAnimationFrame
  // + setTimeout) rather than synchronously in the effect body. The
  // react-hooks/set-state-in-effect rule blocks synchronous setState in
  // effects (cascading renders); async-callback updates are the supported
  // escape hatch for animation orchestration.
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  // Mutable handle so the open-branch cleanup can cancel whichever rAF is
  // currently in flight (id1 mounts, id2 flips visible).
  const cancelRef = useRef<number | null>(null);

  useEffect(() => {
    if (open) {
      // Two rAFs: first frame mounts the DOM with translateX(100%); second
      // frame flips visible=true so the CSS transition runs. Without the
      // double-rAF React batches both updates and the transition is skipped.
      const id1 = requestAnimationFrame(() => {
        setMounted(true);
        const id2 = requestAnimationFrame(() => setVisible(true));
        // Stash id2 on the outer cancel so cleanup can cancel either step.
        cancelRef.current = id2;
      });
      cancelRef.current = id1;
      return () => {
        if (cancelRef.current !== null) cancelAnimationFrame(cancelRef.current);
        cancelRef.current = null;
      };
    }
    // Closing: rAF the visible=false flip (lets the browser paint
    // translateX(100%)), then unmount after the transition duration.
    const id1 = requestAnimationFrame(() => setVisible(false));
    const id2 = window.setTimeout(() => setMounted(false), ANIM_MS);
    return () => {
      cancelAnimationFrame(id1);
      window.clearTimeout(id2);
    };
  }, [open]);

  // ESC to close + body scroll-lock while the drawer is open. Keyed off
  // `open` so closing via outside-click or ESC immediately unlocks scroll
  // even though the unmount waits 500ms.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  // Shift the main content area right when the drawer is open so it doesn't
  // hide behind the panel. We apply padding-right on #main-content directly
  // (the flex-1 scrolling container in AppLayout) via a CSS transition so
  // the page feels like it's making room rather than being covered.
  useEffect(() => {
    const mainEl = document.getElementById("main-content");
    if (!mainEl) return;
    const drawerWidth = Math.min(420, window.innerWidth - 56);
    if (open) {
      mainEl.style.transition = `padding-right ${ANIM_MS}ms ${EASING}`;
      mainEl.style.paddingRight = `${drawerWidth}px`;
    } else {
      mainEl.style.transition = `padding-right ${ANIM_MS}ms ${EASING}`;
      mainEl.style.paddingRight = "";
    }
    return () => {
      mainEl.style.paddingRight = "";
      mainEl.style.transition = "";
    };
  }, [open]);

  if (!mounted) return null;

  const content = HOW_TO_READ_CONTENT[routeKey];

  return (
    <>
      {/* Backdrop — focusable so keyboard users can dismiss without the X.
          Fades in/out with the drawer. */}
      <button
        type="button"
        aria-label="Close how-to-read drawer"
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.5)",
          zIndex: 40,
          border: "none",
          padding: 0,
          cursor: "default",
          opacity: visible ? 1 : 0,
          pointerEvents: visible ? "auto" : "none",
          transition: `opacity ${ANIM_MS}ms ${EASING}`,
        }}
      />

      {/* Drawer — slides in from the right over 500ms */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="howtoread-title"
        aria-hidden={!visible}
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          width: "min(420px, calc(100vw - 56px))",
          background: "var(--qgi-surface)",
          borderLeft: `3px solid ${CALM_SLATE_BLUE}`,
          padding: "24px 24px 32px",
          overflowY: "auto",
          zIndex: 50,
          boxShadow: "-8px 0 24px rgba(0,0,0,0.3)",
          transform: visible ? "translateX(0)" : "translateX(100%)",
          transition: `transform ${ANIM_MS}ms ${EASING}`,
          willChange: "transform",
        }}
      >
        {/* Header */}
        <header
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginBottom: "8px",
          }}
        >
          <h2
            id="howtoread-title"
            style={{
              fontSize: "15px",
              fontWeight: 600,
              color: CALM_SLATE_BLUE,
              margin: 0,
            }}
          >
            How to read this page
          </h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--qgi-text-muted)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "2px",
            }}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        {/* Lede */}
        <p
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-muted)",
            margin: "0 0 18px",
            lineHeight: 1.5,
          }}
        >
          {content.lede}
        </p>

        {/* 4 rules */}
        <ol
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "14px",
          }}
        >
          {content.rules.map((rule, i) => (
            <li key={i} style={{ paddingLeft: "32px", position: "relative" }}>
              <span
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  width: "22px",
                  height: "22px",
                  borderRadius: "11px",
                  background: `${CALM_SLATE_BLUE}1A`,
                  color: CALM_SLATE_BLUE,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "10px",
                  fontWeight: 600,
                }}
              >
                {i + 1}
              </span>
              <div
                style={{
                  fontSize: "13px",
                  fontWeight: 600,
                  color: "var(--qgi-text)",
                  marginBottom: "3px",
                }}
              >
                {rule.title}
              </div>
              <div
                style={{
                  fontSize: "12px",
                  color: "var(--qgi-text-muted)",
                  lineHeight: 1.55,
                }}
              >
                {rule.body}
              </div>
            </li>
          ))}
        </ol>
      </aside>
    </>
  );
}
