import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";
import Chart1CosineDecomposition, {
  Chart1CosineDecompositionHero,
} from "./charts/Chart1CosineDecomposition";
import Chart2RecipeIndicators from "./charts/Chart2RecipeIndicators";
import Chart3TimeWindowSigma from "./charts/Chart3TimeWindowSigma";
import TocSidebar from "./TocSidebar";
import PrintButton from "./PrintButton";

const BAKE_DATE = "2026-04-30";
const PUBLISH_DATE = "2026-05-22";

export const metadata: Metadata = {
  title: "India and Pakistan Are Not as Different as Their Credit Ratings Say",
  description:
    "On every risk framework that matters, India and Pakistan live in opposite worlds. QG Intelligence's April 2026 scoring run says that is not what the data show.",
  alternates: { canonical: "https://qgintelligence.com/reports/india-pakistan-mirror" },
  openGraph: {
    title: "India and Pakistan Are Not as Different as Their Credit Ratings Say",
    description:
      "QG Intelligence places India and Pakistan at 99% similarity, each other's #1 structural peer in a 156-country cohort.",
    url: "https://qgintelligence.com/reports/india-pakistan-mirror",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: `${PUBLISH_DATE}T00:00:00Z`,
  },
  twitter: {
    card: "summary_large_image",
    title: "India and Pakistan Are Not as Different as Their Credit Ratings Say",
    description:
      "QG places India and Pakistan at 99% similarity, each other's #1 structural peer in the 156-country cohort.",
  },
  robots: { index: true, follow: true },
};

const FOOTNOTES = [
  {
    n: 1,
    term: "April 2026 scoring run",
    def: "A specific computation cycle of QG Intelligence on April 2026 data. Scores change as new data arrives.",
    anchor: "#what-is-a-scoring-run",
  },
  {
    n: 2,
    term: "99% cosine similarity",
    def: "A geometric measure of how similarly shaped two countries' risk profiles are across 8 categories. 99% means they look almost identical from above.",
    anchor: "#l1-dimensions-and-peers",
  },
  {
    n: 3,
    term: "Civil War recipe",
    def: "A model that scores how closely a country's recent indicator trajectory matches the trajectories of countries that historically experienced civil war onset or escalation.",
    anchor: "#aggregate-vs-per-recipe",
  },
  {
    n: 4,
    term: "S / M / L / XL windows",
    def: "Four time horizons the platform measures: Short (3-8 years), Medium (9-20 years), Long (21-40 years), Extra-Long (41+ years). Patterns on shorter windows are recent; patterns on the XL window are decades-deep.",
    anchor: "#pattern-tiers",
  },
] as const;

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
          Read more →
        </a>
      </span>
      <style>{`.fn-wrap:hover .fn-tooltip, .fn-wrap:focus-within .fn-tooltip { display: block !important; }`}</style>
    </span>
  );
}

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

export default function IndiaPakistanMirrorReportPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <style
        dangerouslySetInnerHTML={{
          __html: `@media print { .print\\:hidden, header, footer, .fn-tooltip { display: none !important; } body, .rpt-page-root { background: #fff !important; color: #111 !important; } article { max-width: 100% !important; padding: 0 !important; } h1, h2, h3 { color: #111 !important; } blockquote { border-left-color: #333 !important; background: transparent !important; color: #111 !important; } aside { background: #f5f5f5 !important; border-color: #ccc !important; color: #333 !important; } a { color: #111 !important; text-decoration: underline !important; } #footnotes { border-top: 1px solid #ccc !important; } figure { overflow: visible !important; } @page { margin: 20mm 15mm; } }`,
        }}
      />

      <ArticleJsonLd
        headline="India and Pakistan Are Not as Different as Their Credit Ratings Say"
        description="QG Intelligence places India and Pakistan at 99% similarity. The Civil War recipe fires on both with the same fingerprint."
        url="https://qgintelligence.com/reports/india-pakistan-mirror"
        datePublished={`${PUBLISH_DATE}T00:00:00Z`}
        imageUrl="https://qgintelligence.com/reports/india-pakistan-mirror/opengraph-image"
        author={{ type: "Person", name: "Amin Al-Ait" }}
      />

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

      <TocSidebar />

      <article className="mx-auto max-w-3xl px-6 py-16">
        <div className="mb-8">
          <div
            className="text-[10px] tracking-widest uppercase mb-3 font-semibold"
            style={{ color: "var(--qgi-accent)" }}
          >
            Country Analysis · Published {PUBLISH_DATE}
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold leading-tight mb-4">
            India and Pakistan Are Not as Different as Their Credit Ratings Say
          </h1>
          <p className="text-sm mb-4" style={{ color: "var(--qgi-text-muted)" }}>
            Investment grade and CCC+. $3.5 trillion economy and an IMF program. The
            conventional risk frameworks put these countries in different universes. The
            algorithm sees them as twins.
          </p>
          <p className="text-xs mb-1" style={{ color: "var(--qgi-text-dim)" }}>
            By Amin Al-Ait · Scoring date: {BAKE_DATE} · QG V1.9.1
          </p>
          <p
            className="text-[11px] tracking-wide uppercase"
            style={{ color: "var(--qgi-text-muted)", fontVariant: "small-caps" }}
          >
            ~7 min read · April 2026 scoring run
          </p>
        </div>

        <div className="mb-8">
          <Chart1CosineDecompositionHero />
          <p
            className="mt-1 text-xs text-center"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Where the 99% match comes from. Six categories. Two countries. One shared
            shape.
          </p>
        </div>

        <div
          className="prose-qgi text-sm sm:text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          <p>
            Every conventional risk framework places India and Pakistan in opposite
            worlds. India: investment grade, 6.5% growth, $3.5 trillion economy, rising
            global power. Pakistan: IMF program, CCC+ rated, sovereign default flirtation
            in 2023, perpetual political crisis. The two countries share a border, a
            partition, and most of their historical disputes, but in the world of risk
            pricing they have lived in separate universes for thirty years.
          </p>
          <p>
            QG Intelligence&apos;s <Fn n={1}>April 2026 scoring run</Fn> says that
            separation does not exist in the data.
          </p>
          <p>
            The platform places India and Pakistan at <Fn n={2}>99% cosine similarity</Fn>
            , making them each other&apos;s #1 structural peer in the entire 156-country
            cohort. Both sit at the top risk tier. Both score within three percentile
            points of each other on the <Fn n={3}>Civil War recipe</Fn>, the
            platform&apos;s best-validated model. And when the algorithm breaks down where
            the 99% match comes from, it finds that the similarity spans six of the eight
            categories the platform measures: violence and conflict (the biggest slice at
            45%), political power and regime, state authority and governance, economic
            stress, social mobilisation, and diplomatic posture.
          </p>
          <p>This is not a data error. The match holds across multiple scoring cycles.</p>

          <h2
            id="opposite-ends-of-the-spectrum"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            1. What the algorithm is actually measuring
          </h2>
          <p>
            QG is not a news aggregator or a credit rating. It does not score countries on
            what they look like politically. It scores them on the shape of their economic
            and institutional indicators over time, comparing those trajectories against
            decades of historical data to see which historical patterns match.
          </p>
          <p>
            The 99% number is not a claim that India and Pakistan are politically similar.
            It is a claim that across the indicators historically associated with conflict
            and instability, the two countries are currently moving the same direction at
            the same rate.
          </p>

          <h2
            id="what-the-cosine-decomposition-shows"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            2. What it does not mean
          </h2>
          <p>
            QG&apos;s reading is not a forecast that India is about to experience the kind
            of conflict Pakistan has lived through in Khyber Pakhtunkhwa or Balochistan.
            India&apos;s democratic institutions, its independent judiciary, its
            professional civil service, and its track record of governing 1.4 billion
            people through successive peaceful transfers of power are real structural
            facts the algorithm does not see.
          </p>
          <p>
            What it does mean is more uncomfortable: at the level of the indicators that
            historically precede civil conflict, indicators that span economic, political,
            governance, and demographic dimensions, India&apos;s current trajectory is
            producing the same statistical signature as Pakistan&apos;s. The algorithm
            cannot see the institutions that might absorb the stress. It can see the
            stressors themselves.
          </p>

          <Chart1CosineDecomposition />

          <PullQuote>
            &ldquo;The algorithm cannot see the institutions that might absorb the stress.
            It can see the stressors themselves.&rdquo;
          </PullQuote>

          <h2
            id="what-it-doesnt-mean"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            3. What is driving the match
          </h2>
          <p>
            The Civil War recipe fires on both countries with an identical set of
            indicators in the same rank order. Same model, two countries, one structural
            signature.
          </p>

          <Chart2RecipeIndicators />

          <p>
            The top driver is battle-related deaths year over year. In India, that
            reflects the ongoing low-intensity conflict in Jammu and Kashmir, the
            North-East insurgencies (Manipur especially since 2023), and Naxalite-related
            violence. In Pakistan, it reflects the TTP insurgency, ongoing Balochistan
            operations, and the post-Afghanistan-withdrawal security deterioration. The
            model does not distinguish between a counter-insurgency state and a failing
            state. It reads the underlying data.
          </p>
          <p>
            The second driver is a governance metric tracking political stability and
            absence of violence. Both V-Dem and the World Bank&apos;s governance series
            have recorded deterioration in this score for India in recent years, driven by
            state-level communal violence, the Manipur crisis, and rising political
            polarisation. Pakistan&apos;s deterioration on the same metric is more acute
            but the direction of travel is the same.
          </p>
          <p>
            The third is energy import dependency. Both countries are exposed to global
            energy markets in ways that connect economic shocks to political stress.
          </p>

          <h2
            id="the-stressors-driving-the-match"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            4. The number that matters most
          </h2>
          <p>
            The platform measures the strength of each match across four time horizons:{" "}
            <Fn n={4}>
              Short (3-8 years), Medium (9-20 years), Long (21-40 years), and Extra-Long
              (41+ years)
            </Fn>
            . Patterns on shorter windows are recent. Patterns on the XL window are
            decades-deep structural conditions.
          </p>

          <Chart3TimeWindowSigma />

          <p>
            India and Pakistan are identical at Short, Medium, and Long windows: 1.94σ,
            1.74σ, 1.47σ for both countries. At the Extra-Long window, the readings
            diverge. Pakistan stays at MODERATE (1.06σ). India drops to INDICATIVE
            (0.83σ).
          </p>
          <p>
            The longer the time horizon, the more the structural similarity dissipates.
            This is the central nuance of the entire reading. The convergence between
            India and Pakistan is a recent phenomenon, driven by the past decade&apos;s
            indicator movements, not a decades-long structural identity. India has not
            walked Pakistan&apos;s full historical trajectory. It has converged on it
            recently.
          </p>

          <PullQuote>
            &ldquo;The convergence is recent. India has not walked Pakistan&apos;s full
            historical trajectory. It has converged on it recently.&rdquo;
          </PullQuote>

          <h2
            id="banking-system-implication"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            5. The implication for risk frameworks
          </h2>
          <p>
            India&apos;s financial system has spent the past decade building its internal
            risk frameworks on the premise of India-Pakistan divergence. The RBI Financial
            Stability Report assesses India in isolation. Stress tests treat the external
            environment through commodity prices and capital flows, not structural
            comparison. Indian commercial banks run country risk on V-Dem and World Bank
            governance indicators plus S&amp;P sovereign composites. None of these
            frameworks would produce the finding that India and Pakistan are structural
            equivalents.
          </p>
          <p>
            They are not designed to ask the question QG asks. The question is: out of all
            156 countries scored, which one&apos;s recent indicator trajectory most
            closely resembles a given country&apos;s, across the full set of dimensions
            that historically precede geopolitical stress?
          </p>
          <p>The answer, for India, is Pakistan. The answer, for Pakistan, is India.</p>

          <h2
            id="sigma-tier-divergence-at-xl"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            6. The forward call
          </h2>
          <p>
            If India&apos;s Short-window reading on the Civil War recipe stays above 1.5σ
            in the next scoring run while the Extra-Long window stays below 1.0σ, the
            convergence is real but contained as a medium-term phenomenon, not a deep
            structural identity. That is the most likely outcome.
          </p>
          <p>
            The reading falsifies in two ways. First, decay: if India&apos;s political
            stability indicators and battle-related deaths improve over the next 12-18
            months (Manipur resolves, J&amp;K militancy drops, V-Dem stability ticks up
            post-2024 electoral consolidation), India&apos;s Short-window signal would be
            expected to drop below MODERATE. The convergence claim weakens.
          </p>
          <p>
            Second, escalation: if India&apos;s Bilateral Treaty signal escalates above
            MODERATE in the wake of the April 2026 Pahalgam attack and its bilateral
            consequences, the structural fingerprint changes in a way that can be tracked
            in real time against the next scoring run.
          </p>

          <h2 id="forward-call" className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            7. What this is, and what it is not
          </h2>
          <p>
            None of this means India is about to look like Pakistan in any observable
            political sense. It means the structural substrate they share, the stressors
            the algorithm sees beneath the surface, is real and is recent. India&apos;s
            institutions are not Pakistan&apos;s institutions, and India&apos;s historical
            track record of absorbing stress is not Pakistan&apos;s. Those are the
            variables the algorithm cannot read.
          </p>
          <p>
            The takeaway is not panic. The takeaway is that the Indian risk-framework
            community may have been systematically underpricing the kind of structural
            risk that historically connects economic and demographic stressors to
            political instability, because no conventional tool was asking the right
            comparison.
          </p>

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
              The numbers, in one place
            </div>
            <p className="mb-2">
              <Link
                href={"/countries/india" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                India
              </Link>{" "}
              Civil War recipe: 72 out of 100 (CI 62&ndash;81), ranked 24th of 83. Time
              horizons: 1.94σ / 1.74σ / 1.47σ / 0.83σ (Short / Medium / Long /
              Extra-Long).{" "}
              <Link
                href={"/countries/pakistan" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Pakistan
              </Link>{" "}
              Civil War recipe: 68 out of 100 (CI 58&ndash;78), ranked 27th of 83. Time
              horizons: 1.94σ / 1.74σ / 1.47σ / 1.06σ. Both HIGH tier. Cosine similarity
              99% (each other&apos;s #1 of 156). Where the 99% comes from: violence and
              conflict 45%, political power and regime 17%, state authority and governance
              11%, economic stress 11%, social mobilisation 10%, diplomatic posture about
              6%. The Civil War recipe is the platform&apos;s most validated model (LOCO
              AUC 0.769, calibration error 0.006, trained on 64,830 historical instances).
              Data through the April 2026 scoring run on QG Intelligence V1.9.1.
            </p>
            <p className="mb-2">
              What QG is and is not: the platform reports structural pattern resemblance,
              not a probability forecast. The cosine match measures how similarly shaped
              two countries&apos; risk profiles are across 8 categories. It does not
              measure how likely Country A is to experience Country B&apos;s outcomes. The
              S/M/L/XL window labels refer to the time horizon over which historical
              patterns are matched.
            </p>
            <p>
              See{" "}
              <Link
                href={"/methodology" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                the methodology page
              </Link>{" "}
              for the full recipe construction, validation approach, and confidence
              interval definitions.
            </p>
          </aside>

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
              India&apos;s full risk profile is at{" "}
              <Link
                href={"/countries/india" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                qgintelligence.com/countries/india
              </Link>
              ; Pakistan&apos;s at{" "}
              <Link
                href={"/countries/pakistan" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /countries/pakistan
              </Link>
              . The Civil War recipe page (83 countries ranked) is at{" "}
              <Link
                href={"/trends/civil_war_and_insurgency" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /precedents/civil_war_and_insurgency
              </Link>
              . To commission country-specific structural analysis or discuss access to
              QG&apos;s full dataset, write to{" "}
              <a
                href="mailto:amin@qgintelligence.com"
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                amin@qgintelligence.com
              </a>
              .
            </p>
          </aside>

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
              Quick definitions
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
            style={{ color: "var(--qgi-text-dim)", borderColor: "var(--qgi-border)" }}
          >
            Published {PUBLISH_DATE} · QG Intelligence · By Amin Al-Ait · Scores from the{" "}
            {BAKE_DATE} V1.9.1 scoring run. This piece reports structural pattern
            resemblance, not a forecast.
          </p>
        </div>
      </article>
    </div>
  );
}
