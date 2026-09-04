/**
 * Page-aware "How to read this page" content for the HowToReadDrawer.
 *
 * One entry per V4.1 route. The 4-rule spine is constant across all pages;
 * the noun and sentence framing shift to match what the reader is actually
 * looking at on that page.
 *
 * Rules must carry no banned vocabulary (M8-R5, HARD_FAIL, LOCO, gate,
 * Majles, F-ML-1, cascade-vs-ML, etc.) and no em-dashes.
 */

export type RouteKey =
  | "dashboard-v4.1"
  | "recipes-v4.1"
  | "recipes-v4.1-detail"
  | "countries-v4.1"
  | "countries-v4.1-detail"
  | "risk-board"
  | "compound-risk"
  | "analogues"
  | "recipe-tracker"
  | "compare"
  | "patterns-v4"
  | "patterns-v4-detail"
  | "recipe-country-match"
  | "live-pulse";

export interface RuleEntry {
  /** Short title, sentence case, ~5 words. */
  title: string;
  /** 1-2 sentences, plain English, page-aware noun. */
  body: string;
}

export interface PageHowToRead {
  /** 1 sentence, page-specific framing. */
  lede: string;
  /** Four rules house-style; five allowed where a page gains a distinct
   *  data layer (the country profile's news panels, 2026-06-10). */
  rules:
    | [RuleEntry, RuleEntry, RuleEntry, RuleEntry]
    | [RuleEntry, RuleEntry, RuleEntry, RuleEntry, RuleEntry];
}

export const HOW_TO_READ_CONTENT: Record<RouteKey, PageHowToRead> = {
  "dashboard-v4.1": {
    lede: "Four rules for everything you read on this dashboard.",
    rules: [
      {
        title: "Scores are ranks, not probabilities",
        body: "Every score on this page is a resemblance rank: how closely a country's recent trajectory matches a validated historical pattern. A rank of 80 is not an 80% chance of anything.",
      },
      {
        title: "Counts come from the tracker",
        body: "The hero tile counts and the activity feed are pulled from the Trend Tracker, which is the source of truth. Nothing on this dashboard upgrades or changes a trend's status.",
      },
      {
        title: "Corrections are published on purpose",
        body: "When a prior validation does not survive audit, we withdraw it publicly in the activity log. Visible corrections are part of how the program works, not a sign of failure.",
      },
      {
        title: "Nothing here is a forecast",
        body: "QGI describes resemblance, not a forecast about which country will see which event in which year.",
      },
    ],
  },

  "recipes-v4.1": {
    lede: "Four rules for reading the trend catalogue.",
    rules: [
      {
        title: "Scores are ranks, not probabilities",
        body: "Every score listed for a trend is a resemblance rank against historical precedents, not a probability that the event will recur. A higher rank means a closer structural match.",
      },
      {
        title: "Status comes from the tracker",
        body: "The status badge on each trend (validated, tested, queued, and so on) is the Trend Tracker's current reading. The catalogue table reflects that source directly.",
      },
      {
        title: "Corrections are published on purpose",
        body: "If a trend's prior status did not survive re-evaluation, the revised status appears here alongside a public note. That transparency is intentional.",
      },
      {
        title: "Nothing here is a forecast",
        body: "A trend describes a structural pattern observed in historical data. It does not predict whether or when a specific country will experience that event.",
      },
    ],
  },

  "recipes-v4.1-detail": {
    lede: "Four rules for reading a single trend's detail page.",
    rules: [
      {
        title: "Scores are ranks, not probabilities",
        body: "Every country score on this trend page is a resemblance rank showing how closely that country's current indicators match the historical pattern for this event type. It is not a probability of occurrence.",
      },
      {
        title: "Counts come from the tracker",
        body: "The validation status, run history, and indicator count shown here are drawn from the Trend Tracker. The detail page does not produce its own status.",
      },
      {
        title: "Corrections are published on purpose",
        body: "If this trend was previously validated and that result was later withdrawn, you will see both states and the reason. Withdrawals are part of the methodology record.",
      },
      {
        title: "Nothing here is a forecast",
        body: "This trend describes resemblance between a country's current trajectory and a historical instability pattern. It does not forecast a specific event in a specific year.",
      },
    ],
  },

  "countries-v4.1": {
    lede: "Four rules for reading the country list.",
    rules: [
      {
        title: "Scores are ranks, not probabilities",
        body: "Every score next to a country name is a resemblance rank within the current panel, not a probability of instability. Countries ranked close together can have very different underlying situations.",
      },
      {
        title: "Counts come from the tracker",
        body: "The trend counts and status badges shown per country are pulled from the Trend Tracker. The countries list does not generate its own trend statuses.",
      },
      {
        title: "Corrections are published on purpose",
        body: "When a trend that previously scored a country is withdrawn or revised, the country's count updates accordingly. That is expected behavior, not a data error.",
      },
      {
        title: "Nothing here is a forecast",
        body: "Country scores describe how structurally similar a country is to historical precedents for various event types. They do not predict events in specific countries at specific times.",
      },
    ],
  },

  "countries-v4.1-detail": {
    lede: "Five rules for reading a single country's profile.",
    rules: [
      {
        title: "Scores are ranks, not probabilities",
        body: "Every trend lit on this country page shows a resemblance rank, not a probability. A trend marked as firing means this country's current indicators structurally resemble historical cases where that event type occurred.",
      },
      {
        title: "Trend status comes from the tracker",
        body: "The validated or tested status for each trend shown here is drawn from the Trend Tracker. The country profile reflects those statuses; it does not set them.",
      },
      {
        title: "Corrections are published on purpose",
        body: "If a trend that previously fired for this country has since been withdrawn or revised, the profile updates to show the corrected state. The prior result is not erased.",
      },
      {
        // News layer (2026-06-10): the panels' resemblance-not-forecast
        // firewall, in the designated escape valve (V4.1 §9).
        title: "News pressure measures attention, not events",
        body: "The news panels show how much of this country's coverage is running on each theme versus its own history. News pressure confirms or questions a structural reading; it does not forecast an event.",
      },
      {
        title: "Nothing here is a forecast",
        body: "The indicators and pattern scores on this page describe structural resemblance to historical cases. They do not constitute a prediction of a specific event for this country.",
      },
    ],
  },

  // Live Pulse terminal (2026-06-11): the soft landing for the news layer.
  // Written for a first-time reader; the terminal itself stays dense.
  "live-pulse": {
    lede: "Five rules for reading the Live Pulse terminal.",
    rules: [
      {
        title: "Two readings, never one number",
        body: "Structural is how closely this country's long-run signals resemble the shape that ran ahead of this kind of event in the past, from 0 to 100. News pulse is how much of the country's news coverage is on this theme right now, where 50 is its own normal month.",
      },
      {
        title: "News pulse measures attention, not events",
        body: "A pulse of 100 means the theme dominates this country's coverage compared with its own history. It confirms or questions a structural reading; it does not forecast an event.",
      },
      {
        title: "The verdict is the combination",
        body: "Active means structure and news are both elevated, from 60 upward. Signal is news without structural backing, often noise. Latent is structure primed while the news stays quiet. Quiet is neither.",
      },
      {
        title: "Pins are real events",
        body: "The pins on the chart mark events from the verified record. Hover a pinned month and the tooltip names what happened.",
      },
      {
        title: "How themes show up in the news",
        body: "For the Electoral and Economic themes, the news pulse is recall-validated: it fires at known events on the verified record. Other themes are tracked while their validation runs.",
      },
    ],
  },

  "risk-board": {
    lede: "Four rules for reading the risk board grid.",
    rules: [
      {
        title: "Scores are ranks, not probabilities",
        body: "Every cell on the board holds a resemblance rank showing how closely a country-trend pair matches its validated historical pattern. A higher number is a closer structural match, not a higher probability of an event.",
      },
      {
        title: "Cell status comes from the tracker",
        body: "The color coding and status of each cell reflect the Trend Tracker's current reading for that trend. The board is a visualization of tracker data, not an independent scoring layer.",
      },
      {
        title: "Corrections are published on purpose",
        body: "When a trend status changes after audit, the relevant cells update. Empty or revised cells after a prior fill are the methodology working correctly.",
      },
      {
        title: "Nothing here is a forecast",
        body: "The board shows structural resemblance across countries and event types simultaneously. It is a comparative view, not a ranked list of countries most likely to experience events.",
      },
    ],
  },

  "compound-risk": {
    lede: "Four rules for reading compound risk scores.",
    rules: [
      {
        title: "Compound scores stack ranks, not odds",
        body: "A compound score adds up resemblance ranks from multiple trends for a single country. It does not multiply probabilities. Two trends each at rank 70 produce a compound score of 140, not a 70% combined probability.",
      },
      {
        title: "Input statuses come from the tracker",
        body: "Only trends with a current validated status in the Trend Tracker contribute to compound scores. The tracker is the source of truth for which trends are eligible to stack.",
      },
      {
        title: "Corrections are published on purpose",
        body: "When a trend contributing to a compound score is withdrawn, that country's compound score changes. The change is expected and is reported alongside the withdrawal notice.",
      },
      {
        title: "Nothing here is a forecast",
        body: "A high compound score means a country simultaneously resembles historical patterns across several event types. It does not forecast that multiple events will occur.",
      },
    ],
  },

  analogues: {
    lede: "Four rules for reading Analogues matches.",
    rules: [
      {
        title: "Matches are similarities, not predictions",
        body: "Each analogue pair shows two countries whose indicator trajectories ran in close parallel over a shared historical window. Structural similarity over the past does not predict that the target country will follow the reference country's future path.",
      },
      {
        title: "Analogue scores come from validated trends",
        body: "The trend scores shown alongside analogue pairs are drawn from the Trend Tracker. An analogue's relevance depends on whether the shared trends are validated; the tracker is the source of truth for that.",
      },
      {
        title: "Corrections are published on purpose",
        body: "If a trend that anchored an analogue pair is later revised or withdrawn, the pair's displayed context updates. The analogue itself stays in the record; its trend context is corrected.",
      },
      {
        title: "Nothing here is a forecast",
        body: "Finding that Country A resembles Country B at a given historical moment does not mean Country A will replicate Country B's subsequent trajectory. Analogy is a structural lens, not a forward projection.",
      },
    ],
  },

  compare: {
    lede: "Four rules for reading a side-by-side comparison.",
    rules: [
      {
        title: "Scores are ranks, not probabilities",
        body: "Every cell on this page is a resemblance rank showing how closely each country's recent trajectory matches a trend today. A 30-point gap between two countries on a trend is a gap in rank position, not a gap in event probability.",
      },
      {
        title: "Comparison is structural, not relative",
        body: "Placing two countries next to each other on the same trends does not declare a winner or rank one as more at risk than the other. Both countries sit on the same distribution; the page shows you where each one currently sits.",
      },
      {
        title: "Status comes from the tracker",
        body: "The status chip on each trend row (deployed, tested, queued, withdrawn) is drawn from the Trend Tracker, which is the source of truth. The comparison view reflects those statuses; it does not set them.",
      },
      {
        title: "Nothing here is a forecast",
        body: "A side-by-side comparison describes how two countries' structural shapes look today. It does not predict which country will experience a specific event, nor which one will experience it first.",
      },
    ],
  },

  "patterns-v4": {
    lede: "Four rules for reading the patterns catalogue.",
    rules: [
      {
        title: "Strength is a rank, not a probability",
        body: "Every pair strength on this page is a 0-to-100 rank showing how tightly two countries' indicator trajectories rhymed over a shared historical window. A pair at 91 is at the top of the distribution, not 91 percent likely to do anything.",
      },
      {
        title: "Both countries' pasts, not either's future",
        body: "A pattern describes the historical record. Argentina and Russia running together through the 1990s is a fact about those decades. It does not say that Argentina will follow Russia next, or that Russia will follow Argentina next. The rhyme is symmetric and historical.",
      },
      {
        title: "Corrections are published on purpose",
        body: "When a pair's window or strength is revised after a fresh data release, the change appears here. A pair sliding out of the top 30 between releases is the methodology working as designed.",
      },
      {
        title: "Nothing here is a forecast",
        body: "Pair-rhymes are a historical-shape lens. They describe how two countries' stories ran together, not how either country's story will unfold next. Read them as analogies, not as predictions.",
      },
    ],
  },

  "patterns-v4-detail": {
    lede: "Four rules for reading a single pair of countries' shared past.",
    rules: [
      {
        title: "Scores are ranks, not probabilities",
        body: "The strength of this pair, the indicator contribution bars, and the catalogue rank shown on this page are all resemblance ranks. They describe how closely two countries' historical trajectories ran together. They are not probabilities of any current or future event for either country.",
      },
      {
        title: "Both countries' pasts, not either's future",
        body: "The page describes a shared historical window. Even when one country's indicators crossed a threshold years before the other country's did, that fact is historical. It is not a signal that the second country will repeat the first country's later trajectory. The page treats the two countries symmetrically for that reason.",
      },
      {
        title: "Per-indicator timestamps are facts, pair-level direction is not",
        body: "Inside the indicators panel you will see two years per indicator: the historical year each country crossed a notable threshold on that indicator. Those two years are facts. The page does not combine them into a single direction for the whole pair, because doing so would imply a forecast the methodology cannot support.",
      },
      {
        title: "Nothing here is a forecast",
        body: "Finding that two countries resembled each other across a historical window does not tell you that either country will resemble its past, or the other country's past, going forward. To read either country's present, follow the country-profile link at the bottom of the page. The two countries' present-day stories are not narrated on this page.",
      },
    ],
  },

  "recipe-country-match": {
    lede: "Four rules for reading how one country is tracing one trend.",
    rules: [
      {
        title: "The score is a rank, not a probability",
        body: "The big number is a resemblance rank: how closely this country's recent trajectory matches the shape that ran ahead of this event type in past cases. A score of 90 means it sits near the top of that resemblance, not that there is a 90% chance of anything.",
      },
      {
        title: "Shape behind, this country's path in front",
        body: "For each signal we draw the average path that ran ahead of past cases and the range most cases stayed within, then lay this country's own recent path on top in white. Where the white line sits inside the band, the country is in shape. Where it parts, it is drifting off.",
      },
      {
        title: "The white line ends at today",
        body: "Every movement line stops at the latest reading and is never drawn forward. A line that has been settling into the shape describes the recent past, not a projection of where the country goes next.",
      },
      {
        title: "Nothing here is a forecast",
        body: "Tracing the shape of an event type is a measure of resemblance to history. It does not predict that this country will experience that event, nor when. The analogues we list are history about other situations, not a forecast about this one.",
      },
    ],
  },

  "recipe-tracker": {
    lede: "Four rules for reading the Trend Tracker, which is the source of truth for all trend statuses across QGI.",
    rules: [
      {
        title: "Scores are ranks, not probabilities",
        body: "Where resemblance scores appear on this page, they are ranks showing structural similarity to historical patterns. The tracker's own role is to record validation status, not to generate probability estimates.",
      },
      {
        title: "This page is the source of truth",
        body: "Every trend status you see anywhere on QGI traces back to this tracker. If you see a discrepancy between another page and this one, this tracker's reading is correct.",
      },
      {
        title: "Corrections are published on purpose",
        body: "Status changes, withdrawals, and revisions are logged here with timestamps. The full history of a trend's status is part of the methodology record, not a footnote.",
      },
      {
        title: "Nothing here is a forecast",
        body: "A validated trend means the historical pattern was confirmed to exist and be statistically meaningful. Validation status does not imply a forecast about when or where the pattern will next occur.",
      },
    ],
  },
};
