import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";
import Chart1SalienceBars from "./charts/Chart1SalienceBars";
import Chart2L1Comparison, { Chart2L1ComparisonHero } from "./charts/Chart2L1Comparison";
import Chart3FiscalTrajectory from "./charts/Chart3FiscalTrajectory";
import Chart4L1Profile from "./charts/Chart4L1Profile";
import TocSidebar from "./TocSidebar";
import PrintButton from "./PrintButton";

/**
 * Ghana's Double Signal: /reports route (V2 elevation from /blog).
 *
 * V2 changes vs V3 blog original:
 *  - Elevated to /reports/ghana-mauritania-mirror
 *  - Helena Marchetti soft-landing intro (198 words, verbatim)
 *  - Three pull-quotes per brief
 *  - End-of-piece CTA
 *  - 15-term citation-tooltip footnotes
 *  - Interactive chart hover states (client chart components)
 *  - Hero image = Chart 2 (900x400 render)
 *  - OG card = opengraph-image.tsx (1200x630 chart render)
 *  - Sticky table-of-contents (xl: breakpoint, IntersectionObserver)
 *  - Print stylesheet
 *
 * All quantitative claims unchanged from V3 manuscript.
 * Source scoring run: 2026-04-30, QGI V1.9.1.
 */

const BAKE_DATE = "2026-04-30";
const PUBLISH_DATE = "2026-05-19";

// ─── Metadata ─────────────────────────────────────────────────────────────────

export const metadata: Metadata = {
  title: "Ghana's Double Signal: QG Intelligence Report",
  description:
    "QGI places Ghana at the 99th percentile of global election-stress in its April 2026 scoring run. Its closest structural analogue is not Burkina Faso, it is Mauritania. That comparison is the story.",
  alternates: {
    canonical: "https://qgintelligence.com/reports/ghana-mauritania-mirror",
  },
  openGraph: {
    title:
      "Ghana's Double Signal: The Ballot Box, the Barracks, and the Country Nobody Expected",
    description:
      "QGI places Ghana at the 99th percentile of global election-stress. Its closest structural peer is Mauritania at 99% cosine similarity, not Mali, not Burkina Faso. What that structural resemblance means.",
    url: "https://qgintelligence.com/reports/ghana-mauritania-mirror",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: `${PUBLISH_DATE}T00:00:00Z`,
  },
  twitter: {
    card: "summary_large_image",
    title:
      "Ghana's Double Signal: The Ballot Box, the Barracks, and the Country Nobody Expected",
    description:
      "Ghana is at the 99th percentile of global election-stress. Its structural analogue is Mauritania. That comparison is the story.",
  },
  robots: { index: true, follow: true },
};

// ─── Footnote registry ─────────────────────────────────────────────────────────
// Footnotes are numbered in order of first appearance. Static registry kept
// here so the footnote list at the bottom and the inline markers are in sync.

const FOOTNOTES = [
  {
    n: 1,
    term: "99th percentile of global election-stress",
    def: "Ghana sits higher than 99% of the 131-country cohort on its Elections & Voting Precedent Match score; the percentile is a rank, not a probability.",
    anchor: "#aggregate-vs-per-recipe",
  },
  {
    n: 2,
    term: "Elections & Voting Precedent Match",
    def: "A per-recipe score (0–100) ranking how closely a country's current indicator trajectory resembles historical cases that preceded elections-related geopolitical events, within a cohort of countries that fire on that recipe.",
    anchor: "#aggregate-vs-per-recipe",
  },
  {
    n: 3,
    term: "99/100 [CI 97–100]",
    def: "The score is 99 out of 100; the bracketed range is a 95% bootstrap confidence interval showing the uncertainty around that estimate from repeated resampling.",
    anchor: "#bootstrap-ci",
  },
  {
    n: 4,
    term: "bootstrap CI",
    def: "A confidence interval calculated by resampling the data thousands of times to estimate how much the score would vary if measured on slightly different data; narrower intervals indicate more stable estimates.",
    anchor: "#bootstrap-ci",
  },
  {
    n: 5,
    term: "LOCO AUC 0.711",
    def: "Leave-One-Country-Out Area Under the Curve: a cross-validation metric measuring how well the recipe discriminates countries that later experienced an event from those that did not, after removing each country from its own training set; 0.5 = chance, 1.0 = perfect.",
    anchor: "#loco-auc",
  },
  {
    n: 6,
    term: "MODERATE evidence strength",
    def: "QGI's qualitative label for a LOCO AUC in the range that indicates the recipe performs meaningfully better than chance but is not in the highest confidence tier; the label travels with the recipe, not the country score.",
    anchor: "#loco-auc",
  },
  {
    n: 7,
    term: "calibration error of 0.012",
    def: "Expected Calibration Error (ECE): the average difference between a model's predicted probability and the actual observed event rate across score buckets; 0.012 means predictions are on average 1.2 percentage points off.",
    anchor: "#calibration-error",
  },
  {
    n: 8,
    term: "S-tier / M-tier / L-tier / XL-tier",
    def: "Pattern Length Tiers grouping historical precedent windows by duration: S = 3–8 years (policy cycles), M = 9–20 years (leadership eras), L = 21–40 years (structural shifts), XL = 41+ years; each tier captures a different type of structural dynamic.",
    anchor: "#pattern-tiers",
  },
  {
    n: 9,
    term: "salience z-score",
    def: "A measure of how unusual a country's score for a given risk category is relative to its own historical average, scaled in units of standard deviation (σ); z = 2.76 means the score is 2.76 standard deviations above that country's mean.",
    anchor: "#scoring",
  },
  {
    n: 10,
    term: "L1 risk profile",
    def: "An 8-dimension decomposition of a country's risk signal into the master categories of QGI's event taxonomy (Political, Conflict, Governance, Economic, Social, Diplomatic, Humanitarian, Structural); L1 is the first level of the taxonomy hierarchy.",
    anchor: "#l1-dimensions-and-peers",
  },
  {
    n: 11,
    term: "cosine similarity",
    def: "A geometric measure of how similar two countries' 8-dimension L1 risk vectors are, regardless of scale; 99% cosine similarity means the two risk profiles point in nearly the same direction across all active dimensions.",
    anchor: "#l1-dimensions-and-peers",
  },
  {
    n: 12,
    term: "8-dimension L1 risk profile",
    def: "The specific eight master categories (A through H) used in the current QGI taxonomy: Political Power & Regime, Conflict & Insurgency, Governance & Rule of Law, Economic & Financial Stress, Social & Civil Unrest, Diplomatic & Geopolitical, Humanitarian & Displacement, Structural Vulnerability.",
    anchor: "#l1-dimensions-and-peers",
  },
  {
    n: 13,
    term: "composite risk score 68/100",
    def: "The country-level QGI Risk Score: a single percentile rank summarising the strength of the country's overall salience signal against the scoring cohort; distinct from individual recipe Precedent Match scores.",
    anchor: "#aggregate-vs-per-recipe",
  },
  {
    n: 14,
    term: "Tier HIGH",
    def: "A country-level severity label (HIGH / MODERATE / INDICATIVE) assigned based on maximum salience across all patterns, with additional composite-promotion rules; HIGH requires sustained cross-category signal strength.",
    anchor: "#scoring",
  },
  {
    n: 15,
    term: "April 2026 scoring run",
    def: "A specific computation run of QGI's full pipeline on the April 2026 data snapshot; scores are tied to a scoring date because indicator data and model outputs change as new data arrives.",
    anchor: "#what-is-a-scoring-run",
  },
] as const;

// ─── Inline Footnote component ────────────────────────────────────────────────
// Server-compatible: uses CSS-only hover via :hover + focus-visible.
// The tooltip card appears on hover/focus; the term text wraps with
// a superscript marker.

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
      {/* Tooltip card: CSS :hover on .fn-wrap shows .fn-tooltip */}
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
          Read more →
        </a>
      </span>

      {/* CSS to make the tooltip appear on hover/focus */}
      <style>{`
        .fn-wrap:hover .fn-tooltip,
        .fn-wrap:focus-within .fn-tooltip {
          display: block !important;
        }
      `}</style>
    </span>
  );
}

// ─── Pull-quote component ─────────────────────────────────────────────────────

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

// ─── Page component ───────────────────────────────────────────────────────────

export default function GhanaMauritaniaReportPage() {
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
        headline="Ghana's Double Signal: The Ballot Box, the Barracks, and the Country Nobody Expected"
        description="QGI places Ghana at the 99th percentile of global election-stress in its April 2026 scoring run. Its closest structural analogue is not Burkina Faso, it is Mauritania."
        url="https://qgintelligence.com/reports/ghana-mauritania-mirror"
        datePublished={`${PUBLISH_DATE}T00:00:00Z`}
        imageUrl="https://qgintelligence.com/reports/ghana-mauritania-mirror/opengraph-image"
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
        {/* Hero */}
        <div className="mb-8">
          <div
            className="text-[10px] tracking-widest uppercase mb-3 font-semibold"
            style={{ color: "var(--qgi-accent)" }}
          >
            Country Analysis · Published {PUBLISH_DATE}
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold leading-tight mb-4">
            Ghana&apos;s Double Signal: The Ballot Box, the Barracks, and the Country
            Nobody Expected
          </h1>
          <p className="text-xs mb-1" style={{ color: "var(--qgi-text-dim)" }}>
            By Amin Al-Ait · Scoring date: {BAKE_DATE} · QGI V1.9.1
          </p>
          <p
            className="text-[11px] tracking-wide uppercase"
            style={{ color: "var(--qgi-text-muted)", fontVariant: "small-caps" }}
          >
            ~9 min read · April 2026 scoring run
          </p>
        </div>

        {/* Hero image: Chart 2 at 900×400 render */}
        <div className="mb-8">
          <Chart2L1ComparisonHero />
          <p
            className="mt-1 text-xs text-center"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Ghana vs Mauritania, 99% structural similarity, April 2026 scoring run.
            Source: QGI computation.
          </p>
        </div>

        <div
          className="prose-qgi text-sm sm:text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          {/* ── Helena's soft-landing intro (198 words, verbatim) ── */}
          <p>
            The standard read on Ghana is reassuring. Two peaceful transfers of power in
            the past decade. An IMF programme that survived a sovereign default and is now
            in its third review. A professional military that has held to the barracks
            since the Rawlings era ended in 1992. V-Dem, Freedom House, and Afrobarometer
            all point the same direction: Ghana is the exemplar of democratic
            consolidation in West Africa.
          </p>
          <p>
            QG Intelligence is a system that searches for structural resemblance between
            countries&apos; economic trajectories and historical precedents, running the
            numbers across 131 countries and hundreds of indicators to surface risk
            patterns that conventional desk analysis does not reach. In its{" "}
            <Fn n={15}>April 2026 scoring run</Fn>, Ghana scores at the{" "}
            <Fn n={1}>99th percentile of global election-stress</Fn> globally. Its top
            short-horizon risk category is not elections; it is military coup. And the
            country whose current economic and political risk fingerprint most closely
            matches Ghana&apos;s, out of every country in the 131-country cohort, is not
            Mali, not Burkina Faso, not any of the countries that analysts already watch
            for coup risk in West Africa.
          </p>
          <p>It is Mauritania.</p>
          <p>That comparison is the story.</p>

          {/* Section 1 */}
          <h2 id="signal" className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            1. The Signal: Two Numbers That Don&apos;t Belong Together
          </h2>
          <p>
            Ghana&apos;s{" "}
            <Fn n={2}>
              <Link
                href={"/trends/elections_and_voting" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Elections &amp; Voting
              </Link>{" "}
              Precedent Match
            </Fn>{" "}
            registers <Fn n={3}>99/100</Fn> [95% <Fn n={4}>bootstrap CI</Fn>:
            97&ndash;100] , placing it at the 99th percentile of a 131-country global
            cohort. Its top-salience risk category at the short-horizon window is not
            elections; it is Military Coup. And its closest structural analogue, at 99%{" "}
            <Fn n={11}>cosine similarity</Fn> on the{" "}
            <Fn n={12}>8-dimension L1 risk profile</Fn>, is not Mali or Burkina Faso or
            Niger. It is{" "}
            <Link
              href={"/countries/mauritania" as Route}
              className="underline underline-offset-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Mauritania
            </Link>
            .
          </p>
          <p>
            Ghana&apos;s{" "}
            <Link
              href={"/trends/elections_and_voting" as Route}
              className="underline underline-offset-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Elections &amp; Voting
            </Link>{" "}
            score of 99/100 [CI 97&ndash;100] is not alarming in isolation.
            Elections-related structural stress is common in countries navigating economic
            transitions and competitive party politics; the signal at any given moment
            captures more than coup risk. The recipe&apos;s <Fn n={5}>LOCO AUC 0.711</Fn>{" "}
            (<Fn n={6}>MODERATE evidence strength</Fn>) and{" "}
            <Fn n={7}>calibration error of 0.012</Fn> tell you it is a well-performing
            model, one of the more reliable in QGI&apos;s current validated set.
          </p>
          <p>
            What makes Ghana unusual is the{" "}
            <Fn n={8}>S-tier / M-tier / L-tier / XL-tier</Fn> progression. At the S-tier
            (short time-horizon window), Military Coup is Ghana&apos;s top-ranked risk
            category with a <Fn n={9}>salience z-score</Fn> of 1.39. Elections &amp;
            Voting is third. At the M-tier (medium window), Military Coup holds the top
            rank (salience 1.42); Elections &amp; Voting climbs to second (salience 1.14,
            z-score 1.90). At the L-tier (long window), Elections &amp; Voting surges to
            first (salience 1.66, z-score 2.76) with Military Coup holding second. At the
            XL-tier (longest window), Elections &amp; Voting dominates at z-score 2.38;
            Military Coup has dropped out of the top tier entirely.
          </p>

          <Chart1SalienceBars />

          <p>
            At short-horizon windows, the model is picking up coup-adjacent conditions as
            the dominant signal. At longer windows, the election-stress signature becomes
            primary. This is the structural fingerprint of a country where institutional
            stress is building across two timescales simultaneously, not a country with an
            acute crisis in one domain.
          </p>
          <p>
            QGI&apos;s <Fn n={13}>composite risk score 68/100</Fn> [CI 60&ndash;75],{" "}
            <Fn n={14}>Tier HIGH</Fn>. The recipe-level breakdown from the current scoring
            run shows Elections &amp; Voting at 99/100, Multilateral Agreement at 73/100
            [CI 55&ndash;90], and Bilateral Treaty at 27/100 [CI 19&ndash;34]. The wide CI
            on Multilateral Agreement reflects either model uncertainty or data-coverage
            thinness for Ghana&apos;s multilateral treaty history; either reading is
            consistent with the structural argument. Civil War and Insurgency produces a
            null result for Ghana; the model does not see conflict-state conditions. This
            is not the DRC profile. It is not the Sudan profile. The stress is
            specifically in the political-economy intersection where electoral legitimacy
            meets institutional fragility.
          </p>
          <p>
            The election-stress signal at the 99th percentile is available to any FT
            reader who follows Ghana. The simultaneous top-rank salience of Military Coup
            at short-horizon windows is what QGI adds. These two signals together
            constitute what I call the &ldquo;coup-by-election&rdquo; structural template:
            not a naked seizure of power, but a contested or destabilizing electoral
            outcome that becomes the pretext for military intervention. The framing
            matters because it points you toward a different historical template than the
            Burkina Faso or Mali junta model.
          </p>
          <p>
            A methodological note: the Military Coup category appears as top salience
            through a statistical classification layer within QGI&apos;s scoring engine,
            not from a dedicated LOCO-validated recipe. Ghana&apos;s four validated recipe
            scores are Elections &amp; Voting (99/100, LOCO AUC 0.711), Multilateral
            Agreement (73/100, LOCO AUC 0.869), Bilateral Treaty (27/100, LOCO AUC 0.668),
            and Civil War &amp; Insurgency (null). The Military Coup signal is
            directional, not model-validated. I am using it as a structural indicator, not
            as a forecast. The election-stress signal is the ML-validated load-bearing
            component; Military Coup is the contextual reinforcement.
          </p>

          {/* Pull-quote 1, between Section 1 and Section 2 */}
          <PullQuote>
            &ldquo;Ghana is not showing one risk; it is showing the precise combination
            that precedes coup-by-election, where a contested or destabilising electoral
            outcome becomes the pretext for military intervention.&rdquo;
          </PullQuote>

          {/* Section 2 */}
          <h2
            id="mauritania-mirror"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            2. The Mauritania Mirror: Why This Comparator Stops You
          </h2>

          <Chart2L1Comparison />

          <p>
            QGI identifies{" "}
            <Link
              href={"/countries/mauritania" as Route}
              className="underline underline-offset-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Mauritania
            </Link>{" "}
            as Ghana&apos;s closest structural analogue, with a cosine similarity of 99%
            on the <Fn n={10}>L1 risk profile</Fn>. Political Power &amp; Regime accounts
            for 66% of the cosine similarity, Economic &amp; Financial Stress for 24%, and
            Diplomatic &amp; Geopolitical Relations for 9%. The three shared active
            dimensions (A, D, and F in QGI&apos;s taxonomy) form the entire explanatory
            structure of the match. Ghana and Mauritania&apos;s risk fingerprints are not
            generally similar across all eight dimensions; they are precisely similar on
            the three dimensions that matter most for regime-political economy
            interactions.
          </p>
          <p>
            Mauritania does not appear on standard West Africa risk dashboards as a
            comparator for Ghana. The West Africa risk fraternity clusters Ghana
            comparisons around Senegal (similarly competitive electoral democracy),
            C&ocirc;te d&apos;Ivoire (larger Francophone economy), or, in the pessimistic
            register, Burkina Faso (post-2015 democratic fragility before the coups).
            Mauritania is off the standard mental map for Ghana analysis because the two
            countries sit in different subregional frames (Ghana Anglophone coastal,
            Mauritania Arabic-French Sahelian desert) and because their recent political
            trajectories appear to diverge. Ghana held credible elections in December
            2024. Mauritania is run by a general-turned-president who came to power
            through a coup.
          </p>
          <p>
            That apparent divergence is exactly why the structural similarity is
            analytically interesting.
          </p>
          <p>
            In August 2008, General Mohamed Ould Abdel Aziz overthrew President Sidi Ould
            Cheikh Abdallahi, a civilian elected in 2007 in what international observers
            called Mauritania&apos;s most credible election to that point. The pretext was
            Abdallahi&apos;s attempt to dismiss officers loyal to Aziz. The AU condemned
            the coup and suspended Mauritania; the EU froze development assistance. In
            2009, Aziz ran for president, won with 52% in a disputed but non-violently
            contested election, and was internationally recognized within months. His
            successor, Mohamed Ould Ghazouani, was his hand-picked former general.
          </p>
          <p>
            This is the &ldquo;soft coup with electoral normalization&rdquo; template. It
            differs from the Burkina Faso/Mali/Niger junta model in a structural way: the
            Mauritania template involves military intervention followed by electoral
            legitimation, not an indefinite suspension of the constitutional order. The
            coup leader runs for election and wins. The international community accepts
            the result, resets bilateral relations, and moves on. The AU deterrence
            mechanism, already weakened by the Sahel coups, was tested and passed the
            Mauritania case, in part because Aziz moved fast toward an electoral
            framework.
          </p>
          <p>
            The structural question for Ghana is not whether its military officer corps is
            currently planning a coup. Thirty years of civilian rule and the institutional
            memory of Rawlings-era interventions have created a genuine culture of
            military professionalism in the Ghana Armed Forces. The question is whether
            the cost-benefit calculus of intervention has shifted, whether the external
            deterrence that constrained the calculus has eroded, and whether the domestic
            conditions (fiscal deterioration, legitimacy stress, proximity to operational
            theaters) are accumulating.
          </p>
          <p>
            QGI&apos;s 99% cosine match with{" "}
            <Link
              href={"/countries/mauritania" as Route}
              className="underline underline-offset-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Mauritania
            </Link>{" "}
            says: the structural conditions that produce the soft-coup-with-normalization
            pattern are present in Ghana&apos;s indicator trajectory at a level of
            similarity the model finds historically meaningful. Mali and Burkina Faso
            offer the junta-with-no-timetable template: indefinite constitutional
            suspension, foreign security contractors, Russia-backed legitimation
            architecture. That is a different and more destabilizing outcome. The
            Mauritania template (intervention, quick elections, institutional continuity)
            is exactly the scenario where preventive engagement has the most leverage and
            the narrowest window. The distinction matters for policy more than it matters
            for risk scoring.
          </p>

          {/* Pull-quote 2, end of Section 2, before Section 3 */}
          <PullQuote>
            &ldquo;The Mauritania template (intervention, quick elections, institutional
            continuity) is exactly the scenario where preventive engagement has the most
            leverage and the narrowest window. The distinction matters for policy more
            than it matters for risk scoring.&rdquo;
          </PullQuote>

          {/* Section 3 */}
          <h2 id="forward-call" className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            3. The Forward Call: A Six-Month Trigger, Not a Year Target
          </h2>
          <p>
            The forward call is an event-trigger window, not a calendar target. The
            structural stress QGI is measuring does not wait for election day; in the
            Mauritania analogue, it materialized in the 18 months <em>between</em> a
            credible election and a coup. The near-term trigger runs through the IMF
            Extended Credit Facility review cycle. Ghana entered the ECF in 2023 and is in
            its third review, with disbursements contingent on continued fiscal
            consolidation. The Mahama government inherited Bawumia&apos;s debt
            restructuring architecture and must sustain it against an NDC base that ran on
            relief from austerity.{" "}
            <strong>
              The six-month watch window is May&ndash;November 2026: if Ghana misses an
              ECF disbursement trigger or requests a substantial program modification,
              accompanied by public-sector wage arrears or fuel subsidy rollbacks, the
              fiscal-legitimacy stress will register in QGI&apos;s next scoring cycle.
            </strong>{" "}
            That is the leading indicator.
          </p>

          <Chart3FiscalTrajectory />

          <p>
            <strong>The falsification scenario.</strong> The call is off if the Mahama
            government navigates the third and fourth ECF reviews without significant
            program modification, and if ECOWAS reconstitutes a credible deterrence
            framework through the Accra Initiative, giving Ghanaian military officers a
            named reputational cost for intervention. Both conditions holding by November
            2026 would signal that QGI&apos;s L-tier election-stress peak has decayed
            before reaching the Mauritania threshold.
          </p>
          <p>
            The moderate form is most probable: not a junta, not a clean democratic
            handover, but a period of elevated civil-military tension where the
            military&apos;s role as a fiscal-crisis stabilizer becomes politically central
            , exercised through informal veto power over economic policy rather than an
            overt seizure of government. A disputed 2028 electoral outcome resolved
            through military mediation (the Mauritania 2009 pattern) would confirm this
            scenario. A coup before November 2026 would confirm the extreme form. A clean
            second electoral cycle with no institutional crisis would falsify it.
          </p>

          {/* Pull-quote 3, end of Section 3, before Section 4 */}
          <PullQuote>
            &ldquo;A coup before November 2026 would confirm the extreme form. A clean
            second electoral cycle with no institutional crisis would falsify it.&rdquo;
          </PullQuote>

          {/* Section 4 */}
          <h2 id="gaps" className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            4. What QGI Doesn&apos;t See, And Why the Case Still Holds
          </h2>
          <p>Three named gaps warrant disclosure.</p>
          <p>
            <strong>Foreign security presence.</strong> QGI&apos;s indicator base (World
            Bank development indicators, V-Dem electoral quality scores, SIPRI arms
            transfer data) cannot see informal private military company (PMC) approaches.
            Wagner Group / Africa Corps has operated in Burkina Faso, in the operational
            theater that borders Ghana&apos;s northern corridor directly. The commercial
            logic of PMC deployments (mining concession revenue in exchange for security
            services) maps precisely onto Ghana&apos;s gold-exporting economy. This is not
            an assertion that PMC discussions are occurring; it is an observation that QGI
            would not surface them if they were. Field knowledge has to carry this.
          </p>
          <p>
            <strong>AES bloc-level political coherence.</strong> Niger&apos;s Elections
            &amp; Voting score is 93/100, placing it #10 globally in the same recipe
            cohort as Ghana. Niger sits directly north of Ghana&apos;s northern corridor.
            The Alliance des &Eacute;tats du Sahel has explicitly positioned itself as a
            peer legitimacy-granting structure, and a Ghanaian military government
            recognized by Bamako and Niamey would have a form of regional standing that
            did not exist before 2023. This bloc-level political reality is invisible to
            QGI&apos;s per-country scoring. It changes the expected consequences of a coup
            attempt from near-certain AU isolation (the 2008 Mauritania model) to a more
            ambiguous regional response.
          </p>
          <p>
            <strong>Civil society resilience.</strong>{" "}
            <Link
              href={"/countries/ghana" as Route}
              className="underline underline-offset-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Ghana
            </Link>
            &apos;s civil society (the Commission on Human Rights and Administrative
            Justice, the Ghana Centre for Democratic Development, the major media houses)
            proved robust during the 2008 election dispute, resolving a contested outcome
            within constitutional frameworks. QGI cannot measure institutional resilience
            directly; it measures indicator trajectories. The Mauritania analogue involved
            weaker civil society. This is the most important reason Ghana&apos;s
            structural risk, conditional on the indicator conditions being met, may be
            lower than the cosine similarity alone implies.
          </p>
          <p>
            Despite these gaps, the structural case holds because of what QGI can see: the
            deteriorating fiscal-political trajectory in Ghana&apos;s Economic &amp;
            Financial Stress dimension (salience 1.01 on the L1 profile), the Political
            Power &amp; Regime dimension at maximum salience in the current scoring run
            (1.66, the same dimension that accounts for 66% of the Ghana-Mauritania cosine
            match), and the election-stress recipe at the 99th percentile of a validated
            global cohort. The gaps do not negate the structural reading; they bound the
            probability and shape the intervention options.
          </p>

          <Chart4L1Profile />

          {/* Methodology footnote */}
          <aside
            id="methodology-footnote"
            role="note"
            aria-label="Methodology footnote"
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
              QGI data: Elections &amp; Voting Precedent Match 99/100 [CI 97&ndash;100]
              &middot; LOCO AUC 0.711 &middot; ECE 0.012 &middot; Cohort N=131 &middot;
              QGI Risk Score 68/100 [CI 60&ndash;75] &middot; Tier HIGH &middot; Political
              Power &amp; Regime L1 salience 1.66 (peak at L-tier window, z-score 2.76)
              &middot; Military Coup top salience at S-tier (z=1.39) and M-tier (z=1.42)
              &middot;{" "}
              <Link
                href={"/countries/mauritania" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Mauritania
              </Link>{" "}
              99% cosine peer (intersection-only cosine on shared active L1 dimensions
              A/D/F; Jaccard 0.75; composite similarity 74.3%) &middot; Per-dimension
              breakdown of cosine: Political Power &amp; Regime 66%, Economic &amp;
              Financial Stress 24%, Diplomatic &amp; Geopolitical Relations 9% &middot;
              Multilateral Agreement 73/100 [CI 55&ndash;90] &middot; Bilateral Treaty
              27/100 [CI 19&ndash;34] &middot; Civil War &amp; Insurgency: null &middot;
              April 2026 scoring run (generated {BAKE_DATE}) &middot; QGI V1.9.1 scoring.
            </p>
            <p className="mb-2">
              Methodology disclosures: (1) Military Coup salience derives from a
              statistical classification layer, not a dedicated LOCO-validated recipe.
              Treat as directional indicator, not model-validated output. The ML-validated
              load-bearing finding in this piece is the Elections &amp; Voting 99/100
              score. (2) The 99% cosine similarity cited is the intersection-only cosine
              on the three shared active L1 dimensions (A, D, F); the composite score
              (Jaccard &times; cosine) is 74.3%. The QGI countries page renders the cosine
              figure; this article uses the same metric. (3) ECF event markers in Chart 3
              derive from IMF program documentation (historical disbursement records), not
              QGI-computed data. Debt/GDP figures are from IMF Article IV consultation
              historical series. No IMF forward projections are incorporated in this
              piece. (4) The &ldquo;soft coup with electoral normalization&rdquo; template
              is an analyst classification of the Mauritanian precedent, not a
              QGI-generated category.
            </p>
            <p>
              See{" "}
              <Link
                href={"/methodology" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                QGI methodology
              </Link>{" "}
              for scoring run details, salience definition, and cohort construction.
            </p>
          </aside>

          {/* End-of-piece CTA */}
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
              Ghana&apos;s full risk profile (salience scores, precedent matches, and
              structural peers) is at{" "}
              <Link
                href={"/countries/ghana" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                qgintelligence.com/countries/ghana
              </Link>
              . The Elections and Voting precedent cohort (131 countries ranked) is at{" "}
              <Link
                href={"/trends/elections_and_voting" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /precedents/elections_and_voting
              </Link>
              . The methodology behind the scoring is at{" "}
              <Link
                href={"/methodology" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /methodology
              </Link>
              . If your organisation would like to commission country-specific structural
              analysis of this kind, or discuss access to QGI&apos;s full dataset, write
              to{" "}
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

          {/* Footnotes list, for print + non-hover users */}
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
                    Read more →
                  </a>
                </li>
              ))}
            </ol>
          </section>

          <p
            className="text-xs mt-12 pt-6 border-t"
            style={{
              color: "var(--qgi-text-dim)",
              borderColor: "var(--qgi-border)",
            }}
          >
            Published {PUBLISH_DATE} &middot; QG Intelligence &middot; By Amin Al-Ait
            &middot; Salience values cited from the {BAKE_DATE} V1.9.1 scoring run. This
            piece reports structural pattern resemblance and historical analogue
            comparison. It is not a forecast.
          </p>
        </div>
      </article>
    </div>
  );
}
