import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";
import { Chart1CosinePeerRankingHero } from "./charts/Chart1CosinePeerRanking";
import Chart2BilateralMultilateralSequence from "./charts/Chart2BilateralMultilateralSequence";
import Chart3IndicatorFingerprint from "./charts/Chart3IndicatorFingerprint";
import TocSidebar from "./TocSidebar";
import PrintButton from "./PrintButton";

const BAKE_DATE = "2026-04-30";
const PUBLISH_DATE = "2026-05-22";

export const metadata: Metadata = {
  title:
    "The Algorithm Found Ukraine's Closest Historical Mirror. It Is Not the Country You Expect.",
  description:
    "A structural risk platform placed Bosnia and Herzegovina as Ukraine's #1 global peer across 156 countries. Here is what that comparison tells the credit desk.",
  alternates: { canonical: "https://qgintelligence.com/reports/ukraine-bosnia-mirror" },
  openGraph: {
    title:
      "The Algorithm Found Ukraine's Closest Historical Mirror. It Is Not the Country You Expect.",
    description:
      "Ukraine's #1 cosine peer is Bosnia at 81%. 16 points ahead of the next cluster. A falsifiable structural-credit thesis.",
    url: "https://qgintelligence.com/reports/ukraine-bosnia-mirror",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: `${PUBLISH_DATE}T00:00:00Z`,
  },
  twitter: {
    card: "summary_large_image",
    title: "Ukraine's Closest Historical Mirror Is Not the Country You Expect",
    description:
      "Bosnia at 81% cosine, 16 points ahead of the next cluster. A falsifiable structural-credit thesis.",
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
    term: "Cosine similarity",
    def: "A geometric measure of how similarly shaped two countries' risk profiles are across 8 categories. 81% means the two profiles point in nearly the same direction across all active dimensions.",
    anchor: "#l1-dimensions-and-peers",
  },
  {
    n: 3,
    term: "Multilateral Agreement recipe",
    def: "A model that scores how closely a country's recent indicator trajectory matches the trajectories of countries that historically joined or institutionalised multilateral frameworks.",
    anchor: "#aggregate-vs-per-recipe",
  },
  {
    n: 4,
    term: "Bilateral Treaty recipe",
    def: "A model that scores how closely a country's recent indicator trajectory matches the trajectories of countries that historically signed significant bilateral agreements.",
    anchor: "#aggregate-vs-per-recipe",
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

export default function UkraineBosniaMirrorReportPage() {
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
        headline="The Algorithm Found Ukraine's Closest Historical Mirror. It Is Not the Country You Expect."
        description="QG identifies Bosnia as Ukraine's #1 structural twin at 81% cosine, 16 points ahead of the next-closest cluster."
        url="https://qgintelligence.com/reports/ukraine-bosnia-mirror"
        datePublished={`${PUBLISH_DATE}T00:00:00Z`}
        imageUrl="https://qgintelligence.com/reports/ukraine-bosnia-mirror/opengraph-image"
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
            Sovereign Credit Note · Published {PUBLISH_DATE}
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold leading-tight mb-4">
            The Algorithm Found Ukraine&apos;s Closest Historical Mirror. It Is Not the
            Country You Expect.
          </h1>
          <p className="text-sm mb-4" style={{ color: "var(--qgi-text-muted)" }}>
            A structural risk platform placed Bosnia and Herzegovina as Ukraine&apos;s #1
            global peer across 156 countries. Here is what that comparison tells credit
            analysts, peace negotiators, and anyone tracking when this war ends.
          </p>
          <p className="text-xs mb-1" style={{ color: "var(--qgi-text-dim)" }}>
            By Amin Al-Ait · Scoring date: {BAKE_DATE} · QG V1.9.1
          </p>
          <p
            className="text-[11px] tracking-wide uppercase"
            style={{ color: "var(--qgi-text-muted)", fontVariant: "small-caps" }}
          >
            ~8 min read · April 2026 scoring run
          </p>
        </div>

        <div className="mb-8">
          {/* On tablet/phone the hero SVG viewBox (770px wide) can overflow the
              article column; allow horizontal scroll so country names are legible. */}
          <div className="overflow-x-auto -mx-2 px-2">
            <Chart1CosinePeerRankingHero />
          </div>
          <p
            className="mt-1 text-xs text-center"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Ukraine&apos;s top-5 closest countries by overall risk-profile shape. Bosnia
            at 81% is categorically ahead.
          </p>
        </div>

        <div
          className="prose-qgi text-sm sm:text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          <p>
            The conventional framework for analysing Ukraine&apos;s sovereign credit has
            become a ritual. War premium. Reconstruction liability. IMF program integrity.
            The 2022 default and 2024 debt restructuring. JPMorgan&apos;s exclusion of
            Ukrainian bonds from its benchmark indices and what that means for passive
            capital flows. Every fixed-income desk in London, every think tank in
            Washington, every development finance institution reviewing disbursement
            schedules is running some version of that model.
          </p>
          <p>
            None of them have asked a different question: across all 156 countries scored
            by a structural risk platform, which country&apos;s indicator trajectory most
            closely resembles Ukraine&apos;s right now? Not which country faces similar
            geopolitical risk. Not which peer defaulted and recovered on a comparable
            timeline. Which country, across a full eight-dimensional decomposition of
            political, conflict, governance, economic, social, diplomatic, humanitarian,
            and structural indicators, looks most like Ukraine in April 2026?
          </p>
          <p>
            According to QG Intelligence&apos;s <Fn n={1}>April 2026 scoring run</Fn>, the
            answer is not Russia. Not Poland. Not a Middle Eastern post-conflict state.
            The answer is Bosnia and Herzegovina.
          </p>
          <p>
            The <Fn n={2}>cosine similarity</Fn> is 81%, a 16-percentage-point gap above
            the next-closest cluster. Ukraine&apos;s second through fifth peers (Oman, Sri
            Lanka, Türkiye, Uzbekistan) all sit at 65%. Bosnia is not marginally ahead. It
            is categorically in a different league. The match is bidirectional: navigate
            to Bosnia&apos;s own peer panel, and Ukraine appears as Bosnia&apos;s #1
            structural twin at the same 81% figure.
          </p>

          <h2
            id="the-categorical-peer"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            1. What &ldquo;structural similarity&rdquo; actually measures
          </h2>
          <p>
            QG is not a news aggregator or a political judgment system. It does not score
            countries based on analysts&apos; opinions about governance quality, regime
            stability, or geopolitical alignment. It scores countries based on the
            trajectories of their economic and institutional indicators over time,
            comparing those trajectories against hundreds of historical cases to identify
            which patterns are currently firing.
          </p>
          <p>
            The 81% match between Ukraine and Bosnia is not driven by their political
            systems, their alliances, or their cultural histories. It is driven by the
            shape of their indicator trajectories: how those trajectories move together
            across multiple dimensions at the same time, in directions the model has
            learned to recognise from historical precedent.
          </p>
          <p>
            This is why the Bosnia comparison survives the first objection most analysts
            will raise: &ldquo;Bosnia is not at war with a nuclear power.&rdquo; True. The
            similarity is not a claim that Ukraine&apos;s conflict is identical to
            Bosnia&apos;s. It is a claim that the pattern of indicator trajectories
            Ukraine is currently on most closely resembles the pattern Bosnia was on at a
            specific point in its own trajectory.
          </p>
          <p>
            That specific point was approximately 1996 to 2000: the post-Dayton period
            when Bosnia was rebuilding after a devastating conflict and beginning to build
            the structural conditions that would eventually produce multilateral
            institutional lock-in.
          </p>

          <h2
            id="bosnia-template"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            2. The Bosnia template, and what it did
          </h2>
          <p>
            Bosnia in 1996 was a state assembled from the Dayton Peace Accords, signed in
            November 1995 after three and a half years of war. The immediate post-war
            period was not characterised by instant multilateral engagement. It was
            characterised by the slow, uneven improvement of exactly the kind of
            structural indicators that QG&apos;s{" "}
            <Fn n={3}>Multilateral Agreement recipe</Fn> is trained to detect.
          </p>
          <p>
            The recipe was built by training a machine learning model on historical data
            from 58 countries that eventually signed or joined significant multilateral
            frameworks: IMF programs, World Bank reconstruction facilities, EU
            Stabilisation and Association processes, NATO accession frameworks. The model
            learned which indicator trajectories, measured in terms of year-over-year
            change rather than absolute level, most consistently preceded those events.
          </p>
          <p>
            The three indicators that carry the most predictive weight are changes in tax
            revenue as a share of GDP (the biggest factor), changes in female labour force
            participation, and changes in a governance index called Voice and
            Accountability. These are not diplomatic indicators. They are fiscal,
            demographic, and institutional trajectory indicators. The model is detecting
            the structural conditions that make a country capable of sustaining and
            honouring multilateral commitments, not the diplomatic manoeuvring that
            precedes signing them.
          </p>
          <p>
            Bosnia today scores 99 out of 100 on this recipe, ranking first globally in
            the 58-country cohort. The model has finished its read on Bosnia. The
            structural conditions for multilateral re-engagement have, for Bosnia, fully
            resolved. Bosnia is at the end of the pattern.
          </p>

          <PullQuote>
            &ldquo;Bosnia is at the end of the pattern, not the beginning. Ukraine is at
            the beginning.&rdquo;
          </PullQuote>

          <h2
            id="what-qgi-shows-for-ukraine"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            3. Where Ukraine actually sits
          </h2>
          <p>
            QG&apos;s April 2026 read of Ukraine separates into two distinct signals that
            most conventional analysis conflates.
          </p>
          <p>
            The first signal is the expected one: Civil War and Insurgency at 93 out of
            100, ranking 6th globally in that recipe&apos;s 83-country cohort. Ukraine is
            in active conflict. The model sees it. Nobody is surprised.
          </p>
          <p>
            The second signal is the structurally interesting one:{" "}
            <Fn n={4}>Bilateral Treaty</Fn> at 95 out of 100, ranking Ukraine 7th globally
            in that 127-country cohort. This places Ukraine in the company of Saudi
            Arabia, Iran, South Korea, and other states whose structural indicator
            profiles have historically preceded significant bilateral international
            agreements.
          </p>
          <p>
            The Bilateral Treaty recipe&apos;s highest-importance indicators are
            population change, employment ratio change, and mobile cellular subscriptions
            change. These are not diplomatic variables. They are demographic and economic
            trajectory signals. The model is reading Ukraine&apos;s structural economic
            momentum: the displacement and partial return of population, the employment
            shock and partial recovery, the remarkable resilience of telecom
            infrastructure. It is matching those trajectories to historical patterns that
            preceded bilateral treaty formation in other countries.
          </p>

          <Chart3IndicatorFingerprint />

          <p>
            The Multilateral Agreement signal for Ukraine, currently at 51 out of 100 with
            a wide 37-point confidence interval, is where the Bosnia template becomes a
            forward-looking tool rather than a historical curiosity.
          </p>

          <h2
            id="the-bilateral-multilateral-sequence"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            4. The sequence: Bilateral first, Multilateral second
          </h2>
          <p>
            Bosnia&apos;s post-Dayton trajectory followed a sequence that QG&apos;s models
            have now encoded as a structural pattern: Bilateral Treaty signals fired first
            (structural diplomatic warming at the level of indicator trajectories),
            followed by Multilateral Agreement signals (institutionalised framework
            lock-in). Ukraine is currently in the bilateral treaty phase. The structural
            question this generates is: will the multilateral agreement phase follow?
          </p>

          <Chart2BilateralMultilateralSequence />

          <p>
            This is a falsifiable question with a specific, quantitative answer available
            from QG&apos;s scoring schedule.
          </p>

          <h2
            id="forward-call-and-falsification"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            5. The forward call and the falsification
          </h2>
          <p>
            The forward call: if Ukraine&apos;s Multilateral Agreement score crosses above
            70 out of 100 in QG&apos;s January 2027 or April 2027 scoring run, the Bosnia
            template is actively reproducing in Ukraine&apos;s indicator data. That is the
            quantitative signal that the post-conflict institutionalisation trajectory is
            underway at the structural level, before it necessarily appears in headline
            political events.
          </p>
          <p>
            The falsification: if Ukraine&apos;s Multilateral Agreement score remains
            below 60 out of 100 and the confidence interval does not narrow through two
            consecutive scoring runs, the Bosnia path is not activating. At that point,
            the structural case for spread compression on Ukrainian sovereign paper does
            not have QG&apos;s structural validation.
          </p>

          <PullQuote>
            &ldquo;The Bosnia-Ukraine mirror is the trade. The Multilateral Agreement
            recipe crossing 70/100 is the entry trigger. The 60/100 floor with no CI
            narrowing is the exit discipline.&rdquo;
          </PullQuote>

          <h2
            id="three-structural-caveats"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            6. Three caveats that belong in every read
          </h2>
          <p>
            QG&apos;s methodology is explicit about what structural pattern-matching is
            and is not. Three caveats belong in any honest reading.
          </p>
          <p>
            <strong>
              Russia also scores highly on the Multilateral Agreement recipe
            </strong>
            , currently at approximately 91 out of 100. The recipe is reading both
            combatants&apos; indicator trajectories as structurally consistent with a
            multilateral engagement pathway. This complicates simple &ldquo;Ukraine
            stabilises, Russia doesn&apos;t&rdquo; framing. It may mean the recipe is
            detecting a trajectory that both parties are on simultaneously. The Bosnia
            template featured Dayton signatories on multiple sides.
          </p>
          <p>
            <strong>
              The Bilateral Treaty recipe has a significant Colombia concentration in its
              training data.
            </strong>{" "}
            Colombia&apos;s 2016 peace process dominates that recipe&apos;s training set.
            Ukraine&apos;s 95th-percentile bilateral treaty score is partially driven by
            the model having learned Colombia&apos;s post-conflict structural signature.
            The signal is directionally informative, but analysts should treat it as such
            rather than as a precise probability estimate.
          </p>
          <p>
            <strong>Much of the underlying data runs with a one to two year lag.</strong>{" "}
            The April 2026 scoring run reflects economic and governance indicator data
            whose most recent release is largely 2024. Ukraine&apos;s 2025 trajectory may
            not yet be fully reflected.
          </p>

          <h2
            id="what-the-desk-gets-that-bloomberg-cannot"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            7. What this comparison gives the desk that Bloomberg cannot
          </h2>
          <p>
            A Bloomberg analyst can produce Ukraine sovereign credit analysis in depth. An
            area studies specialist can describe Bosnia&apos;s post-Dayton
            institutionalisation in detail. A sell-side strategist can model Ukrainian GDP
            recovery scenarios under various assumptions.
          </p>
          <p>
            None of them would identify Bosnia as Ukraine&apos;s closest structural
            analogue across 156 countries. None would produce the specific quantitative
            trigger, Ukraine&apos;s Multilateral Agreement score crossing 70 out of 100 in
            a named scoring run, as the structural equivalent of the Bosnia template
            activating.
          </p>
          <p>
            This is what cross-national structural indicator pattern-matching produces
            that no other methodology generates: the non-obvious comparator, the one that
            survives quantitative scrutiny, along with the specific observable that would
            confirm or falsify the comparison in real time.
          </p>
          <p>
            Whether Ukraine traverses the pattern that Bosnia traversed, and on what
            timeline, depends on political decisions and military realities that no
            indicator model can see. What the model can see is the structural substrate on
            which those decisions would operate. And that substrate, as of April 2026,
            looks more like Bosnia&apos;s pre-institutionalisation phase than any other
            country in the world.
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
                href={"/countries/ukraine" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Ukraine
              </Link>{" "}
              overall: 96 out of 100 (CI 94&ndash;99), HIGH tier. Civil War recipe: 93 out
              of 100 (CI 88&ndash;98), ranked 6th of 83. Bilateral Treaty: 95 out of 100
              (CI 91&ndash;98), ranked 7th of 127. Multilateral Agreement: 51 out of 100
              (CI 33&ndash;70), ranked 29th of 58.{" "}
              <Link
                href={"/countries/bosnia_and_herzegovina" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Bosnia and Herzegovina
              </Link>{" "}
              overall: 41 out of 100 (CI 34&ndash;49), INDICATIVE tier. Multilateral
              Agreement: 99 out of 100 (CI 96&ndash;100), ranked 1st of 58. Russia
              Multilateral Agreement: 91 out of 100, ranked 6th of 58. Ukraine-Bosnia
              cosine similarity: 81% (each other&apos;s #1 in a 156-country cohort);
              next-closest cluster at ~65%. Multilateral Agreement recipe: the
              platform&apos;s most validated model (LOCO AUC 0.8689, calibration error
              0.009). Bilateral Treaty recipe: validated but with a Colombia 25%
              training-concentration caveat (LOCO AUC 0.6681). Data through the April 2026
              scoring run on QG Intelligence V1.9.1.
            </p>
            <p className="mb-2">
              What QG is and is not: the platform reports structural pattern resemblance,
              not a probability forecast. This piece is structural analysis, not
              investment advice.
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
              for recipe construction, validation approach, and confidence interval
              definitions.
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
              Ukraine&apos;s full profile is at{" "}
              <Link
                href={"/countries/ukraine" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                qgintelligence.com/countries/ukraine
              </Link>
              ; Bosnia&apos;s at{" "}
              <Link
                href={"/countries/bosnia_and_herzegovina" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /countries/bosnia_and_herzegovina
              </Link>
              . Recipe pages:{" "}
              <Link
                href={"/trends/bilateral_treaty" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /precedents/bilateral_treaty
              </Link>{" "}
              and{" "}
              <Link
                href={"/trends/multilateral_agreement" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /precedents/multilateral_agreement
              </Link>
              . To commission structural credit analysis on a specific sovereign or
              discuss access to QG&apos;s full dataset, write to{" "}
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
            resemblance, not a forecast. Not investment advice.
          </p>
        </div>
      </article>
    </div>
  );
}
