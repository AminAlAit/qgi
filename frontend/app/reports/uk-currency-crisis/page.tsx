import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";
import Chart1DriverShares from "./charts/Chart1DriverShares";
import Chart2AnalogueTraj, { Chart2AnalogueTrajHero } from "./charts/Chart2AnalogueTraj";
import TocSidebar from "./TocSidebar";
import PrintButton from "./PrintButton";

/**
 * UK Currency-Crisis report page.
 *
 * Source draft: docs/specs/internal/testing/uk-currency-crisis/draft-article.md
 * Scoring run:  te-fleet-run-2, scored 2026-06-01T22:58:47 UTC
 * Byline:       Amin Al-Ait (NEVER a persona name, see E3 in report guidelines)
 * Template:     mirrors app/reports/ghana-mauritania-mirror/page.tsx exactly
 */

const BAKE_DATE = "2026-06-01";
const PUBLISH_DATE = "2026-06-19";

// ─── Metadata ─────────────────────────────────────────────────────────────────

export const metadata: Metadata = {
  title: "The Judiciary Doesn't Rate-Set · QG Intelligence Report",
  description:
    "QGI ranks the United Kingdom first of 157 countries for currency-crisis structural resemblance in 2026. The largest single driver is not the gilt yield or the current account deficit, it is judicial reform attempts. cv-AUC 0.7346.",
  alternates: {
    canonical: "https://qgintelligence.com/reports/uk-currency-crisis",
  },
  openGraph: {
    title:
      "The Judiciary Doesn't Rate-Set, But It's Topping QGI's Currency-Crisis Leaderboard",
    description:
      "UK ranks #1 of 157 for currency-crisis structural resemblance. Nearest analogue: the UK itself, 1992, match score 0.975. The lead driver is not the current account, it is judicial reform attempts.",
    url: "https://qgintelligence.com/reports/uk-currency-crisis",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: `${PUBLISH_DATE}T00:00:00Z`,
  },
  twitter: {
    card: "summary_large_image",
    title:
      "The Judiciary Doesn't Rate-Set, But It's Topping QGI's Currency-Crisis Leaderboard",
    description:
      "UK is #1 of 157 for currency-crisis structural resemblance. Lead driver: judicial reform attempts, 34.5% of signal. Nearest analogue: UK 1992, match score 0.975.",
  },
  robots: { index: true, follow: true },
};

// ─── Footnote registry ─────────────────────────────────────────────────────────
// Numbered in order of first appearance in the prose body.
// This array is the single source of truth for inline <Fn> markers AND the
// static #footnotes list below.

const FOOTNOTES = [
  {
    n: 1,
    term: "cv-AUC 0.7346",
    def: "Cross-validated Area Under the ROC Curve for the currency-crisis recipe. In a randomly selected pair of country-years (one pre-crisis, one not), the model correctly identifies the pre-crisis case approximately 73% of the time. Materially better than chance (0.5) but not a precision instrument.",
    anchor: "#recipe-performance",
  },
  {
    n: 2,
    term: "SHAP values",
    def: "SHapley Additive exPlanations: a technique derived from game theory that decomposes a model's output for a specific observation into the contribution of each input feature. A positive SHAP value means the feature is pushing the score upward toward crisis resemblance; a negative value would push it downward.",
    anchor: "#shap-attribution",
  },
  {
    n: 3,
    term: "V-Dem v2jureform",
    def: "V-Dem (Varieties of Democracy) is an academic dataset produced by the V-Dem Institute at the University of Gothenburg, coding political and institutional indicators based on expert assessments. The v2jureform indicator captures attempts by the executive to reform the judiciary in ways that reduce its independence. It is expert-coded on a 0-4 ordinal scale then converted via Bayesian IRT to a continuous latent variable; lower values correspond to more aggressive executive attempts to constrain judicial independence. V-Dem coding carries a typical lag of one to two data-vintage years.",
    anchor: "#v-dem-indicators",
  },
  {
    n: 4,
    term: "V-Dem lag caveat",
    def: "The trajectory values for v2jureform in the QGI model are z-scores relative to the cross-national distribution. A z-score persisting across two periods may indicate genuine stabilisation or may reflect the data vintage not yet incorporating the most recent assessments. This distinction is the most material empirical uncertainty in this report.",
    anchor: "#v-dem-indicators",
  },
] as const;

// ─── Inline Footnote component ────────────────────────────────────────────────
// Server-compatible CSS-only hover. Tooltip shows on :hover and :focus-within.

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

// ─── Driver table ─────────────────────────────────────────────────────────────

function DriverTable() {
  const rows = [
    { rank: 1, indicator: "Judicial Reform Attempts (V-Dem v2jureform)", share: "34.5%" },
    { rank: 2, indicator: "Current account balance (% of GDP)", share: "27.2%" },
    { rank: 3, indicator: "Imports of goods and services", share: "20.8%" },
    { rank: 4, indicator: "GDP (current USD)", share: "14.1%" },
    { rank: 5, indicator: "GDP deflator (annual %)", share: "3.5%" },
  ];

  return (
    <div style={{ overflowX: "auto", margin: "1.5rem 0" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.85em",
          fontFamily: "var(--font-data, monospace)",
        }}
      >
        <thead>
          <tr>
            {["Rank", "Indicator", "Signal Share"].map((h) => (
              <th
                key={h}
                style={{
                  padding: "6px 10px",
                  textAlign: h === "Signal Share" ? "right" : "left",
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
            <tr key={r.rank}>
              <td
                style={{
                  padding: "7px 10px",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: "var(--qgi-accent)",
                  width: 48,
                }}
              >
                {r.rank}
              </td>
              <td
                style={{
                  padding: "7px 10px",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: r.rank === 1 ? "var(--qgi-text)" : "var(--qgi-text-dim)",
                  fontWeight: r.rank === 1 ? 600 : 400,
                }}
              >
                {r.indicator}
              </td>
              <td
                style={{
                  padding: "7px 10px",
                  borderBottom: "1px solid var(--qgi-border)",
                  color: r.rank <= 3 ? "#a78bfa" : "var(--qgi-text-dim)",
                  textAlign: "right",
                  fontWeight: r.rank === 1 ? 700 : 400,
                }}
              >
                {r.share}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Page component ───────────────────────────────────────────────────────────

export default function UKCurrencyCrisisReportPage() {
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
        headline="The Judiciary Doesn't Rate-Set, But It's Topping QGI's Currency-Crisis Leaderboard"
        description="QGI ranks the UK first of 157 countries for currency-crisis structural resemblance in 2026. The largest single driver is not the gilt yield or current account deficit, it is judicial reform attempts."
        url="https://qgintelligence.com/reports/uk-currency-crisis"
        datePublished={`${PUBLISH_DATE}T00:00:00Z`}
        imageUrl="https://qgintelligence.com/reports/uk-currency-crisis/opengraph-image"
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
            Country Analysis &middot; Published {PUBLISH_DATE}
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold leading-tight mb-4">
            The Judiciary Doesn&apos;t Rate-Set, But It&apos;s Topping QGI&apos;s
            Currency-Crisis Leaderboard
          </h1>
          <p className="text-xs mb-1" style={{ color: "var(--qgi-text-dim)" }}>
            By Amin Al-Ait &middot; Scoring date: {BAKE_DATE} &middot; QGI te-fleet-run-2
          </p>
          <p
            className="text-[11px] tracking-wide uppercase"
            style={{ color: "var(--qgi-text-muted)", fontVariant: "small-caps" }}
          >
            ~15 min read &middot; June 2026 scoring run
          </p>
        </div>

        {/* Hero chart: analogue trajectory (900x400 render) */}
        <div className="mb-8">
          <Chart2AnalogueTrajHero />
          <p
            className="mt-1 text-xs text-center"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            UK 2026 vs UK 1992 analogue trajectory. Match score 0.975: effectively a
            perfect structural rhyme. Source: QGI te-fleet-run-2.
          </p>
        </div>

        <div
          className="prose-qgi text-sm sm:text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          {/* ── Introduction ── */}
          <section id="intro">
            <p>
              The standard macro anxiety report on the UK runs as follows: a structural
              current account deficit persisting for three decades; gilt yields at their
              highest in a generation; government debt tracking toward 96% of GDP; a pound
              that rose against the dollar while falling against the euro; debt service
              costs tripled in five years. That picture is real, and genuinely
              uncomfortable. It is also, as it turns out, the secondary story.
            </p>
            <p>
              QGI&apos;s currency-crisis model ranks the United Kingdom first of 157
              countries in 2026. The largest single driver of that ranking is not the gilt
              yield, not the current account deficit: it is judicial reform attempts. A
              courts-versus-executive confrontation that bond desks have treated as a
              constitutional sideshow is topping a model trained on historical currency
              crises across 157 countries and multiple decades.
            </p>
            <p>
              The finding becomes more striking when the UK&apos;s nearest historical
              analogue is identified: the <strong>United Kingdom itself, in 1992,</strong>{" "}
              in the twelve quarters preceding Black Wednesday, with a match score of{" "}
              <strong>0.975</strong> (effectively a perfect structural rhyme). The
              country&apos;s nearest structural comparator is itself before its most
              catastrophic post-war currency event.
            </p>
            <p>
              A second independent data point reinforces the judicial thesis. The
              model&apos;s second-closest analogue is <strong>Italy 1992</strong>, at a
              match score of <strong>0.9416</strong>: the same European monetary crisis,
              three days earlier, when the lira was suspended from the ERM before sterling
              followed. Italy 1992 carries secondary recipe tags in QGI&apos;s model for{" "}
              <strong>political_corruption</strong> and <strong>terrorist_attack</strong>,
              consistent with the Tangentopoli anti-corruption prosecutions simultaneously
              dismantling Italian political institutions, and the Mafia&apos;s
              assassination of judges Giovanni Falcone and Paolo Borsellino in May and
              July 1992 respectively. A currency crisis coinciding with the systematic
              murder of the country&apos;s most prominent judicial independence figures.
              Two independent historical data points (one from the UK&apos;s own past, one
              from a structurally similar contemporaneous case) both pairing currency
              crisis with acute institutional breakdown at the courts-executive boundary.
            </p>
          </section>

          {/* ── The Model and Its Honest Limitations ── */}
          <section id="limitations">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              1. The Model and Its Honest Limitations
            </h2>
            <p>
              Before the analysis, the disclosure. QGI&apos;s currency-crisis model
              carries a cross-validated AUC of{" "}
              <Fn n={1}>
                <strong>0.7346 (moderate discriminative power).</strong>
              </Fn>{" "}
              On a scale where 0.5 is a coin flip and 1.0 is perfection, this model sits
              closer to the useful end of the spectrum but is not a precision instrument.
              What it produces is{" "}
              <strong>structural resemblance to historical precedents</strong>, not a
              forecast. A score of 100 means the UK&apos;s current indicator configuration
              is more similar to the pre-crisis configurations in QGI&apos;s historical
              evidence base than any other country on earth. It does not mean a crisis is
              imminent, inevitable, or even probable in a calendar sense. It means the
              structural fingerprint matches. Investors and analysts should treat this as
              a pattern-recognition flag, not a trade signal.
            </p>
            <p>
              The model was scored at 2026-06-01T22:58:47 UTC, vintage te-fleet-run-2,
              across 157 countries. The UK is in the evidence base (meaning it appears in
              the training data as a historical case) and ranks first among all scored
              countries.
            </p>
          </section>

          {/* ── What Is Actually Driving the Score ── */}
          <section id="drivers">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              2. What Is Actually Driving the Score
            </h2>
            <p>
              QGI&apos;s framework decomposes each country score into its contributing
              indicators using <Fn n={2}>SHAP values</Fn>, a technique that assigns each
              input variable a share of the model&apos;s output for that observation. For
              the UK in 2026, the driver ranking is:
            </p>

            <DriverTable />
            <Chart1DriverShares />

            <p>Three things are worth holding in mind as you read this table.</p>
            <p>
              First, all five SHAP values are positive: every driver is pushing the score
              upward. There are no offsetting signals in this model. The UK is not a
              country where economic strengths are partially cancelling institutional
              weaknesses. The configuration is uniformly crisis-resemblant across all five
              dimensions.
            </p>
            <p>
              Second, the top three drivers together account for{" "}
              <strong>82.5% of the signal.</strong> This is a concentrated, coherent
              profile, not a diffuse one.
            </p>
            <p>
              Third, and most consequential for the analysis that follows: the lead signal
              is institutional, not macroeconomic. A judiciary indicator outweighs the
              current account deficit by seven percentage points.
            </p>
          </section>

          <PullQuote>
            &ldquo;The lead signal is institutional, not macroeconomic. A judiciary
            indicator outweighs the current account deficit by seven percentage
            points.&rdquo;
          </PullQuote>

          {/* ── The Judicial Dimension ── */}
          <section id="judicial">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              3. The Judicial Dimension: What the Model Is Measuring
            </h2>
            <p>
              The{" "}
              <Fn n={3}>
                V-Dem <code>v2jureform</code> indicator
              </Fn>{" "}
              is expert-coded on a 0&ndash;4 ordinal input scale, then converted via
              Bayesian item response theory to a continuous latent variable score; the
              output is not bounded to 0&ndash;4 and can take negative values (the UK raw
              value in this vintage is &minus;0.045). Lower latent scores correspond to
              more aggressive executive attempts to constrain or reform the judiciary. The
              UK&apos;s trajectory in the data shows a striking pattern: relatively stable
              scores from 2021 through early 2023, then a sharp deterioration (a z-score
              drop from +0.55 to &minus;2.98 at the inflection point), with partial
              stabilisation around &minus;0.40 to &minus;0.61 thereafter. The model&apos;s
              trajectory window registers this as a large, sudden, and incompletely
              reversed shock to judicial-executive relations.
            </p>
            <p>
              The events underneath that inflection point are not obscure. In November
              2023, the UK Supreme Court ruled unanimously that the government&apos;s
              Rwanda deportation policy was unlawful, finding Rwanda was not a safe third
              country and that the risk of refoulement was real [Human Rights Watch, Nov
              2023; Euronews, Nov 2023]. The Sunak government&apos;s response was not to
              accept the ruling. It legislated around it. The Safety of Rwanda (Asylum and
              Immigration) Act 2024 directed judges to treat Rwanda as safe
              &ldquo;regardless of any evidence to the contrary before them&rdquo;,
              stripping courts of their factual review function in that domain. The UN
              Special Rapporteur and the Council of Europe Commissioner for Human Rights
              issued formal statements: the Bill constituted an &ldquo;effective
              infringement of judicial independence&rdquo; and amounted to
              &ldquo;legislative usurpation of the judicial function&rdquo; [OHCHR, March
              2024; International Bar Association, 2024].
            </p>
            <p>
              This was not an isolated episode. Running alongside it: a sustained debate
              about the UK&apos;s continued membership of the European Convention on Human
              Rights, which shifted from fringe to mainstream party politics by
              2025&ndash;26 [Public Law for Everyone, July 2025; BIICL, 2026]; ongoing
              judicial review reform proposals narrowing the scope of court oversight of
              executive action [Law Society; Commons Library]; and a structural question
              about executive willingness to operate within judicial constraints that the
              Law Society described as the most acute courts-versus-executive
              confrontation in post-war British constitutional history.
            </p>
            <p>
              The QGI model was not coded to find this. It was trained on pre-crisis
              structural configurations across 157 countries and multiple decades. When it
              identifies judicial reform attempts as the single largest driver of UK
              currency-crisis resemblance, it is reporting a pattern in the historical
              data: the pre-crisis period in currency crises has repeatedly been a period
              of elevated institutional stress, including stress at the boundary between
              executive and judicial authority. The mechanism is not opaque, even if the
              model does not specify it. Three transmission channels are consistent with
              the historical co-occurrence. First, judicial independence functions as a
              proxy for rule-of-law credibility: overseas capital markets assign a
              sovereign risk premium to jurisdictions where executive power over judicial
              outcomes is perceived to be expanding, not because courts set rates, but
              because the rule of law is the underlying guarantee of property rights and
              contract enforcement on which capital allocation depends. Second,
              executive-judicial conflict is a leading indicator of policy
              unpredictability: governments willing to legislate around court rulings
              signal a lower constraint on future executive action, raising the
              institutional discount that foreign investors apply to long-duration assets
              denominated in that currency. Third, and most structurally, executive
              overreach toward judicial institutions has historically been a coincident or
              leading indicator of the underlying political-economy deterioration that
              produces crises: governments under electoral and fiscal stress reach for
              institutional control tools precisely when macroeconomic pressure is
              building, making judicial attacks a symptom of the same underlying
              fragility. The model has learned this co-occurrence across 157 countries and
              multiple decades. The mechanism need not be direct to be real.
            </p>
            <p>
              <strong>
                The <Fn n={4}>V-Dem lag caveat</Fn> deserves full treatment here, not a
                footnote.
              </strong>{" "}
              V-Dem scores carry a typical lag of one to two years in their expert-coding
              process. The trajectory values in the model&apos;s window (2024&ndash;26)
              likely reflect predominantly 2022&ndash;24 events, specifically the Rwanda
              Act period under the Sunak government. Whether the Starmer government&apos;s
              materially different posture has already changed the underlying score is
              unconfirmed in available data. The plateau in the z-score trajectory
              (&minus;1.0085 for two consecutive periods, then &minus;1.1605) may reflect
              data vintage lag as much as genuine stabilisation. There are two possible
              interpretations with meaningfully different implications. If the plateau is
              genuine (meaning the Starmer government&apos;s less confrontational approach
              has arrested the deterioration), the lead signal should recede in the next
              two V-Dem coding cycles, and the QGI score should fall from its current
              rank-1 position. If the plateau is artefactual (meaning the coding lag means
              the 2025 assessments have not yet been incorporated and the underlying
              institutional trajectory has not reversed as fully as the current
              government&apos;s posture suggests), the signal may remain elevated or
              worsen. A country specialist pressing on this question would find it
              genuinely unresolved in the current data vintage. It is the single most
              important caveat on the lead finding.
            </p>
          </section>

          {/* ── The Macroeconomic Layer ── */}
          <section id="macro">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              4. The Macroeconomic Layer: The Conventional Story Is Also Real
            </h2>
            <p>
              Stripping out the judicial signal, the remaining 65.5% of the QGI score is
              macroeconomic, and it maps directly onto the standard anxiety report.
            </p>
            <p>
              <strong>Current account balance (27.2% of signal).</strong> The UK&apos;s
              current account deficit ran at &pound;86 billion (3.0% of GDP) in 2024,
              narrowing to &pound;74 billion (2.4% of GDP) in 2025 [ONS, Q4 2025]. The
              quarterly pattern is not reassuring: Q2 2025 widened to 3.2% of GDP, Q3
              narrowed to 1.4%, Q4 widened again to 2.4%, oscillating rather than
              converging. The QGI raw value reads &minus;2.98% of GDP, improving
              directionally from &minus;3.58% but still structurally negative. The
              trajectory z-score of +1.598 means the improvement is modest relative to
              historical variation in the evidence base.
            </p>
            <p>
              The UK has run a structural current account deficit for most of the past
              three decades. Its external position depends continuously on capital
              inflows: the &ldquo;kindness of strangers&rdquo; formulation that Mark
              Carney put to Parliament in 2016 retains its accuracy. That dependence
              creates a structural vulnerability to confidence shifts in overseas capital
              markets that a surplus country does not face.
            </p>
            <p>
              <strong>Imports (20.8% of signal).</strong> The raw value of $1.174 trillion
              (up from $1.132 trillion in the prior vintage) carries a trajectory z-score
              change of +2.456, the steepest upward move of any indicator in the UK&apos;s
              entire profile. This is the variable moving fastest, relative to its own
              historical distribution, in the UK&apos;s current configuration, and it is
              moving in the wrong direction.
            </p>
            <p>
              Rising imports, in the model&apos;s historical pattern, are associated with
              the pre-crisis period through a specific mechanism: domestic demand running
              ahead of productive capacity, currency strength masking external fragility,
              and a trade position that can deteriorate rapidly when the exchange rate
              moves. The sequence in crisis episodes typically runs as follows. An import
              surge, sustained by consumer demand and a relatively strong currency, widens
              the current account deficit in a way that is self-obscuring while the
              currency holds, with sterling strength in 2025 making the current account
              look manageable even as the underlying import trend worsened. When the
              exchange rate moves under external pressure, the import bill does not
              contract immediately; it typically lags by several quarters, meaning the
              external position worsens through the initial depreciation before improving.
              In the 1992 UK analogue, the Lawson Boom import surge (current account
              reaching &minus;4.9% of GDP by 1989) was precisely this mechanism:
              demand-led overheating, currency-masked fragility, rapid reversal on ERM
              entry and subsequent squeeze. The +2.456 z-score on imports today is the
              strongest upward signal in the UK&apos;s current configuration. It warrants
              equivalent attention to the judicial dimension: it is one-fifth of the
              model&apos;s total output, and the mechanism connecting it to currency
              crisis risk is well-documented in the historical evidence.
            </p>
            <p>
              <strong>GDP nominal level (14.1%) and GDP deflator (3.5%).</strong> These
              are structural positioning variables. At $3.686 trillion, UK GDP places the
              country in a size cohort (large, liquid, internationally referenced) that
              matches the historical currency-crisis evidence base in specific ways.
              Large, liquid currencies are subject to large, liquid speculative attacks,
              as 1992 demonstrated. The GDP deflator at 3.62%, declining from a recent
              peak of 6.34%, shows that the post-pandemic inflation spike is unwinding,
              but the trajectory z-score of +1.990 means the level relative to history
              remains elevated.
            </p>
            <p>
              <strong>The gilt market as corroborating signal.</strong> The QGI model does
              not include gilt yields directly, but the bond market&apos;s own verdict is
              consistent with the model&apos;s reading. In January 2025, 30-year gilt
              yields reached 5.27%, their highest level since 1998 [Bloomberg, 7 Jan
              2025]. The Lords held an emergency debate on 14 January 2025 specifically
              titled &ldquo;Sterling: Rise in Yields on 30-Year Gilts&rdquo; [Hansard]. By
              May 2026, yields had returned to those levels [Bloomberg, 5 May 2026]. The
              National Institute of Economic and Social Research published a blog in 2026
              titled &ldquo;Could a Gilt Market Shock Derail the Economy in 2026?&rdquo;
              [NIESR, 2026]. The UK&apos;s 10-year gilt currently carries the highest
              yield in the G7. The government plans to issue &pound;297 billion of bonds
              in this fiscal year, the second-highest on record [Bank of England Insights,
              2026]. These are not the numbers of a country whose external financing
              position is stable.
            </p>
          </section>

          {/* ── Black Wednesday ── */}
          <section id="black-wednesday">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              5. Black Wednesday: The Self-Rhyme
            </h2>
            <p>
              The nearest historical analogue in QGI&apos;s model is the{" "}
              <strong>United Kingdom in 1992</strong>, with a match score of{" "}
              <strong>0.975</strong>, effectively a perfect structural rhyme.
              Understanding what happened then is inseparable from understanding what the
              model is saying now.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              The Run-Up: 1988&ndash;1990
            </h3>
            <p>
              The conditions were assembled across a decade. The Lawson Boom of the late
              1980s (UK GDP growth running well above the 2.5% long-run trend, a housing
              market surge feeding consumer demand) produced a current account deficit of{" "}
              <strong>4.9% of GDP</strong> by 1989 and inflation reaching{" "}
              <strong>9.5% by 1990</strong>, roughly three times Germany&apos;s rate
              [Economics Help; Economics Observatory]. These are the 1992 analogues of the
              current account deficit at &minus;2.98% and imports running at +2.46
              standard deviations above historical mean in today&apos;s data.
            </p>
            <p>
              Margaret Thatcher had resisted ERM membership for over a decade, viewing a
              fixed exchange rate as a surrender of monetary sovereignty. On 8 October
              1990, with John Major as Chancellor, the UK joined the ERM at a central rate
              of <strong>&pound;1 = DM2.95</strong>, with a &plusmn;6% fluctuation band
              [John Major Archive, Oct 1990]. Major stated publicly he was
              &ldquo;confident that a central rate of DM2.95 is sustainable.&rdquo;
              Critics argued the rate was overvalued (some preferred DM2.50), and that the
              overvaluation would structurally worsen the current account [Economics Help;
              OMFIF].
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              The Squeeze: 1990&ndash;1992
            </h3>
            <p>
              Two forces converged to make the peg untenable. The Bundesbank raised German
              interest rates aggressively to counteract inflationary spending from German
              reunification. By August 1992, German short-term rates stood at
              approximately <strong>9.9%</strong> (their highest in roughly 60 years),
              while US rates sat at <strong>3.4%</strong>, their lowest in 30 years
              [Economics Observatory; NBER Working Paper w29488]. The ERM&apos;s design
              required member states to import German monetary tightness regardless of
              their own cyclical position.
            </p>
            <p>
              The UK was in recession. High interest rates (maintained to defend the peg)
              inflated mortgage costs precisely as the housing market collapsed. Default
              rates rose. Unemployment climbed. The political trap was complete: defend
              the peg (maintain high rates that were breaking the domestic economy), cut
              rates (abandon the peg), or devalue (political humiliation). George Soros
              began building a short position on sterling in late 1991 as the structural
              contradiction became visible to sophisticated market participants
              [MoneyWeek; IG UK]. By summer 1992 the position had grown to{" "}
              <strong>$10 billion</strong> against the pound.
            </p>
            <p>
              The political-institutional dimension ran in parallel. The Maastricht Treaty
              ratification became a constitutional crisis: Conservative &ldquo;Maastricht
              Rebels&rdquo; (including figures backed by Thatcher and Norman Tebbit)
              opposed the European Communities (Amendment) Bill at multiple stages
              [Wikipedia, Maastricht Rebels; Mile End Institute, QMUL]. Separately, the
              Factortame litigation had established by 1990 that UK courts could disapply
              Acts of Parliament conflicting with EU law, a rupture in the Diceyan
              doctrine of parliamentary sovereignty that ran directly through the
              ERM/Maastricht era [House of Lords, Factortame, 1999]. In July 1993, William
              Rees-Mogg brought a judicial review challenge to the Maastricht
              Treaty&apos;s ratification (calling it &ldquo;the most important
              constitutional case for 300 years&rdquo;), which was dismissed but
              demonstrated that the courts were being drawn into the centre of a
              political-monetary crisis [Wikipedia, R v Secretary of State ex p
              Rees-Mogg].
            </p>
            <p>
              This is the dimension the QGI model is now measuring in 2026 through the
              v2jureform indicator. The judicial-constitutional tension of 1992&ndash;93,
              parliament versus courts, executive versus legal constraints on sovereignty,
              co-occurred with the currency crisis. The model learned that this
              co-occurrence is a structural pattern, not a coincidence.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">
              Black Wednesday: 16 September 1992
            </h3>
            <blockquote
              style={{
                margin: "1.5rem 0",
                padding: "0.75rem 1.25rem",
                borderLeft: "3px solid var(--qgi-border)",
                fontStyle: "italic",
                color: "var(--qgi-text-dim)",
                fontSize: "0.95em",
                lineHeight: 1.6,
              }}
            >
              &ldquo;If I had to pick one day in history to symbolise the supremacy of
              markets over states and democracies, Black Wednesday would be the one...
              Black Wednesday killed off any idea that markets could be tamed by
              democratic means.&rdquo;
              <footer
                style={{
                  marginTop: "0.5rem",
                  fontSize: "0.85em",
                  color: "var(--qgi-text-muted)",
                  fontStyle: "normal",
                }}
              >
                &mdash; Professor Alexis Stenfors [University of Portsmouth / The
                Conversation, 2022]
              </footer>
            </blockquote>
            <p>
              The Italian lira had been devalued on 13 September and suspended from the
              ERM, signalling wider fragility [Wikipedia; IG UK]. On 16 September, the
              Bank of England was buying{" "}
              <strong>&pound;2 billion of sterling per hour</strong> against an
              unstoppable tide of selling. The base rate was raised from 10% to 12%, then
              to 15%, within a single trading day. Speculators judged, correctly, that 15%
              interest rates were politically unsustainable against a backdrop of
              recession, collapsing house prices, and heavy variable-rate mortgage
              exposure: the government could not inflict 15% rates on an already-broken
              domestic economy long enough to outlast a position of $10 billion. Selling
              continued. By evening, Chancellor Norman Lamont announced Britain&apos;s
              suspension from the ERM. The loss on currency intervention was later
              confirmed by declassified Treasury papers at{" "}
              <strong>&pound;3.3 billion</strong> [IG UK; UK Stockbrokers]. Soros made an
              estimated <strong>$1 billion profit</strong> [Wikipedia; MoneyWeek].
            </p>
            <p>
              The political consequence was structural and lasting. Black Wednesday
              destroyed the Conservative Party&apos;s reputation for economic competence,
              legitimised euroscepticism, and made future UK participation in the euro
              politically impossible [tutor2u; IG UK; The Conversation/Stenfors]. The
              institutional consequence was equally consequential: the crisis triggered
              the adoption of inflation targeting and ultimately the Bank of
              England&apos;s operational independence in 1997 [Economics Observatory; IG
              UK], one of the most significant institutional changes in UK economic
              governance in the twentieth century.
            </p>

            <h3 className="text-lg font-semibold mt-6 mb-2">The Secondary Analogues</h3>
            <p>
              Italy 1992 carries a match score of <strong>0.9416</strong>, the
              second-closest structural comparator [QGI, te-fleet-run-2]. Italy also
              exited the ERM on 13 September 1992, three days before the UK. The secondary
              recipe tags (political_corruption and terrorist_attack) point to
              Tangentopoli and to the assassinations of Falcone and Borsellino. The
              Italian case is not a simple monetary parallel to 1992: it is a case in
              which a currency crisis and the systematic destruction of judicial
              independence through assassination unfolded simultaneously. A cross-national
              model picking up Italy 1992 as the UK&apos;s second-nearest analogue,
              through the judicial reform indicator, is doing something analytically
              meaningful: it is confirming the judicial-institutional co-occurrence from a
              structurally independent case that shares neither the UK&apos;s legal
              tradition nor its monetary history.
            </p>
            <p>
              Spain 1993 is the third analogue, at a match score of{" "}
              <strong>0.7727</strong>; the Spanish peseta underwent multiple devaluations
              in the ERM aftershock period. All three analogues cluster in the same
              European monetary crisis of 1992&ndash;93.
            </p>
            <p>
              The fact that the UK&apos;s nearest analogue is itself (not a country with
              different institutions, different currency, different history) is
              analytically striking. The model is not drawing an analogy across different
              systems. It is saying the UK&apos;s current indicator configuration, across
              five structural dimensions, is nearly identical to its own configuration in
              the twelve quarters before its most severe post-war currency event.
            </p>

            {/* Hero chart also inline for in-article context */}
            <Chart2AnalogueTraj />
          </section>

          <PullQuote>
            &ldquo;The fact that the UK&apos;s nearest analogue is itself (not a country
            with different institutions, different currency, different history) is
            analytically striking. The model is not drawing an analogy across different
            systems.&rdquo;
          </PullQuote>

          {/* ── What Is Different This Time ── */}
          <section id="differences">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              6. What Is Different This Time: How the Crisis Would Manifest
            </h2>
            <p>
              The self-rhyme is structural, not mechanical. There are important
              differences between 1992 and 2026 that the model&apos;s resemblance score
              does not fully capture, and intellectual honesty requires stating them, but
              they modify the <em>form</em> of vulnerability, not its existence.
            </p>
            <p>
              <strong>No fixed exchange-rate constraint.</strong> Sterling floats. The ERM
              peg was the precise mechanism through which the 1992 crisis manifested: the
              government was obligated to defend a rate that markets believed was wrong,
              and that obligation was both finite (bounded reserves) and politically
              catastrophic to abandon. Today, sterling can move. A currency crisis in a
              floating-rate regime looks different: it is typically slower, more diffuse,
              expressed through sustained depreciation pressure and the cost of external
              financing rather than a single dramatic peg collapse.
            </p>
            <p>
              The Liz Truss precedent is instructive about what that looks like. In 45
              days in autumn 2022, sterling fell to an all-time low of $1.035, 30-year
              gilt yields rose over 100 basis points, the Bank of England intervened in
              the gilt market to prevent a pension fund liquidity crisis, and a Prime
              Minister was removed [Wikipedia; Bank of England]. The mechanism was not an
              exchange rate peg: it was bond-market repricing combined with sterling
              depreciation triggered by a loss of fiscal credibility in overseas capital
              markets. That is the template for how a crisis manifests in a floating-rate
              regime with the UK&apos;s external position. The 2022 episode resolved
              rapidly because the fiscal shock was reversed; a crisis that combined the
              fiscal position with the external financing volume of &pound;297 billion in
              planned issuance, and with an already-elevated yield environment, would be
              less quickly resolved.
            </p>
            <p>
              <strong>
                The judicial dimension is new, and its unresolved lag is the most
                important caveat.
              </strong>{" "}
              The 1992 analogue does not have an equivalent of the Rwanda Act as a direct
              causal precursor to the currency crisis. The constitutional tensions of
              1992&ndash;93 were real and contemporaneous, but they were not the lead
              signal in contemporaneous analysis. The fact that the QGI model now
              identifies judicial reform attempts as the strongest signal in the UK&apos;s
              2026 configuration is either evidence that the model is detecting a
              cross-national structural pattern that contemporaneous analysis missed, or
              evidence that the UK&apos;s current institutional configuration is genuinely
              outside historical parameters on this dimension. The V-Dem coding lag
              (discussed in the judicial section above) means the critical empirical
              question (has the Starmer government already changed the underlying score?)
              remains unresolved. This is the single most material uncertainty in the
              analysis.
            </p>
            <p>
              <strong>Scale of external financing.</strong> &pound;297 billion in planned
              gilt issuance (the second-highest on record [Bank of England Insights,
              2026]) means the UK&apos;s dependence on ongoing overseas demand for its
              debt is exceptionally high. Gilt yields at 27-year highs, with the 10-year
              spread the widest in the G7, suggest that market is pricing in elevated risk
              even before any acute event.
            </p>
            <p>
              <strong>A forward-looking peer worth watching.</strong> The three identified
              analogues are all co-contemporaneous crisis participants, not countries in
              an early stage of resemblance. A country currently showing an early-stage
              combination of judicial independence pressure and current account deficit
              that rhymes with the UK configuration (at a lower QGI score today, but on a
              trajectory) would complete the analytical picture. QGI&apos;s scoring of
              Poland warrants attention in this context: judicial independence
              deterioration has been the defining political-economy story of the past
              decade, the current account position has oscillated, and the country is in
              the large-external-financing-dependent cohort of EU member states. This is
              an early-stage watch, not a scored finding, and will be revisited in future
              vintage updates.
            </p>
          </section>

          {/* ── The Forward Call ── */}
          <section id="forward-call">
            <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
              7. The Forward Call
            </h2>
            <p>QGI&apos;s framework requires a falsifiable forward statement.</p>
            <p>
              The structural configuration identified (judiciary-first lead signal,
              current account deficit, import elevation at +2.456 standard deviations,
              nominal GDP size placing the UK in the large-liquid-currency cohort) is
              consistent with elevated vulnerability to an external financing shock that
              manifests in gilt yields and sterling rather than a peg collapse. The
              specific crisis form most consistent with the historical analogue and the
              Truss 2022 precedent: a loss of fiscal credibility in overseas capital
              markets, leading to sustained gilt yield elevation, currency depreciation
              pressure, and a government forced to tighten monetary or fiscal policy at a
              cyclically inopportune moment.
            </p>
            <p>
              <strong>The falsifiable test has three observable components.</strong>{" "}
              First: if the UK&apos;s V-Dem judicial reform score stabilises and reverses
              materially over the next two V-Dem coding cycles, reflecting a structural
              improvement in judicial-executive relations confirmed by the Starmer
              government&apos;s legislative record, the QGI score should fall
              substantially from rank 1. Second: if the current account deficit narrows
              below &minus;1.5% of GDP for two consecutive quarters, the macroeconomic
              layer recedes with it. Third, the model&apos;s flag is validated if, before
              the next vintage update, the UK advances ECHR departure legislation AND gilt
              yields sustain above 5% on 30-year paper AND sterling trades below 1.20
              against the euro for more than 30 consecutive trading days, the combination
              of renewed institutional confrontation, elevated financing costs, and
              currency pressure that constitutes an
              external-shock-meeting-structural-vulnerability in a floating-rate regime.
            </p>
            <p>
              Conversely, the combination most likely to produce a score retreat: the
              Starmer government legislatively restores judicial review scope that was
              narrowed in the Rwanda era, the current account deficit converges toward
              &minus;1% of GDP, and sterling holds its trade-weighted position through the
              autumn gilt issuance period. If all three conditions are met and the QGI
              score persists at rank 1 through two vintage updates without an acute event,
              that would represent evidence against the model&apos;s discriminative
              validity at this end of the distribution.
            </p>
            <p>
              This is a structural resemblance finding, not an event prediction. The
              model&apos;s honest AUC of 0.7346 means roughly that in a two-country
              comparison between a high-scorer and a low-scorer, it calls the crisis
              country correctly about 73% of the time at the population level. It does not
              speak to timing, magnitude, or the probability of any specific event in the
              next twelve months. Investors and risk desks should use it as one input
              among many, specifically as a cross-indicator structural flag that surfaces
              a configuration not visible from any single macro variable.
            </p>
          </section>

          <PullQuote>
            &ldquo;This is a structural resemblance finding, not an event prediction. The
            model&apos;s honest cv-AUC of 0.7346 means roughly that in a two-country
            comparison, it calls the crisis country correctly about 73% of the time. It
            does not speak to timing, magnitude, or the probability of any specific
            event.&rdquo;
          </PullQuote>

          {/* ── Methodology Note ── */}
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
              QGI data: UK currency-crisis score rank 1 of 157 &middot; cv-AUC 0.7346
              &middot; Analogue match scores: UK 1992 = 0.975, Italy 1992 = 0.9416, Spain
              1993 = 0.7727 &middot; SHAP driver shares: v2jureform 34.5%, current account
              27.2%, imports 20.8%, GDP 14.1%, GDP deflator 3.5% &middot; All SHAP values
              positive &middot; Vintage te-fleet-run-2, scored 2026-06-01T22:58:47 UTC
              &middot; Analogue match scores are cosine similarity measures between
              indicator vectors &middot; Country scores are percentile ranks across 157
              countries.
            </p>
            <p className="mb-2">
              Methodology disclosures: (1) The V-Dem v2jureform indicator carries a
              typical expert-coding lag of one to two years; trajectory values in the
              2024&ndash;26 window likely reflect predominantly 2022&ndash;24 events.
              Whether the Starmer government&apos;s different posture has already changed
              the underlying score is unconfirmed in the current data vintage: this is the
              single most material uncertainty in the report. (2) The ONS current account
              data is current through 2025; Q1 2026 figures were not available at scoring
              time. (3) All SHAP values and raw indicator values are extracted directly
              from qgi-frontend/data/te-fleet-run-2/scores/currency_crisis.scores.json.
              (4) The what_happened_next field for all three UK analogues (UK 1992, Italy
              1992, Spain 1993) is null in the current data vintage: the curation wave has
              not yet covered these entries. (5) QGI&apos;s currency-crisis model uses
              XGBoost with SHAP TreeExplainer attribution; the cv-AUC of 0.7346 reflects
              performance on held-out country-year observations. Scores represent
              structural resemblance, not probability estimates or forecasts.
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
              for scoring run details, recipe performance metrics, and cohort
              construction.
            </p>
          </aside>

          {/* ── End-of-piece CTA ── */}
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
              The UK&apos;s full risk profile (salience scores, precedent matches, and
              structural peers) is at{" "}
              <Link
                href={"/countries/united-kingdom" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                qgintelligence.com/countries/united-kingdom
              </Link>
              . The currency-crisis precedent cohort (157 countries ranked) is at{" "}
              <Link
                href={"/trends/currency_crisis" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /trends/currency_crisis
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

          {/* ── Sources ── */}
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
                '[Bloomberg, 7 Jan 2025] "UK 30-Year Bond Yield Climbs to Highest Since 1998." Bloomberg.',
                '[Bloomberg, 5 May 2026] "Gilts Selloff Pushes 30-Year Yield to the Highest Since 1998." Bloomberg.',
                '[Hansard, 14 Jan 2025] Lords Debate: "Sterling: Rise in Yields on 30-Year Gilts." UK Parliament.',
                "[ONS Q4 2025] Balance of Payments, October to December 2025. Office for National Statistics.",
                "[OBR, March 2026] Economic and Fiscal Outlook. Office for Budget Responsibility.",
                '[Bank of England Insights, 2026] "What Were the Drivers of UK Long-Term Interest Rates in 2025?"',
                '[Human Rights Watch, Nov 2023] "UK Supreme Court Finds UK-Rwanda Asylum Scheme Unlawful."',
                '[OHCHR, March 2024] "UK-Rwanda Bill Threatens to Undermine Independence of Judiciary, UN Experts."',
                '[International Bar Association, 2024] "Migration: UK Gov Plans to Overrule SC Rwanda Defeat."',
                '[Public Law for Everyone, July 2025] "The Developing Domestic Debate About the ECHR."',
                '[NIESR, 2026] "Could a Gilt Market Shock Derail the Economy in 2026?"',
                '[Wikipedia] "Black Wednesday."',
                '[Economics Observatory] "The Birth of Inflation Targeting: Why Did the ERM Crisis Happen?"',
                '[John Major Archive, Oct 1990] "Mr Major\'s Exchange Rate Mechanism Statement, 15 October 1990."',
                '[Economics Help] "UK in ERM 1990–92"; "UK Recession of 1991–92"; "Lawson Boom of the Late 1980s."',
                '[OMFIF, 2017] "Britain\'s Most Stupid Decision."',
                '[IG UK] "Black Wednesday Explained."',
                '[MoneyWeek] "16 September 1992: Sterling Crashes Out of the ERM."',
                '[University of Portsmouth / The Conversation, Stenfors, 2022] "Why Black Wednesday Still Matters."',
                '[NBER Working Paper w29488] "Imported or Home Grown? The 1992–3 EMS Crisis."',
                '[Wikipedia] "Maastricht Rebels."',
                '[Mile End Institute, QMUL] "Major Clean Bowled: The Maastricht Confidence Motion 30 Years On."',
                '[Wikipedia] "R v Secretary of State for Foreign and Commonwealth Affairs, ex p Rees-Mogg."',
                '[House of Lords, 1999] "Regina v Secretary of State for Transport ex parte Factortame."',
                '[BIICL, 2026] "The Chisinau Declaration on the ECHR and Migration."',
                '[Law Society] "Judicial Review Reform"; "Big Win for Rule of Law, Government Restores Judges\' Discretion."',
              ].map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </section>

          {/* ── Footnotes ── */}
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

          {/* Closing dateline */}
          <p
            className="text-xs mt-12 pt-6 border-t"
            style={{
              color: "var(--qgi-text-dim)",
              borderColor: "var(--qgi-border)",
            }}
          >
            Published {PUBLISH_DATE} &middot; QG Intelligence &middot; By Amin Al-Ait
            &middot; Scoring run: {BAKE_DATE} te-fleet-run-2 &middot; This piece reports
            structural pattern resemblance (cv-AUC 0.7346) and historical analogue
            comparison. It is not a forecast.
          </p>
        </div>
      </article>
    </div>
  );
}
