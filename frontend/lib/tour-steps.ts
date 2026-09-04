import type { Step } from "react-joyride";

/**
 * QGI in-product tour — steps across 10 canonical pages.
 *
 * Original 12 legacy steps (for /dashboard V3, /precedents, /patterns V3,
 * /signals, /countries V3) removed 2026-05-28 as part of the V4.1
 * canonical promotion — those routes are deleted; the steps would target
 * dead anchors. The V4.1 steps (authored by Hana Kawai-Bjornsson 2026-05-28,
 * revised 2026-06-04 for anchor correctness and the Recipe→Trend rename)
 * cover every visible panel on each canonical surface. Arc:
 * "Resemblance, not prediction."
 *
 * Every page has a mandatory **(a) Introduction** step anchored on the
 * page's `h1` or primary header element. Additional **(d) "What to be
 * careful of"** steps anchor on methodology disclosure callouts where
 * the how-to-read-button is available. Some pages add **(b) Navigation**
 * or **(c) Workflow** steps where 3+ personas converged on a high-leverage
 * affordance.
 *
 * Steps are page-resumed by the TourProvider — visiting another page
 * mid-tour picks up at that page's first remaining step.
 *
 * 2026-06-04 changes:
 *  - /dashboard: hero-tiles/highlights-band/surfaces-grid/activity-timeline
 *    → closest-matches/historical-resemblances/world-activity/scope-strip.
 *    how-to-read-button dropped (/dashboard does not render HowToReadButton).
 *  - /countries: cotw-tile step dropped (country-of-the-week section removed
 *    from CountriesV41Hero). Step count: 5→4.
 *  - /trends/foreign_intervention: demo-disclosure retargeted to
 *    section[id="cap-1"] (isDemoGraduated() always returns false). Steps: 13→12.
 *  - /risk-board: how-to-read-button step dropped (/risk-board does not
 *    render HowToReadButton). Step count: 5→4.
 *  - /compare: compare-picker/matrix/drivers/at-a-glance/generate-comparison
 *    all sit in aria-hidden pointer-events:none backdrop. Steps reduced to
 *    h1 + compare-coming-soon (new anchor on the overlay panel). Steps: 6→2.
 *  - /patterns: how-to-read-button step dropped (/patterns does not render
 *    HowToReadButton). Step count: 6→5.
 *  - /patterns detail: slug updated to "172-208" (Paraguay + South Korea,
 *    top PPS entry). Steps retargeted to anchors added to the real page.
 *    how-to-read-button step dropped. Steps: 7→4.
 *  - Copy: "recipe"→"trend", "Recipe"→"Trend" in all user-visible strings.
 *    Route literals and code identifiers unchanged.
 */

export interface QgiTourStep extends Step {
  /** Which page route this step is anchored on. Used by the provider to
   *  segment the tour by route + resume on navigation. */
  page:
    | "/dashboard"
    | "/trends"
    | "/trends/foreign_intervention"
    | "/countries"
    | "/countries/sdn"
    | "/risk-board"
    | "/analogues"
    | "/compare"
    | "/patterns"
    | "/patterns/172-208";
  /** Tour-design dimension covered (a/b/c/d) per the spec. */
  dimension: "a" | "b" | "c" | "d";
}

export const TOUR_STEPS: ReadonlyArray<QgiTourStep> = [
  // ─── /dashboard — 5 steps, ordered top-to-bottom ────────────────────
  // Note: /dashboard does not render HowToReadButton. how-to-read-button
  // step removed. Scope strip added as closing reference step instead.
  {
    page: "/dashboard",
    dimension: "a",
    target: "h1",
    title: "Start with the thesis",
    content:
      "QG Intelligence describes country risk by comparing today against history. Every number on this site is a resemblance score: how strongly a country's recent trajectory matches a validated historical pattern. Nothing here is a forecast of a specific event in a specific year.",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/dashboard",
    dimension: "b",
    target: '[data-tour="closest-matches"]',
    title: "On the radar right now",
    content:
      "Countries whose recent signals are tracing an event trend especially closely this release. Each card links to the full country-by-trend match view. These are measures of resemblance, not forecasts.",
    placement: "bottom",
  },
  {
    page: "/dashboard",
    dimension: "c",
    target: '[data-tour="historical-resemblances"]',
    title: "Where today looks like the past",
    content:
      "Each card pairs a country today with the historical situation it most resembles. Similarity is not prediction; it is a lens on history. Open any card to explore the full set of analogues.",
    placement: "bottom",
  },
  {
    page: "/dashboard",
    dimension: "c",
    target: '[data-tour="world-activity"]',
    title: "What is moving this release",
    content:
      "Country movements, trend leaders, and historical resemblances pulled from the current scoring run. Every row links to the underlying data. A rank shift is not a probability change.",
    placement: "top",
  },
  {
    page: "/dashboard",
    dimension: "d",
    target: '[data-tour="scope-strip"]',
    title: "Program scope at a glance",
    content:
      "How many countries, trends, families, and signals the program currently covers, with a link to the full methodology. These counts come from the tracker; they refresh each data release. Nothing here is a forecast.",
    placement: "top",
  },

  // ─── /trends — 4 steps ─────────────────────────────────────────────
  {
    page: "/trends",
    dimension: "a",
    target: "h1",
    title: "The catalog of patterns",
    content:
      "A trend is a pre-registered shape: a small set of indicators (typically three to five) whose trajectory tends to rise or fall together in the years before a particular kind of event. The catalog is grouped by family.",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/trends",
    dimension: "b",
    target: '[data-tour="family-section-A"] header',
    title: "Eight families, by event kind",
    content:
      "Families group trends by what kind of rupture they describe: conflict and violence, governance breakdown, economic crisis, and so on. The color on each card is the family color, kept consistent everywhere on the site.",
    placement: "top",
  },
  {
    page: "/trends",
    dimension: "d",
    target: 'a[href="/trends/foreign_intervention"]',
    title: "Pick one to see how deep it goes",
    content:
      "We will open foreign_intervention next. It is the demo trend: it was withdrawn for re-evaluation after an audit found a coverage gap, and the page carries that note transparently. That is the methodology working as designed.",
    placement: "right",
  },
  {
    page: "/trends",
    dimension: "d",
    target: '[data-tour="how-to-read-button"]',
    title: "Open this when you forget",
    content:
      "Every page has this button. It opens a quiet reference card with the four ground rules: scores are ranks not probabilities, counts come from the tracker, corrections are published on purpose, nothing here is a forecast.",
    placement: "bottom",
  },

  // ─── /trends/foreign_intervention — 12 steps, top-to-bottom ────────
  // Reading arc: Header (h1) → Structure (Definition cap-1, Identity card,
  // Indicator Set cap-2, Window) → Validation (Discrimination, Reliability,
  // Calibration) → Results (Countries, Score Distribution) → Deep-dive
  // (Precedents, Pattern Alignment) → how-to-read-button.
  // Note: demo-disclosure is not rendered (isDemoGraduated always returns
  // false). The arc opens with the Definition panel (cap-1) instead.
  {
    page: "/trends/foreign_intervention",
    dimension: "a",
    target: "h1",
    title: "One trend, laid bare",
    content:
      "A trend is a pre-registered shape, validated against curated historical events. The page is organized in four blocks: structure (what the trend is made of), validation (how well it works), results (which countries currently resemble it), and deep-dive (the anatomy behind a single match).",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "a",
    target: '[data-tour="definition-lede"]',
    title: "The trend's definition",
    content:
      "Every trend starts with a structural identity: a plain-language description of what kind of trajectory it was built to detect. Read this to understand what the trend is looking for before you look at any number.",
    placement: "bottom",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "b",
    target: 'section[id="cap-2"]',
    title: "What moves with the trend",
    content:
      "A trend is a small set of indicators whose canonical movement shape defines it. The weights sum to 100% across the set: a higher weight means the indicator pulled more of its weight in distinguishing pre-event years from non-event ones.",
    placement: "right",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "a",
    target: '[data-tour="window-panel"]',
    title: "How far back the shape looks",
    content:
      "Each trend's canonical movement shape spans a fixed window of years before the event. This number is the trend's memory horizon: how much past trajectory it considers when matching today's countries.",
    placement: "right",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "c",
    target: '[data-tour="discrimination-panel"]',
    title: "How well the trend separates",
    content:
      "The discrimination score reports how well the trend separates pre-event years from non-event years on countries it never trained on. Higher means a cleaner separation: it does not mean any single country will experience the event.",
    placement: "right",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "c",
    target: '[data-tour="reliability-panel"]',
    title: "Does it hold up across passes",
    content:
      "Discrimination on one validation pass can be a coincidence. Reliability asks whether the result repeats across multiple passes on the same evidence base. This panel says whether the verdict survived the second look.",
    placement: "right",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "c",
    target: '[data-tour="calibration-panel"]',
    title: "Calibration, separately tracked",
    content:
      "Discrimination tells you whether the trend separates pre-event from non-event years. Calibration is a different question: whether the score it assigns means what it claims to mean. Tracked separately because they fail differently.",
    placement: "right",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "c",
    target: '[data-tour="countries-panel"]',
    title: "Today's resemblance, ranked",
    content:
      "These are the countries whose recent trajectory most resembles the trend today. Read it as a leaderboard of resemblance, not a watchlist of risk. The same shape appears as a row on the Live Risk Board you will see in a few steps.",
    placement: "top",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "c",
    target: '[data-tour="score-distribution-panel"]',
    title: "Where today's countries fall",
    content:
      "The histogram of every country's score on this trend today. The top countries you saw a panel up sit in the right tail; most countries cluster around the middle. The shape of the curve tells you whether the trend is decisive or ambiguous.",
    placement: "top",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "c",
    target: '[data-tour="precedents-timeline-panel"]',
    title: "The cases this trend was trained on",
    content:
      "Every event in the curated record that this trend was validated against, in date order. Click any to read the case brief. This is the historical evidence base; nothing else on the page would exist without it.",
    placement: "top",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "c",
    target: '[data-tour="pattern-alignment-panel"]',
    title: "The shape, indicator by indicator",
    content:
      "The canonical movement shape spelled out: for each indicator in the trend, the mean trajectory of validated positives in the years leading to the event, with a band showing the 25th to 75th percentile. This is what 'looks like' looks like.",
    placement: "top",
  },
  {
    page: "/trends/foreign_intervention",
    dimension: "d",
    target: '[data-tour="how-to-read-button"]',
    title: "Open this when you forget",
    content:
      "Every page has this button. It opens a quiet reference card with the four ground rules. Re-open it on any page to re-anchor.",
    placement: "bottom",
  },

  // ─── /countries — 4 steps, ordered top-to-bottom ────────────────────
  // Note: cotw-tile step removed 2026-06-04 — CountriesV41Hero no longer
  // renders the country-of-the-week section.
  {
    page: "/countries",
    dimension: "a",
    target: "h1",
    title: "The same data, pivoted",
    content:
      "If a trend is the pattern, a country is the body the pattern shows up on. This atlas asks: of every country we track, which trends does it currently resemble? Each card is a small dossier; tap it for the full country view.",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/countries",
    dimension: "b",
    target: '[data-tour="atlas-filters"]',
    title: "Filter and sort the atlas",
    content:
      "Region filter, family filter, sort by compound score or by number of trends in play. The atlas is the entire roster of countries we cover, and these controls are how you cut it.",
    placement: "bottom",
  },
  {
    page: "/countries",
    dimension: "c",
    target: '[data-tour="atlas-grid"]',
    title: "Every country, as a card",
    content:
      "Each card is a small dossier: dominant family color on the border, the trends the country is currently matching, the compound score. Tap any card for the full country view.",
    placement: "top",
  },
  {
    page: "/countries",
    dimension: "d",
    target: '[data-tour="how-to-read-button"]',
    title: "Same rules apply",
    content:
      "Scores on this page are still ranks of resemblance, not probabilities. A country lit on three trends is not three times more likely to break: it is a country whose current trajectory rhymes with three distinct historical patterns.",
    placement: "bottom",
  },

  // ─── /countries/sdn — 7 steps, ordered top-to-bottom ────────────────
  {
    page: "/countries/sdn",
    dimension: "a",
    target: "h1",
    title: "One country, in full",
    content:
      "What the platform currently says about Sudan, in plain language. The lede tells you how many trends this country is in play on, across how many families, and reminds you that none of these trends is deployed for real decisions. Resemblance, not prediction.",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/countries/sdn",
    dimension: "b",
    target: '[data-tour="recipes-in-play-panel"]',
    title: "Active trends, scored and chipped",
    content:
      "Every trend Sudan currently resembles, scored on the same 0 to 100 rank. The status chip on the right says whether that trend has been deployed, was tested and did not hold up, is in review, or is still queued.",
    placement: "top",
  },
  {
    page: "/countries/sdn",
    dimension: "c",
    target: '[data-tour="drivers-panels"]',
    title: "Why and what's moving",
    content:
      "The two panels here split the question. 'Why' shows which indicators contributed most to the top resemblance score. 'What's moving' shows which indicators have shifted most lately. Together they answer: where did the score come from, and where is it heading.",
    placement: "top",
  },
  {
    page: "/countries/sdn",
    dimension: "c",
    target: '[data-tour="rank-history-panel"]',
    title: "Where the country sits over time",
    content:
      "How the country's rank on its top trend has moved across recent quarters. Movement is a rank shift, not a probability change. A country climbing the list does not mean an event is more likely; it means its trajectory is matching the trend shape more strongly than it was.",
    placement: "top",
  },
  {
    page: "/countries/sdn",
    dimension: "c",
    target: '[data-tour="analogs-panel"]',
    title: "Closest historical rhymes",
    content:
      "The three past cases whose trajectories most resemble this country's recent shape. Open Analogues from the sidebar to explore the full picker; this panel is the country-detail shorthand.",
    placement: "top",
  },
  {
    page: "/countries/sdn",
    dimension: "b",
    target: '[data-tour="vintage-sources-panel"]',
    title: "Provenance, in one place",
    content:
      "When the data was last refreshed, which providers it came from, and the release it belongs to. Visit this panel before quoting any number; freshness is part of the claim.",
    placement: "top",
  },
  {
    page: "/countries/sdn",
    dimension: "d",
    target: '[data-tour="how-to-read-button"]',
    title: "Open this when you forget",
    content:
      "Every page has this button. It opens a quiet reference card with the four ground rules. The country page is the one most often deep-linked and shared, so it is worth opening before you cite a number from here.",
    placement: "bottom",
  },

  // ─── /risk-board — 4 steps, ordered top-to-bottom ────────────────────────
  // Note: /risk-board does not render HowToReadButton. how-to-read-button
  // step removed. Step count: 5→4.
  {
    page: "/risk-board",
    dimension: "a",
    target: "h1",
    title: "Today, in one leaderboard",
    content:
      "Which countries currently resemble a validated crisis shape, ranked across every trend in the catalog. Each cell is one country, on one trend, today. Click any cell to open that trend's report card.",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/risk-board",
    dimension: "b",
    target: '[data-tour="risk-board-grid"]',
    title: "Every trend, top ten countries each",
    content:
      "The grid: each row is one trend, each cell is one country's rank on it. Sort, filter by family, pin a country to track it across rows. Click any cell to open that trend's full report card.",
    placement: "top",
  },
  {
    page: "/risk-board",
    dimension: "c",
    target: '[data-tour="recent-movements"]',
    title: "Who moved most this quarter",
    content:
      "Countries whose rank shifted most since the last data release. Up arrows are countries climbing the board, down arrows are countries falling. A rank shift is not a probability change — nothing here is a forecast.",
    placement: "top",
  },

  // /compound-risk tour steps removed 2026-05-30 — the route was taken
  // down. Tour-step authoring will return once the page is rejuvenated.

  // ─── /analogues — 6 steps, ordered top-to-bottom ────────────────────────
  {
    page: "/analogues",
    dimension: "a",
    target: "h1",
    title: "Today's shape, in history",
    content:
      "Pick a country today, the engine shows you the closest historical match. Pure shape-matching across the trend library. A similarity statement, never a forecast of what happens next.",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/analogues",
    dimension: "c",
    target: '[data-tour="picker-panel"]',
    title: "Pick a country, see its rhyme",
    content:
      "Search for any country in the corpus. The page returns its three closest historical analogues, with what happened to those analogue countries listed for context. That history is a fact about the analogue, not a prediction about today's country.",
    placement: "right",
  },
  {
    page: "/analogues",
    dimension: "b",
    target: '[data-tour="analog-results"]',
    title: "Three matches, with outcomes",
    content:
      "Each match card carries the analogue country, the year, a similarity score, and a brief note on what happened next. 'What happened next' is a fact about the analogue, not a forecast about today's country. Read it that way and you read it correctly.",
    placement: "top",
  },
  {
    page: "/analogues",
    dimension: "c",
    target: '[data-tour="recipe-contributions"]',
    title: "Which trends pulled the match",
    content:
      "A match is a weighted average of resemblances across the trend library. This panel tells you which trends did most of the pulling. A non-deployed trend contributing 30 percent is not a green light; it is a flag, weighted into a similarity statement.",
    placement: "top",
  },
  {
    page: "/analogues",
    dimension: "c",
    target: '[data-tour="analog-methodology-box"]',
    title: "Resemblance, never forecast",
    content:
      "If you read one statement on this site, read this panel's four. Analogues matches are similarities, not forward predictions: today's Egypt looking like 2008 Tunisia means the trajectories rhyme, not that Egypt will follow Tunisia.",
    placement: "left",
  },
  {
    page: "/analogues",
    dimension: "d",
    target: '[data-tour="how-to-read-button"]',
    title: "Open this when you forget",
    content:
      "Every page has this button. It opens a quiet reference card with the four ground rules. Analogues matches are similarities, not forward predictions -- open the rules on any page when you need to re-anchor.",
    placement: "bottom",
  },

  // ─── /compare — 2 steps ─────────────────────────────────────────────────
  // /compare is "Coming soon". The real comparison panels sit in an
  // aria-hidden, pointer-events:none blurred backdrop. Only the overlay is
  // accessible. how-to-read-button is also not rendered on this page.
  {
    page: "/compare",
    dimension: "a",
    target: "h1",
    title: "Two countries, same metrics",
    content:
      "Compare places two countries next to each other on the same set of trends, today. This surface is coming soon; until then, you can compare any country to its closest historical analogue via the Analogues page.",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/compare",
    dimension: "c",
    target: '[data-tour="compare-coming-soon"]',
    title: "What this page will do",
    content:
      "When live: pick any two countries, read every trend side by side on the same scale, see where the gap comes from at the indicator level. The blurred preview behind this message is a mock of what the surface will look like.",
    placement: "bottom",
  },

  // /trend-tracker tour steps removed 2026-05-29 — the route was deleted.

  // ─── /patterns — 5 steps, ordered top-to-bottom ───────────────────────
  // Note: /patterns does not render HowToReadButton. how-to-read-button
  // step removed. Step count: 6→5.
  {
    page: "/patterns",
    dimension: "a",
    target: "h1",
    title: "Two countries, same arc",
    content:
      "A pattern is two countries whose stories ran in step for a long stretch of history. This page is the catalogue. Each row is a pair, the years they ran together, and how tightly they rhymed.",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/patterns",
    dimension: "b",
    target: '[data-tour="patterns-filters"]',
    title: "Narrow the catalogue",
    content:
      "The whole archive is searchable from this panel: filter by country, by how long the shared window ran, and by start year. The results update as you go.",
    placement: "right",
  },
  {
    page: "/patterns",
    dimension: "c",
    target: '[data-tour="patterns-results"]',
    title: "The ranked results",
    content:
      "Each row is a pair: the two countries, the years they ran in step, and how tightly they rhymed. The strongest rhymes sort to the top; click any row to open its detail page. The strength score is a rank, not a probability.",
    placement: "top",
  },

  // ─── /patterns/172-208 — 4 steps (Paraguay + South Korea, top PPS) ──────
  // The detail page renders real cascade data. Four anchors were added to
  // the page for the tour. how-to-read-button is not rendered on this page.
  {
    page: "/patterns/172-208",
    dimension: "a",
    target: '[data-tour="pair-header"]',
    title: "A pair, not a leader and a follower",
    content:
      "You are looking at two countries whose trajectories ran in parallel over a shared historical window. The page treats them symmetrically. Neither country is described as leading or following the other.",
    placement: "bottom",
    skipBeacon: true,
  },
  {
    page: "/patterns/172-208",
    dimension: "a",
    target: '[data-tour="pair-summary"]',
    title: "Where this pair sits",
    content:
      "Four numbers: where this pair sits in the catalogue, how long the shared window was, how many indicators went into it, and the average Pearson correlation over the window. These are the structural facts of the resemblance.",
    placement: "bottom",
  },
  {
    page: "/patterns/172-208",
    dimension: "b",
    target: '[data-tour="pair-shape-overlay"]',
    title: "What the resemblance looked like",
    content:
      "A plain-language summary of the pair's shared window: how long they tracked together, the Pearson correlation, and how many indicators were in parallel. This is structural resemblance, not a forecast about what either country does next.",
    placement: "top",
  },
  {
    page: "/patterns/172-208",
    dimension: "c",
    target: '[data-tour="pair-indicators"]',
    title: "Per-indicator breakdown — coming next",
    content:
      "The indicator-level detail for this pair (which specific indicators ran in parallel, with their aligned series) is computed by the cascade SCDI batch. It lands with the next data release. We show it only once it is real.",
    placement: "top",
  },
];

/** Step count by page — used by the TourProvider for "Step N of M" display. */
export const TOUR_STEPS_BY_PAGE: Readonly<Record<QgiTourStep["page"], number>> =
  TOUR_STEPS.reduce<Record<string, number>>((acc, s) => {
    acc[s.page] = (acc[s.page] ?? 0) + 1;
    return acc;
  }, {}) as Readonly<Record<QgiTourStep["page"], number>>;

export const TOUR_TOTAL_STEPS = TOUR_STEPS.length;
