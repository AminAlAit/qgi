"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

/**
 * Presentation mode wrapper — activated by ?mode=presentation in URL.
 *
 * When active:
 * - Hides sidebar via CSS
 * - Increases base font size 25%
 * - Adds QGI watermark in corner
 * - Designed for screen recording (YouTube, X)
 */
function PresentationInner({ children }: { children: React.ReactNode }) {
  const searchParams = useSearchParams();
  const isPresentation = searchParams.get("mode") === "presentation";

  if (!isPresentation) {
    return <>{children}</>;
  }

  return (
    <div className="presentation-mode">
      <style>{`
        .presentation-mode {
          font-size: 125%;
          position: relative;
          height: 100%;
        }
        .presentation-mode aside {
          display: none !important;
        }
        .presentation-mode main {
          max-width: 100% !important;
        }
        /* Watermark */
        .presentation-mode::after {
          content: 'QG INTELLIGENCE';
          position: fixed;
          bottom: 12px;
          right: 16px;
          font-family: var(--font-geist-mono), monospace;
          font-size: 9px;
          letter-spacing: 0.25em;
          color: var(--qgi-text-dim);
          opacity: 0.5;
          pointer-events: none;
          z-index: 9999;
        }
      `}</style>
      {children}
    </div>
  );
}

export function PresentationWrapper({ children }: { children: React.ReactNode }) {
  // #435: previous fallback was `<>{children}</>` which caused the ENTIRE
  // page tree to render twice in the streamed HTML — once as the Suspense
  // fallback and once as the resolved body. Every client-component widget
  // appeared in `document.body` twice, which broke click-state testing
  // (two <TaxonomyL1Widget>s with independent useState meant the QA
  // agent's click landed on a sibling that wasn't being measured).
  //
  // `null` fallback is safe: useSearchParams() resolves on the first
  // client tick and presentation mode is an off-by-default URL param,
  // so the momentary empty wrapper isn't user-visible. The sidebar +
  // page content live inside `children`, not inside the fallback.
  return (
    <Suspense fallback={null}>
      <PresentationInner>{children}</PresentationInner>
    </Suspense>
  );
}
