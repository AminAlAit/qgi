"use client";

import { useState, useRef, useEffect, type CSSProperties, type ReactNode } from "react";

/**
 * ExplainTip — InfoTooltip's fixed-position tooltip card with an arbitrary
 * trigger (a chip, a pill, a badge) instead of the (i) circle.
 *
 * Born from the 2026-06-11 persona panel: every "dead ⓘ" complaint traced
 * to native `title` attributes, which only surface after a ~1s mouse idle
 * and never on click, touch, or keyboard. Wrap the trigger in this and the
 * same text becomes hover + click + Enter/Space + Escape accessible.
 *
 * Positioning reuses the #567 pattern: true `position: fixed` computed from
 * getBoundingClientRect, escaping every overflow-hidden ancestor.
 */
export function ExplainTip({
  text,
  children,
  style,
}: {
  text: string;
  children: ReactNode;
  /** Styles for the trigger wrapper (the visible chip/pill). */
  style?: CSSProperties;
}) {
  const [show, setShow] = useState(false);
  const [coords, setCoords] = useState<{
    top: number;
    left: number;
    flip?: boolean;
  } | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!show || !triggerRef.current) return;
    const update = () => {
      if (!triggerRef.current) return;
      const r = triggerRef.current.getBoundingClientRect();
      // Clamp to the viewport + flip below when near the top (QA panel).
      const half = 150;
      const left = Math.min(
        Math.max(r.left + r.width / 2, half + 8),
        window.innerWidth - half - 8
      );
      const flip = r.top < 120;
      setCoords({ top: flip ? r.bottom + 8 : r.top - 8, left, flip });
    };
    update();
    window.addEventListener("scroll", update, { capture: true, passive: true });
    window.addEventListener("resize", update, { passive: true });
    return () => {
      window.removeEventListener("scroll", update, { capture: true });
      window.removeEventListener("resize", update);
    };
  }, [show]);

  return (
    <span className="relative inline-block">
      <span
        ref={triggerRef}
        role="button"
        tabIndex={0}
        aria-label={text}
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onClick={(e) => {
          e.stopPropagation();
          setShow(!show);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            setShow(!show);
          }
          if (e.key === "Escape") setShow(false);
        }}
        style={{ cursor: "help", ...style }}
      >
        {children}
      </span>
      {show && coords && (
        <div
          role="tooltip"
          className="px-3 py-2 rounded-lg text-[11.5px] leading-relaxed w-72 max-w-[90vw] shadow-lg pointer-events-none"
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            transform: coords.flip ? "translate(-50%, 0)" : "translate(-50%, -100%)",
            zIndex: 9999,
            backgroundColor: "var(--qgi-surface-2)",
            color: "var(--qgi-text)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          {text}
        </div>
      )}
    </span>
  );
}
