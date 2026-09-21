/**
 * RotatingWordmark — the landing hero wordmark.
 *
 * "Quantitative Geopolitical" in the QG-logo face (Century Gothic stack);
 * the third line cycles "Intelligence → Insights → Decisions → Foresight →
 * Clarity" on a timer with a soft crossfade. Client component (timer state).
 */
"use client";

import { useEffect, useState } from "react";

// The QG-logo face (matches the "QG" wordmark in the sidebar/nav).
const QG_FACE =
  "'Century Gothic', 'CenturyGothic', 'URW Gothic', 'AppleGothic', 'ITC Avant Garde Gothic', var(--font-qg-brand), sans-serif";

const WORDS = ["Intelligence", "Insights", "Decisions", "Foresight", "Clarity"];
const INTERVAL_MS = 2600;

export function RotatingWordmark() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((p) => (p + 1) % WORDS.length), INTERVAL_MS);
    return () => clearInterval(t);
  }, []);

  return (
    <h1
      style={{
        margin: 0,
        lineHeight: 1.04,
        letterSpacing: "-0.5px",
        fontWeight: 700,
        fontSize: "clamp(40px, 6.4vw, 76px)",
      }}
    >
      <style>{`
        @keyframes qgiWordIn {
          from { opacity: 0; transform: translateY(0.18em); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .qgi-rot-word { display: inline-block; animation: qgiWordIn 520ms ease-out both; }
      `}</style>
      <span style={{ fontFamily: QG_FACE, color: "var(--qgi-accent)" }}>
        Quantitative
      </span>
      <br />
      <span style={{ fontFamily: QG_FACE, color: "var(--qgi-accent)" }}>
        Geopolitical
      </span>
      <br />
      <span
        key={i}
        className="qgi-rot-word"
        style={{ color: "var(--qgi-text)" }}
        aria-live="polite"
      >
        {WORDS[i]}
      </span>
    </h1>
  );
}
