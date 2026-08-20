// Lighthouse CI config (#441 Part A).
//
// Audits a handful of high-traffic public routes against four budgets:
// performance, accessibility, SEO, best-practices. Tuned to the bar QGI's
// own QA sweep on 2026-04-24 was implicitly applying — the goal is to
// catch regressions like:
//
//   - missing <h1>          (accessibility)
//   - 404'd og-default.png  (SEO)
//   - <meta description> drift  (SEO)
//   - LCP/TTI regressions   (performance)
//
// Hard error thresholds; warn-only categories noted below.
//
// Local: `npm run lhci` (after `npm run build && npm run start &`)
// CI:    `.github/workflows/lighthouse.yml`

module.exports = {
  ci: {
    collect: {
      // Routes audited on every CI run. Keep this list short — every URL
      // here doubles the workflow runtime. Add new routes only when
      // they become a public landing surface.
      url: [
        "http://localhost:3000/",
        "http://localhost:3000/countries",
        "http://localhost:3000/methodology",
        "http://localhost:3000/about",
        "http://localhost:3000/blog",
      ],
      // 3 runs per URL; LHCI takes the median to absorb cold-start noise.
      numberOfRuns: 3,
      settings: {
        // The default LHCI throttling is 4× CPU + slow 4G. That's correct
        // for surfacing perf regressions but produces failed runs on
        // GitHub-hosted runners under occasional load. Use "desktop"
        // form factor + provided throttling so budgets are stable and
        // tuned to what users actually see (we ship via Vercel + CDN, so
        // mid-tier desktop is the realistic delivery profile).
        preset: "desktop",
        // Skip the PWA category — we ship a manifest but aren't building
        // a service worker; LHCI's PWA audits add noise without signal.
        skipAudits: ["uses-http2"],
      },
    },
    assert: {
      assertions: {
        // Performance budget: 0.85 = "Good" Lighthouse band. Warn rather
        // than error so a single noisy run doesn't block a merge — the
        // "warn" surfaces in the PR comment and a sustained drop trips
        // a follow-up review.
        "categories:performance": ["warn", { minScore: 0.85 }],
        // Accessibility is non-negotiable — error on regression. Threshold
        // 0.9 leaves headroom for legitimate aria-*-related warnings while
        // catching missing-h1 / missing-alt class bugs.
        "categories:accessibility": ["error", { minScore: 0.9 }],
        // SEO catches the og-default.png 404 + meta description drift +
        // canonical-tag breakage — every regression today's QA caught
        // would trip this.
        "categories:seo": ["error", { minScore: 0.9 }],
        // Best practices: warn (not error). The audit dings third-party
        // libraries we don't control (Vercel, NextAuth callbacks) and
        // produces noise; we still want the score visible in the PR.
        "categories:best-practices": ["warn", { minScore: 0.9 }],
      },
    },
    upload: {
      // Default to the temporary public storage Lighthouse provides so the
      // PR comment links to a real report. Switch to `target: "lhci"` and
      // a self-hosted server later if/when retention matters.
      target: "temporary-public-storage",
    },
  },
};
