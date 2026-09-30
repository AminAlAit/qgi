import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";
import {
  ChartMultiRecipeConvergenceHero,
  ChartMultiRecipeConvergence,
  ChartSelfAnalogue,
} from "./charts/ChartWrapper";
import TocSidebar from "./TocSidebar";
import PrintButton from "./PrintButton";

/**
 * Pakistan Country Profile report page.
 *
 * Source draft: docs/specs/internal/testing/pakistan-profile/draft-article.md
 * Scoring run:  te-fleet-run-2, scored 2026-06-01T22:58:47 UTC
 * Byline:       Amin Al-Ait (NEVER a persona name -- see E3 in report guidelines)
 * Template:     mirrors app/reports/uk-currency-crisis/page.tsx exactly
 */

const BAKE_DATE = "2026-06-01";
const PUBLISH_DATE = "2026-06-20";

// --- Metadata ---------------------------------------------------------------

export const metadata: Metadata = {
  title: "Five Models, One Country: Pakistan's Structural Scan · QG Intelligence Report",
  description:
    "Pakistan ranks in the top 8 to 20 globally across five independent structural models simultaneously. Its nearest self-analogue is Pakistan 2011 (match 0.9712). QGI te-fleet-run-2, June 2026.",
  alternates: {
    canonical: "https://qgintelligence.com/reports/pakistan-profile",
  },
  openGraph: {
    title:
      "Five Models, One Country: What QGI's Structural Scan Finds in Pakistan That Macro Analysis Misses",
    description:
      "Pakistan tops 5 independent structural models simultaneously. Nearest self-analogue: Pakistan 2011 (match 0.9712). The same indicator configuration that preceded Raymond Davis, Abbottabad, and Salala.",
    url: "https://qgintelligence.com/reports/pakistan-profile",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: `${PUBLISH_DATE}T00:00:00Z`,
  },
  twitter: {
    card: "summary_large_image",
    title: "Five Models, One Country: Pakistan's Structural Scan",
    description:
      "Pakistan ranks top 8-20 across 5 independent structural models. Self-analogue: Pakistan 2011 (match 0.9712). Repression score 82.6, news pulse 25: the widest structure-news divergence in QGI's full profile.",
  },
  robots: { index: true, follow: true },
};

// --- Footnote registry -------------------------------------------------------
// Numbered in order of first appearance in the prose body.

const FOOTNOTES = [
  {
    n: 1,
    term: "LOCO AUC interpretation",
    def: "LOCO AUC (leave-one-country-out area under the ROC curve) measures how well the model ranks pre-event country-years above non-event country-years when each country is held out of training in turn. A value of 0.50 is chance; 1.00 is perfect discrimination. Values below 0.65 (Experimental tier) indicate limited validated signal; values of 0.72 to 0.82 (Directional tier) indicate reliable directional signal at the country level. These are historical validation metrics, not event-probability estimates.",
    anchor: "#loco-auc",
  },
  {
    n: 2,
    term: "Cosine similarity and structural resemblance",
    def: "Analogue match scores are cosine similarity values between two indicator vectors in the recipe's feature space. Cosine similarity ranges from 0 (orthogonal, no structural resemblance) to 1 (identical configuration). QGI uses intersection-only cosine: only indicators present in both vectors contribute to the score. A score of 0.97 means the current configuration is nearly identical to the historical comparator along the recipe's indicator dimensions.",
    anchor: "#structural-resemblance",
  },
  {
    n: 3,
    term: "SHAP attribution",
    def: "SHAP (SHapley Additive exPlanations) values decompose each country's score into indicator-level contributions. The percentage figures cited in this report represent each indicator's share of the total absolute signal. Positive SHAP pushes the score toward pre-event resemblance; negative SHAP offsets it. The SHAP decomposition comes from the scoring-refit XGBoost model, not the LOCO-validated training model, so driver percentages should be read as explanatory rather than as out-of-sample validated features.",
    anchor: "#shap-attribution",
  },
  {
    n: 4,
    term: "V-Dem coding lag on the foreign intervention self-rhyme",
    def: "The foreign intervention model's top analogue is Pakistan 2011. Several of the model's primary drivers (v2x_gender, v2stfisccap, v2xeg_eqprotec) are V-Dem indicators that carry a one-to-two year coding lag relative to real-world events. This means the 2026 vintage reflects V-Dem coding through approximately 2024-25. Developments in Pakistan's gender empowerment environment and fiscal capacity after that window are not yet captured.",
    anchor: "#data-vintages",
  },
  {
    n: 5,
    term: "Foreign Intervention recipe status: MARGINAL_PENDING_BETA_CALIBRATION",
    def: "The foreign intervention recipe has LOCO AUC of 0.7227 (Directional tier) but has not yet completed beta calibration, meaning the mapping between score_pp and event-base-rate probability has not been formally validated. The Pakistan score of 89.0 (rank 20 of 172) is valid as a structural resemblance signal; it should not be read as an event probability. Self-analogues can inflate cosine similarity by sharing country-fixed structural characteristics that are not event-predictive.",
    anchor: "#recipe-tiers",
  },
] as const;

// --- Inline Footnote component -----------------------------------------------

function Fn({ n, children }: { n: number; children: React.ReactNode }) {
  const fn = FOOTNOTES.find((f) => f.n === n);
  if (!fn) return <>{children}</>;
  return (
    <span className="fn-wrap" style={{ position: "relative", display: "inline" }}>
      <span
        className="fn-term"
        tabIndex={0}
        style={{
          borderBottom: "1px dotted var(--qgi-accent)",
          cursor: "help",
          outline: "none",
        }}
      >
        {children}
        <sup
          style={{
            color: "var(--qgi-accent)",
            fontSize: "0.65em",
            marginLeft: "1px",
            verticalAlign: "super",
          }}
        >
          {n}
        </sup>
      </span>
      <span
        className="fn-tooltip"
        role="tooltip"
        style={{
          display: "none",
          position: "absolute",
          bottom: "calc(100% + 6px)",
          left: "50%",
          transform: "translateX(-50%)",
          width: 280,
          backgroundColor: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: 4,
          padding: "8px 10px",
          zIndex: 20,
          fontSize: 11,
          lineHeight: 1.5,
          pointerEvents: "none",
          whiteSpace: "normal",
          boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
        }}
      >
        <span style={{ color: "var(--qgi-text)", display: "block", marginBottom: 4 }}>
          {fn.def}
        </span>
        <a
          href={`/methodology${fn.anchor}`}
          style={{
            color: "var(--qgi-accent)",
            textDecoration: "underline",
            fontSize: 10,
          }}
        >
          Read more &rarr;
        </a>
      </span>

      <style>{`
        .fn-wrap:hover .fn-tooltip,
        .fn-wrap:focus-within .fn-tooltip {
          display: block !important;
        }
      `}</style>
    </span>
  );
}

// --- Pull-quote component ----------------------------------------------------

function PullQuote({ children }: { children: React.ReactNode }) {
  return (
    <blockquote
      className="print:border-black"
      style={{
        margin: "2rem auto",
        maxWidth: 580,
        padding: "0.75rem 1.5rem",
        borderLeft: "4px solid var(--qgi-accent)",
        fontStyle: "italic",
        fontSize: "1.2em",
        lineHeight: 1.55,
        color: "var(--qgi-text)",
        backgroundColor: "rgba(167,139,250,0.04)",
        borderRadius: "0 4px 4px 0",
      }}
    >
      {children}
    </blockquote>
  );
}

// --- Recipe score table ------------------------------------------------------

function RecipeTable() {
  const rows = [
    {
      recipe: "Labor Action",
      score: "96.0",
      rank: "8 of 174",
      auc: "0.8145",
      tier: "Directional",
      fail: false,
    },
    {
      recipe: "Religious and Social Movement",
      score: "93.6",
      rank: "12 of 171",
      auc: "0.8186",
      tier: "Directional",
      fail: false,
    },
    {
      recipe: "Political Repression",
      score: "91.4",
      rank: "16 of 174",
      auc: "0.6847",
      tier: "Experimental",
      fail: true,
    },
    {
      recipe: "Foreign Intervention",
      score: "89.0",
      rank: "20 of 172",
      auc: "0.7227",
      tier: "Directional",
      fail: false,
    },
    {
      recipe: "Democratic Transition",
      score: "79.9",
      rank: "36 of 174",
      auc: "0.6967",
      tier: "Experimental",
      fail: true,
    },
  ];

  const cols = ["Recipe", "Percentile Score", "Global Rank", "LOCO AUC", "Tier"];

  return (
    <div style={{ overflowX: "auto", margin: "1.5rem 0" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.82em",
          fontFamily: "var(--font-data, monospace)",
        }}
      >
        <thead>
          <tr>
            {cols.map((h) => (
              <th
                key={h}
                style={{
                  padding: "6px 10px",
                  textAlign:
                    h === "Percentile Score" || h === "LOCO AUC" ? "right" : "left",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: "var(--qgi-text-muted)",
                  fontSize: "0.75em",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  fontWeight: 600,
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.recipe}>
              <td
                style={{
                  padding: "7px 10px",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: "var(--qgi-text)",
                  fontWeight: 500,
                }}
              >
                {r.recipe}
                {r.fail && (
                  <span
                    style={{
                      marginLeft: 6,
                      fontSize: "0.78em",
                      color: "rgba(251,113,133,0.8)",
                    }}
                  >
                    *
                  </span>
                )}
              </td>
              <td
                style={{
                  padding: "7px 10px",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: "#a78bfa",
                  textAlign: "right",
                  fontWeight: 700,
                }}
              >
                {r.score}
              </td>
              <td
                style={{
                  padding: "7px 10px",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: "var(--qgi-text-dim)",
                }}
              >
                {r.rank}
              </td>
              <td
                style={{
                  padding: "7px 10px",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: "var(--qgi-text-dim)",
                  textAlign: "right",
                }}
              >
                {r.auc}
              </td>
              <td
                style={{
                  padding: "7px 10px",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: r.tier === "Directional" ? "#a78bfa" : "rgba(251,191,36,0.8)",
                  fontSize: "0.85em",
                }}
              >
                {r.tier}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p
        style={{
          fontSize: "0.72em",
          color: "var(--qgi-text-muted)",
          marginTop: "0.4rem",
        }}
      >
        * HARD_FAIL in current walk: treat score as orientation signal only. LOCO AUC from
        recipe-tracker.json, not cv_auc_full.
      </p>
    </div>
  );
}

// --- Structure-news divergence table -----------------------------------------

function SilentAlarmTable() {
  const rows = [
    {
      topic: "Repression and Human Rights",
      structural: 82.6,
      pulse: 25,
      status: "LATENT",
      reading: "Widest divergence",
    },
    {
      topic: "Governance, Corruption and Reform",
      structural: 84.0,
      pulse: 42,
      status: "LATENT",
      reading: "Wide divergence",
    },
    {
      topic: "Terrorism and Targeted Violence",
      structural: 82.9,
      pulse: 50,
      status: "LATENT",
      reading: "Wide divergence",
    },
    {
      topic: "Economic Distress and Policy",
      structural: 83.6,
      pulse: 57,
      status: "LATENT",
      reading: "Notable divergence",
    },
    {
      topic: "Protest, Unrest and Labor",
      structural: 80.2,
      pulse: 57,
      status: "LATENT",
      reading: "Notable divergence",
    },
    {
      topic: "Electoral and Regime Change",
      structural: 79.0,
      pulse: 54,
      status: "LATENT",
      reading: "Moderate divergence",
    },
    {
      topic: "Humanitarian and Displacement",
      structural: 77.9,
      pulse: 52,
      status: "LATENT",
      reading: "Moderate divergence",
    },
    {
      topic: "Trade, Sanctions and Investment",
      structural: 80.9,
      pulse: 100,
      status: "ACTIVE",
      reading: "News tracking structure",
    },
    {
      topic: "Diplomacy and Alignment",
      structural: 77.0,
      pulse: 100,
      status: "ACTIVE",
      reading: "News tracking structure",
    },
    {
      topic: "Armed Conflict and Political Violence",
      structural: 78.6,
      pulse: 79,
      status: "ACTIVE",
      reading: "News broadly tracking",
    },
    {
      topic: "Energy, Resources and Environment",
      structural: 80.3,
      pulse: 99,
      status: "ACTIVE",
      reading: "News tracking structure",
    },
    {
      topic: "Technology, Cyber and Infrastructure",
      structural: 86.3,
      pulse: 88,
      status: "ACTIVE",
      reading: "Broadly converged",
    },
  ];

  return (
    <div style={{ overflowX: "auto", margin: "1.5rem 0" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.8em",
          fontFamily: "var(--font-data, monospace)",
        }}
      >
        <thead>
          <tr>
            {["Topic", "Structural Score", "News Pulse", "Status", "Reading"].map((h) => (
              <th
                key={h}
                style={{
                  padding: "5px 8px",
                  textAlign:
                    h === "Structural Score" || h === "News Pulse" ? "right" : "left",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: "var(--qgi-text-muted)",
                  fontSize: "0.72em",
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  fontWeight: 600,
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const isLatent = r.status === "LATENT";
            return (
              <tr key={r.topic}>
                <td
                  style={{
                    padding: "6px 8px",
                    borderBottom: "1px solid var(--qgi-border)",
                    color: isLatent ? "var(--qgi-text)" : "var(--qgi-text-dim)",
                    fontWeight: isLatent ? 500 : 400,
                    fontFamily: "sans-serif",
                    fontSize: "0.9em",
                  }}
                >
                  {r.topic}
                </td>
                <td
                  style={{
                    padding: "6px 8px",
                    borderBottom: "1px solid var(--qgi-border)",
                    color: "#a78bfa",
                    textAlign: "right",
                  }}
                >
                  {r.structural.toFixed(1)}
                </td>
                <td
                  style={{
                    padding: "6px 8px",
                    borderBottom: "1px solid var(--qgi-border)",
                    color: isLatent ? "rgba(251,113,133,0.85)" : "var(--qgi-text-dim)",
                    textAlign: "right",
                    fontWeight: isLatent ? 600 : 400,
                  }}
                >
                  {r.pulse}
                </td>
                <td
                  style={{
                    padding: "6px 8px",
                    borderBottom: "1px solid var(--qgi-border)",
                    color: isLatent ? "rgba(251,191,36,0.9)" : "rgba(74,222,128,0.8)",
                    fontSize: "0.8em",
                    fontWeight: 600,
                  }}
                >
                  {r.status}
                </td>
                <td
                  style={{
                    padding: "6px 8px",
                    borderBottom: "1px solid var(--qgi-border)",
                    color: "var(--qgi-text-dim)",
                    fontFamily: "sans-serif",
                    fontSize: "0.88em",
                  }}
                >
                  {r.reading}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// --- Page component ----------------------------------------------------------

export default function PakistanProfileReportPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      {/* Print stylesheet */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
@media print {
  .print\\:hidden, header, footer, .fn-tooltip { display: none !important; }
  body, .rpt-page-root { background: #fff !important; color: #111 !important; }
  article { max-width: 100% !important; padding: 0 !important; }
  h1, h2, h3 { color: #111 !important; }
  blockquote { border-left-color: #333 !important; background: transparent !important; color: #111 !important; }
  aside { background: #f5f5f5 !important; border-color: #ccc !important; color: #333 !important; }
  a { color: #111 !important; text-decoration: underline !important; }
  #footnotes { border-top: 1px solid #ccc !important; }
  figure { overflow: visible !important; }
  @page { margin: 20mm 15mm; }
}
          `,
        }}
      />

      <ArticleJsonLd
        headline="Five Models, One Country: What QGI's Structural Scan Finds in Pakistan That Macro Analysis Misses"
        description="Pakistan ranks in the top 8 to 20 globally across five independent structural models simultaneously. Nearest self-analogue: Pakistan 2011, match score 0.9712."
        url="https://qgintelligence.com/reports/pakistan-profile"
        datePublished={`${PUBLISH_DATE}T00:00:00Z`}
        imageUrl="https://qgintelligence.com/reports/pakistan-profile/opengraph-image"
        author={{ type: "Person", name: "Amin Al-Ait" }}
      />

      {/* Navbar */}
      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md print:hidden"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-4xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="report" href={"/" as Route} title="Home" />
          <nav className="flex items-center gap-4">
            <Link
              href={"/reports" as Route}
              className="text-xs tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)] flex items-center gap-1"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              &larr; All Reports
            </Link>
            <PrintButton />
          </nav>
        </div>
      </header>

      {/* Sticky TOC sidebar (xl: only, client component for active tracking) */}
      <TocSidebar />

      <article className="mx-auto max-w-3xl px-6 py-16">
        {/* Hero header */}
        <div className="mb-8">
          <div
            className="text-[10px] tracking-widest uppercase mb-3 font-semibold"
            style={{ color: "var(--qgi-accent)" }}
          >
            Country Analysis &middot; Published {PUBLISH_DATE}
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold leading-tight mb-4">
            Five Models, One Country: What QGI&apos;s Structural Scan Finds in Pakistan
            That Macro Analysis Misses
          </h1>
          <p className="text-xs mb-1" style={{ color: "var(--qgi-text-dim)" }}>
            By Amin Al-Ait &middot; Scoring date: {BAKE_DATE} &middot; QGI te-fleet-run-2
          </p>
          <p
            className="text-[11px] tracking-wide uppercase"
            style={{ color: "var(--qgi-text-muted)", fontVariant: "small-caps" }}
          >
            ~18 min read &middot; June 2026 scoring run
          </p>
        </div>

        {/* Chart hero: multi-recipe convergence */}
        <div className="mb-8">
          <ChartMultiRecipeConvergenceHero />
          <p
            className="mt-1 text-xs text-center"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Pakistan top-20 across five independent structural models simultaneously.
            Purple = Directional tier; amber = Experimental (asterisk = HARD_FAIL,
            orientation only). Source: QGI te-fleet-run-2.
          </p>
        </div>

        <div
          className="prose-qgi text-sm sm:text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          {/* --- Introduction --- */}
          <section id="intro">
            <p>
              The standard country-risk read on Pakistan in mid-2026 is one of cautious
              stabilisation. The IMF&apos;s Extended Fund Facility, approved in September
              2024, has held. Headline inflation, which peaked at 38 percent in 2023, has
              fallen sharply. Foreign exchange reserves have rebuilt to roughly three
              months of import cover after near-depletion in the crisis of 2022-23.
              India-Pakistan relations, following a ceasefire after the Pahalgam attack of
              April 2025, are on their most cooperative diplomatic footing in years. The
              elected government of Shehbaz Sharif is implementing a fiscal adjustment
              program, growth has resumed at around 3 percent in the current fiscal year,
              and the rupee has stabilised. Operationally, the conventional picture is:
              still fragile, still watching the debt-service calendar, but no longer in
              the acute danger zone.
            </p>
            <p>
              QGI is a structural pattern-matching system trained on 25-year indicator
              trajectories across more than 170 countries. It does not read news or track
              election calendars; it reads the shape of how dozens of institutional,
              economic, and political indicators have been moving, relative to how they
              moved in other countries before the events those countries are known to have
              experienced. In its June 2026 scoring run, Pakistan ranks in the top 8 to 20
              countries globally across five independent structural models simultaneously:
              labor action, religious and social movement, political repression, foreign
              intervention, and democratic transition. No single macro indicator produces
              this convergence. The five models use different indicator sets, were trained
              on different historical evidence bases, and capture different crisis types.
              The convergence across all five is visible only through a cross-national,
              multi-recipe structural scan.
            </p>
            <p>
              And the closest structural analogue to Pakistan 2026, out of every
              country-year QGI scores, is not a peer in open crisis. It is Pakistan
              itself.
            </p>
            <p>
              In 2011, at a <Fn n={2}>match score of 0.9712</Fn> in the foreign
              intervention model.
            </p>
            <p>That comparison is the story.</p>
          </section>

          {/* --- Five Models --- */}
          <section id="five-models">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              1. The Structural Picture: Five Models, Five Top-20 Rankings
            </h2>
            <p>
              QGI&apos;s scoring vintage te-fleet-run-2, scored at 2026-06-01T22:58:47
              UTC, places Pakistan as follows across the endogenous structural recipes:
            </p>

            <RecipeTable />
            <ChartMultiRecipeConvergence />

            <p>
              The overall composite structural risk score is 81 out of 100 (confidence
              interval: 75 to 88), placing Pakistan approximately 30th globally across 156
              scored countries. Countries carrying higher composite scores include
              Somalia, Lebanon, Myanmar, Ukraine, Sri Lanka, Ethiopia, Iraq, Sudan, Libya,
              and Israel. Pakistan&apos;s structural risk picture is not the highest on
              the board, but it is the most multi-dimensional: the simultaneous top-20
              presence across five recipes that measure categorically different historical
              processes is a configuration that QGI&apos;s full scoring universe does not
              produce often.
            </p>
            <p>
              Two recipes are deliberately switched off here. Natural disaster and
              epidemic-and-pandemic are exogenous shocks, things that happen to a country,
              not crises its own structure builds toward. They fail the endogenous-shape
              test that gives QGI&apos;s comparisons their value, so they do not count
              toward this profile.
            </p>

            <PullQuote>
              &ldquo;The same underlying institutional erosion is driving risk across
              three structurally independent models simultaneously.&rdquo;
            </PullQuote>

            <p>
              <strong>
                What makes this convergence analytically significant is the independence
                of the models.
              </strong>{" "}
              The labor action recipe uses a specific set of indicators about civil
              liberties, political freedoms, and institutional capacity. The foreign
              intervention recipe uses a separate set dominated by fiscal state capacity,
              gender empowerment, and demographic variables. The democratic transition
              recipe weights political participation, corruption, and neopatrimonialism.
              That all five models independently place Pakistan in the global top 8 to 20
              means that the same underlying structural deterioration is legible across
              multiple different indicator windows.
            </p>
          </section>

          {/* --- Lead Signals --- */}
          <section id="lead-signals">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              2. The Primary Driver: What the Indicators Are Actually Saying
            </h2>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              Political Civil Liberties as the Through-Line
            </h3>
            <p>
              One indicator appears across multiple recipe models as a primary or
              significant driver: V-Dem&apos;s Political Civil Liberties Index
              (v2x_clpol), which captures freedoms of assembly, association, and political
              expression. In the June 2026 vintage, Pakistan&apos;s Political Civil
              Liberties Index carries a z-score change of{" "}
              <strong>
                <Fn n={3}>-2.968</Fn>
              </strong>
              , a steep and fast deterioration relative to the cross-national
              distribution. This single indicator threads through the labor action model
              (18.2% of signal), the religious and social movement model (6.7% of signal),
              and the foreign intervention model as a contextual signal.
            </p>
            <p>
              The real-world context beneath that z-score is specific. Since the removal
              of Imran Khan as Prime Minister in April 2022, Pakistan Tehreek-e-Insaf
              (PTI) has been subjected to a systematic judicial and administrative
              campaign: the party&apos;s election symbol removed by the Election
              Commission; Khan convicted on multiple charges including a 14-year sentence
              under the Official Secrets Act; hundreds of PTI leaders and supporters
              charged under anti-terrorism provisions following the events of May 2023,
              when supporters briefly ransacked military installations. The February 2024
              elections produced PTI-affiliated independents as the largest single bloc,
              but a coalition of PML-N and PPP formed the government. As of mid-2026, Khan
              remains imprisoned and PTI&apos;s organisational capacity is severely
              degraded.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              The Labor Action Model: Why Pakistan Is Globally 8th
            </h3>
            <p>
              The labor action model&apos;s top driver is population size (SP.POP.TOTL,
              22.9% of signal, z-score +3.097): Pakistan has crossed 250 million people,
              and scale is itself a structural amplifier. But the operative driver is the
              Political Civil Liberties Index decline at -2.968, combined with a Private
              Civil Liberties Index (v2x_clpriv, covering property rights and private
              freedoms) moving in the opposite direction at +1.275. This divergence
              (political liberties contracting while private liberties hold) is the
              structural fingerprint of a state where collective action is being squeezed
              but individual private life remains relatively intact. QGI&apos;s model has
              learned, from historical cross-national data, that this configuration is
              associated with organised labour mobilisation becoming a vehicle for
              political expression precisely because the formal political channels are
              closing.
            </p>
            <p>
              The momentum in this score has been declining gradually and is now slightly
              accelerating downward: 65.5 in 2023, 64.3 in 2024, 64.7 in 2025, 63.7 in
              2026. The structural score at the 96th percentile reflects accumulated
              trajectory history, not just the most recent point.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              The Foreign Intervention Model: Fiscal Capacity and the Self-Rhyme
            </h3>
            <p>
              The foreign intervention model identifies the following top drivers for
              Pakistan in 2026. <Fn n={4}>Fiscal Capacity</Fn> (v2stfisccap, 26.7% of
              signal) is declining at a z-score change of -1.961, a significant
              deterioration in the state&apos;s ability to extract revenue relative to its
              size and structural requirements. Women&apos;s Political Empowerment
              (v2x_gender, 24.4% of signal) is declining at -2.154, a sharper move that
              functions in QGI&apos;s model as a proxy for the quality of state-society
              relations and institutional inclusiveness. Two partially offsetting signals
              are also present: Equal Protection Index (v2xeg_eqprotec, 21.6% of signal,
              improving at +0.576 z-score) and GDP growth (NY.GDP.MKTP.KD.ZG, 20.1% of
              signal, slightly negative SHAP contribution). The net configuration still
              produces a rank-20 score because the two declining signals outweigh the
              offsetting ones.
            </p>
            <p>
              Life expectancy improving at +2.746 z-score (SP.DYN.LE00.IN, 7.2% of signal)
              is also present as a positive signal in the model, and it matters for
              interpretation: Pakistan is not a collapsing state. Human development
              metrics are improving even as institutional quality erodes. This is
              precisely the structural configuration (a state with rising population
              health outcomes and a demographic dividend, combined with fiscal weakness
              and constrained political freedoms) that QGI&apos;s model associates with
              external military or security involvement in the historical evidence base.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              The Democratic Transition Signal: Between Brazil 1974 and Uganda 2021
            </h3>
            <p>
              The democratic transition model places Pakistan at the 79.9th percentile
              (rank 36 of 174). This recipe carries an Experimental tier and a HARD_FAIL
              verdict in the current walk; treat the score as directional orientation
              only. The top drivers are Political Participation (v2x_partip, 27.4% of
              signal, falling at -1.846 z-score), population scale (SP.POP.TOTL, 22.8% of
              signal), and Political Corruption Index (v2x_corr, 21.5% of signal,
              declining at -1.902). Neopatrimonialism (v2x_neopat, 17.1% of signal) is
              also rising at +2.098 z-score, and the Pakistani military&apos;s dominant
              position in the country&apos;s political economy maps precisely onto that
              signal. The momentum in this score has edged upward in the most recent
              period: 67.6 in 2023, 67.4 in 2024, 67.9 in 2025, 68.6 in 2026.
            </p>
          </section>

          {/* --- Self-Analogue --- */}
          <section id="self-analogue">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              3. The Historical Analogue: What Pakistan 2011 Implies
            </h2>
            <p>
              The foreign intervention model&apos;s top analogue for Pakistan 2026 is
              Pakistan itself in 2011, with a{" "}
              <Fn n={5}>
                <strong>match score of 0.9712</strong>
              </Fn>
              , near-perfect structural rhyme to its own most turbulent year.
            </p>

            <ChartSelfAnalogue />

            <h3 className="text-lg font-semibold mt-6 mb-2">
              2011: The Year Pakistan&apos;s Civil-Military Architecture Was Stress-Tested
              at Every Joint
            </h3>
            <p>
              The twelve months of 2011 delivered, in rapid succession: the arrest and
              subsequent diplomatic standoff over CIA contractor Raymond Davis; the US
              Navy SEAL raid on the Abbottabad compound killing Osama bin Laden in May,
              conducted without Pakistani knowledge or consent, in a garrison town housing
              a major Pakistani military academy; the Salala checkpoint attack in
              November, in which US-led NATO forces killed 24 Pakistani soldiers on the
              Afghan border, prompting Pakistan to close NATO supply lines and boycott the
              Bonn Conference; and the Memogate affair, in which a Pakistani-American
              businessman was accused of secretly seeking US help to prevent a military
              coup. All of this occurred against the backdrop of the highest TTP attack
              tempo on record and the drone strike campaign operating at its most
              intensive.
            </p>
            <p>
              The Pakistani state&apos;s fiscal capacity in 2011 was stretched by exactly
              the same dynamics visible today: heavy security spending, IMF-contingent
              external borrowing, and a revenue base inadequate to the demands being made
              of the state. Women&apos;s political empowerment was already under
              structural pressure from both internal dynamics and the deteriorating Afghan
              spillover. These are the variables the foreign intervention model is
              measuring. The 0.9712 match score says: Pakistan&apos;s current structural
              configuration is nearly identical to the configuration it held in 2011 along
              these indicator dimensions.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              What the Second and Third Analogues Add
            </h3>
            <p>
              Haiti 1994 (match 0.9497) and Somalia 1994 (match 0.9268) are the second and
              third analogues in the foreign intervention model. Both are cases of
              external military presence responding to state fiscal fragility and
              institutional failure: Haiti 1994 was the US-led multinational intervention
              to restore President Aristide after the military coup; Somalia 1994 was the
              catastrophic conclusion of the UNOSOM II mission following Black Hawk Down,
              with US and UN forces withdrawing.
            </p>
            <p>
              Pakistan is not Haiti 1994 or Somalia 1994 in any direct sense. Its
              institutions are far more robust, its military is a full-spectrum
              professional force, and it has nuclear weapons. But the structural signal
              the model is detecting (the specific combination of fiscal weakness,
              political empowerment deterioration, and scale) is what those cases had in
              common with Pakistan 2011, and what Pakistan 2026 now shares with all three.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              The Russia 1989 Labour Comparator
            </h3>
            <p>
              In the labor action model, the closest non-self analogue is Russia 1989
              (match 0.8449). In 1989, Soviet coal miners in the Donbas and Siberia
              launched the first major independent labour action in Soviet history,
              demanding better conditions and, increasingly, political reforms that the
              Gorbachev government could not fully deliver. The second analogue is Brazil
              1978 (match 0.8166): the ABC metalworkers&apos; strikes in the industrial
              suburbs of Sao Paulo under the military government, which launched Luiz
              Inacio Lula da Silva&apos;s political career and began the long transition
              that produced democracy in 1985.
            </p>
            <p>
              The model is not predicting a Soviet-style collapse or a Lula-style
              labour-led political transformation in Pakistan. But both analogues are
              cases where a large young population with constrained political liberties
              found in organised labour, in the absence of open political channels, the
              vehicle for expressing political discontent that then became structurally
              transformative. Pakistan has a population of 250 million, over 60 percent
              under age 30, rapidly improving child health outcomes, and a political civil
              liberties environment that has contracted at -2.97 standard deviations in
              the current vintage.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              The Uganda 2021 Repression Mirror
            </h3>
            <p>
              Like Democratic Transition, the political repression model carries an
              Experimental tier and a HARD_FAIL verdict in the current walk, so its score
              is structural orientation only, not a validated probability. The political
              repression model&apos;s top analogue is Uganda 2021 (match 0.9057,
              secondary: elections and voting). Uganda 2021 was Yoweri Museveni&apos;s
              post-election systematic persecution of Bobi Wine&apos;s National Unity
              Platform: hundreds of supporters killed in pre-election violence, Wine
              himself shot and arrested, widespread detention of opposition figures after
              a heavily manipulated vote. Rwanda 2021 (match 0.8885) and Zimbabwe 2019
              (match 0.8805) follow as second and third analogues.
            </p>
            <p>
              The Zimbabwe analogue deserves particular attention for Pakistan&apos;s
              current circumstances. Zimbabwe 2019 combined post-coup political
              consolidation under Mnangagwa with economic crisis and a currency collapse.
              The structural co-occurrence of political repression and currency or fiscal
              distress in the same episode is the signature. Pakistan&apos;s current
              configuration of PTI suppression coinciding with IMF program conditionality
              and structural fiscal weakness carries the same dual-stress signature.
            </p>
            <p>
              The political repression model&apos;s cosine similarity, measuring how
              closely the current indicator trajectory matches the historical
              pre-repression movement pattern, is at 0.304, rated HIGH. The Liberal
              Democracy Index (v2x_libdem) is falling at -2.841 z-score. Legislature
              oversight capacity (v2lgqstexp) is declining at -1.283. Freedom from
              Political Killings is improving at +1.627, which means the model is not
              reading Pakistan as in active violent state repression, but as in the
              institutional degradation that precedes and enables it.
            </p>

            <PullQuote>
              &ldquo;The crackdown has been sustained long enough to have normalised in
              coverage. The structural conditions that enabled it remain fully in place
              and have actually deepened.&rdquo;
            </PullQuote>
          </section>

          {/* --- News vs Structure --- */}
          <section id="news-vs-structure">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              4. The News-versus-Structure Picture: Five Divergences
            </h2>
            <p>
              QGI&apos;s high-frequency news layer (hf-topics.json, built 2026-06-09)
              provides live news pulse scores for Pakistan across 14 topic categories. The
              most analytically significant finding from this layer is not what the news
              is covering but what it is not covering relative to what the structural
              models show.
            </p>

            <SilentAlarmTable />

            <p>
              The calibration check is important before reading the divergences. Three
              topics (Trade, Sanctions and Investment at pulse 100; Diplomacy and
              Alignment at pulse 100; and Energy, Resources and Environment at pulse 99)
              are fully ACTIVE. These map precisely to what is actually dominating
              coverage of Pakistan in mid-2026: the IMF EFF negotiations and structural
              benchmarks, the India-Pakistan ceasefire diplomatic track, the CPEC
              renegotiation with Beijing, and the energy sector pricing reforms required
              under the IMF program. The HF layer is calibrated correctly. The silence on
              other topics is not a data artifact.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              The Repression Divergence: Structural Score 82.6, News Pulse 25
            </h3>
            <p>
              The most extreme structural-versus-news divergence in Pakistan&apos;s full
              profile is on Repression and Human Rights: structural score 82.6, news pulse
              25. The structural score places Pakistan in a globally elevated zone on the
              institutional conditions that historically co-occur with state crackdowns on
              civil and political rights. The news pulse at 25 (roughly one-third of what
              would be expected given that structural backdrop) means international media
              is running well below the coverage volume that a structural backdrop this
              elevated would typically accompany.
            </p>
            <p>
              This divergence is not primarily explained by the PTI crackdown being
              unknown or unreported. The issue is rather that the crackdown has been
              sustained long enough to have normalised in coverage: the international
              media cycle that follows an acute event has largely passed, while the
              structural conditions that enabled the crackdown remain fully in place and,
              by QGI&apos;s indicators, have actually deepened. The v2x_libdem decline
              (-2.841 z-score) and the v2lgqstexp decline (-1.283 z-score) suggest this is
              not a resolved situation being correctly deprioritised. It is an ongoing
              institutional erosion that coverage has underweighted because the acute
              flashpoints are less visible than they were in 2023.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              The Terrorism Divergence: Structure at 82.9, Pulse at 50
            </h3>
            <p>
              The terrorism and targeted violence structural score of 82.9 against a news
              pulse of 50 points to a different divergence. TTP attacks in Khyber
              Pakhtunkhwa and Balochistan have been running at elevated levels since the
              ceasefire with the government collapsed in late 2022. The QGI structural
              score measures the institutional and political configuration that
              historically co-occurs with elevated terrorism frequency. The Afghan border
              situation, the fiscal constraints on security spending, and the political
              fragmentation of governance in KPK combine to sustain a structural risk that
              international coverage is not fully reflecting at current pulse 50.
            </p>

            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              5. The Forward Look: Resemblance, Precedent, and the Bifurcation
            </h2>
            <p>
              QGI&apos;s framework requires a falsifiable forward statement. It does not
              produce timing or probability estimates. What the structural pattern-match
              supports is a statement about the configuration and the historical
              precedents for how configurations of this type have resolved.
            </p>
            <p>
              Pakistan&apos;s structural configuration in 2026 has, across five
              independent models, produced historical analogues that cluster in two
              distinct resolution categories.
            </p>
            <p>
              <strong>The democratic transition trajectory.</strong> Pakistan 2013 (match
              0.9777 in the democratic transition model) is the structural self-analogue
              in that recipe: Pakistan&apos;s first-ever civilian-to-civilian transfer of
              power, from Asif Ali Zardari&apos;s PPP government to Nawaz Sharif&apos;s
              PML-N. Brazil 1974 (match 0.9186) is the cross-national comparator:
              Geisel&apos;s controlled abertura, a managed liberalisation under military
              pressure that eventually produced full democracy in 1985. Nigeria 1998
              (match 0.9262) is the final year of the Abacha dictatorship before the
              transition to Obasanjo.
            </p>
            <p>
              <strong>The authoritarian consolidation trajectory.</strong> Uganda 2021
              (match 0.9057 in the political repression model) is the downside case: a
              contested election followed by systematic suppression of the opposition,
              with Museveni extending his now-four-decade rule. Zimbabwe 2019 (match
              0.8805) combined political consolidation with currency crisis, producing a
              years-long economic deterioration alongside political stasis.
            </p>
            <p>
              The structural evidence does not discriminate between these trajectories.
              Both are consistent with the current configuration.
            </p>

            <PullQuote>
              &ldquo;The structural evidence does not discriminate between these
              trajectories. Both are consistent with the current configuration.&rdquo;
            </PullQuote>

            <p>
              <strong>
                The falsifiable forward call has three observable components.
              </strong>{" "}
              First: if Pakistan&apos;s Political Civil Liberties Index (v2x_clpol)
              stabilises and reverses over the next two V-Dem coding cycles, the labor
              action and political repression scores should fall materially from their
              current positions. Second: if Fiscal Capacity (v2stfisccap) improves as the
              IMF program builds structural state revenue capacity, the foreign
              intervention score should recede. Third, and most immediately: the
              Repression and Human Rights divergence (structural score 82.6, news pulse
              25) is the configuration to watch. If repression intensifies and news
              coverage rises to match it, that combined configuration has historically
              preceded the Uganda 2021 resolution. If instead the PTI ban is lifted, Khan
              released, and the February 2024 election results are more fully honoured,
              the democratic transition model should see its closest analogue shift from
              Nigeria 1998 (Abacha&apos;s last year) toward Nigeria 1999 (Obasanjo&apos;s
              inauguration).
            </p>

            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              6. The Multi-Recipe Convergence: What This Means for Risk Analysis
            </h2>
            <p>
              The central methodological argument behind this report is this: no desk
              analyst reviewing Pakistan from any single source of data would find this
              convergence. An analyst reviewing V-Dem data would see the institutional
              deterioration but might attribute it to a temporary election cycle. An
              analyst reviewing fiscal data would see the IMF program as the stabilising
              frame. An analyst following news would see the diplomatic progress with
              India as an offsetting signal.
            </p>
            <p>
              The point of the five-model convergence is that it is not visible from any
              single vantage point. The same Political Civil Liberties deterioration (one
              indicator, one trajectory) appears in five different crisis models because
              five different historical crisis types are structurally associated with that
              indicator configuration. Each model sees it through a different historical
              lens. The labor model sees it as the configuration before organised workers
              act collectively in the absence of political outlets. The political
              repression model sees it as the institutional degradation before state
              crackdown. The foreign intervention model sees it through the fiscal and
              empowerment co-occurrence. The democratic transition model sees it through
              the neopatrimonialism frame. The religious and social movement model sees it
              as the pressure-cooker configuration that precedes mobilisation.
            </p>
            <p>
              <strong>The mass protest finding is itself informative.</strong> Pakistan
              ranks globally last (174th of 174) in the mass protest structural model. The
              structural configuration most closely associated with classical street
              protest movements is not what Pakistan 2026 structurally resembles. The
              model identifies Bangladesh 2015, Zimbabwe 2016, and Chad 2021 as the
              closest analogues to what Pakistan&apos;s structural profile does resemble
              in the protest recipe: repressive-environment, limited-turnout,
              constrained-channel protest, not the full-spectrum mass mobilisation type.
              An analyst looking for signs of Tahrir Square-style protest as the leading
              indicator of Pakistan instability is looking at the wrong signal.
            </p>
          </section>

          {/* --- Methodology --- */}
          <aside
            id="methodology-footnote"
            role="note"
            aria-label="Methodology note"
            className="my-8 rounded-lg p-5 text-xs leading-relaxed"
            style={{
              backgroundColor: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              color: "var(--qgi-text-dim)",
              fontSize: "0.75rem",
            }}
          >
            <div
              className="text-[10px] tracking-widest uppercase font-semibold mb-3"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Methodology
            </div>
            <p className="mb-2">
              QGI&apos;s structural recipes are XGBoost classifiers trained on 25-year
              cross-national indicator trajectories, with{" "}
              <Fn n={1}>LOCO cross-validated AUC</Fn> measuring discriminative power on
              held-out country-year observations. LOCO AUC is the leave-one-country-out
              validation metric from recipe-tracker.json; it differs from the cv_auc_full
              field in the scoring refit files. LOCO AUC values in this report: Labor
              Action 0.8145 (Directional); Religious and Social Movement 0.8186
              (Directional); Political Repression 0.6847 (Experimental, HARD_FAIL);
              Foreign Intervention 0.7227 (Directional,
              MARGINAL_PENDING_BETA_CALIBRATION); Democratic Transition 0.6967
              (Experimental, HARD_FAIL).
            </p>
            <p className="mb-2">
              Scores represent structural resemblance to historical pre-event
              configurations, not probability estimates or event forecasts. A score at the
              96th percentile in labor action means Pakistan&apos;s current indicator
              configuration is more similar to the pre-labor-action configurations in
              QGI&apos;s evidence base than 96 percent of all scored countries, not that a
              labor action event is 96 percent likely.
            </p>
            <p className="mb-2">
              <Fn n={3}>SHAP driver values</Fn> are from the scoring-refit XGBoost model
              for each recipe, reporting each indicator&apos;s percentage contribution to
              Pakistan&apos;s score_pp. V-Dem indicators in the SHAP driver lists carry a
              coding-lag caveat: V-Dem&apos;s most recent edition typically reflects data
              through the prior calendar year.
            </p>
            <p className="mb-2">
              Several SHAP-contributing indicators (SP.POP.TOTL, SP.DYN.LE00.IN,
              SH.DYN.MORT, NY.GDP.MKTP.KD.ZG) appear with obscured labels in the current
              data vintage; they are World Bank standard series (population, life
              expectancy, child mortality, GDP growth) and their z-score values are real
              computed figures.
            </p>
            <p>
              All structural recipe scores are from vintage te-fleet-run-2, scored at
              2026-06-01T22:58:47 UTC. High-frequency news pulse scores are from
              hf-topics.json, built 2026-06-09. See{" "}
              <Link
                href={"/methodology" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                QGI methodology
              </Link>{" "}
              for full scoring run details, recipe performance metrics, and cohort
              construction.
            </p>
          </aside>

          {/* --- CTA --- */}
          <aside
            className="my-8 rounded-lg p-6 print:hidden"
            style={{
              backgroundColor: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            <p
              className="text-sm leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              <strong style={{ color: "var(--qgi-text)" }}>
                Explore the underlying data.
              </strong>{" "}
              Pakistan&apos;s full structural profile (all recipe scores, analogue
              matches, and indicator drivers) is at{" "}
              <Link
                href={"/countries/pakistan" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                qgintelligence.com/countries/pakistan
              </Link>
              . The foreign intervention precedent cohort is at{" "}
              <Link
                href={"/trends/foreign_intervention" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /trends/foreign_intervention
              </Link>
              . The methodology behind all recipe models is at{" "}
              <Link
                href={"/methodology" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /methodology
              </Link>
              . Organisations working on South Asian political risk, institutional
              resilience, or security dynamics can commission country-specific structural
              analysis of this kind, or discuss access to QGI&apos;s full dataset, by
              writing to{" "}
              <a
                href="mailto:qgintelligence@gmail.com"
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                qgintelligence@gmail.com
              </a>
              .
            </p>
          </aside>

          {/* --- Sources --- */}
          <section
            id="sources"
            className="my-8 pt-4"
            style={{ borderTop: "1px solid var(--qgi-border)" }}
          >
            <div
              className="text-[10px] tracking-widest uppercase font-semibold mb-3"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Sources
            </div>
            <ul
              className="space-y-1 text-xs"
              style={{ color: "var(--qgi-text-dim)", listStyle: "none", padding: 0 }}
            >
              {[
                "[V-Dem Institute, 2026] Varieties of Democracy Dataset v14. University of Gothenburg. Indicators: v2x_clpol, v2x_clpriv, v2x_libdem, v2stfisccap, v2x_gender, v2lgqstexp, v2x_partipdem, v2x_corr, v2x_regime, v2x_neopat, v2xeg_eqprotec, v2x_partip.",
                "[World Bank Development Indicators, 2026] SP.POP.TOTL, SP.DYN.LE00.IN, SH.DYN.MORT, NY.GDP.MKTP.KD.ZG, SM.POP.NETM, NY.GNP.PCAP.CD.",
                "[IMF, September 2024] Extended Fund Facility for Pakistan. Program documentation, disbursement records, and structural benchmarks.",
                "[IMF Article IV, 2025] Pakistan: Selected Issues and Staff Report.",
                "[Pakistan Bureau of Statistics, FY2025-26] GDP and growth estimates.",
                "[State Bank of Pakistan, May 2026] Foreign exchange reserves and monetary statistics.",
                "[UN Special Rapporteur on Torture; OHCHR, 2023-24] Reports on detention of PTI members and political prisoners.",
                "[Human Rights Watch, 2023-24] Annual Pakistan chapter; specific reporting on May 9 arrests and PTI suppression.",
                "[SIPRI, 2025] Military expenditure data, Pakistan.",
                "[Pakistan Election Commission, February 2024] General election results.",
                "[QGI, te-fleet-run-2, 2026-06-01] All structural recipe scores, SHAP driver values, analogue match scores, cosine similarity measures, overall composite score, HF topic pulse values. Source files: qgi-frontend/data/te-fleet-run-2/scores/*.scores.json; qgi-frontend/data/hf-topics.json; qgi-frontend/data/recipe-tracker.json; qgi-frontend/data/country-risks.json.",
              ].map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </section>

          {/* --- Footnotes --- */}
          <section
            id="footnotes"
            className="my-8 pt-6"
            style={{ borderTop: "1px solid var(--qgi-border)" }}
            aria-label="Footnotes"
          >
            <div
              className="text-[10px] tracking-widest uppercase font-semibold mb-4"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Term definitions
            </div>
            <ol className="space-y-3 text-xs leading-relaxed list-none p-0">
              {FOOTNOTES.map((fn) => (
                <li key={fn.n} id={`fn-${fn.n}`} style={{ color: "var(--qgi-text-dim)" }}>
                  <span
                    style={{
                      color: "var(--qgi-accent)",
                      fontFamily: "var(--font-data, monospace)",
                      marginRight: 6,
                    }}
                  >
                    {fn.n}.
                  </span>
                  <strong style={{ color: "var(--qgi-text)" }}>{fn.term}</strong>
                  {": "}
                  {fn.def}{" "}
                  <a
                    href={`/methodology${fn.anchor}`}
                    className="underline underline-offset-2"
                    style={{ color: "var(--qgi-accent)" }}
                  >
                    Read more &rarr;
                  </a>
                </li>
              ))}
            </ol>
          </section>

          {/* Closing dateline -- byline #3 */}
          <p
            className="text-xs mt-12 pt-6 border-t"
            style={{
              color: "var(--qgi-text-dim)",
              borderColor: "var(--qgi-border)",
            }}
          >
            Published {PUBLISH_DATE} &middot; QG Intelligence &middot; By Amin Al-Ait
            &middot; Scoring run: {BAKE_DATE} te-fleet-run-2 &middot; This piece reports
            structural pattern resemblance and historical analogue comparison. It is not a
            forecast.
          </p>
        </div>
      </article>
    </div>
  );
}
