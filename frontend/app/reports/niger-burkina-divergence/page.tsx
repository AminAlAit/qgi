import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";
import Chart1DivergenceBars, {
  Chart1DivergenceBarsHero,
} from "./charts/Chart1DivergenceBars";
import Chart2IndicatorWeights from "./charts/Chart2IndicatorWeights";
import Chart3CosineVsRecipe from "./charts/Chart3CosineVsRecipe";
import Chart4BosniaTemplate from "./charts/Chart4BosniaTemplate";
import TocSidebar from "./TocSidebar";
import PrintButton from "./PrintButton";

const BAKE_DATE = "2026-04-30";
const PUBLISH_DATE = "2026-05-22";

export const metadata: Metadata = {
  title:
    "Why Niger and Burkina Faso Are Not the Same Country (Even Though Every Map Says They Are)",
  description:
    "QG Intelligence's April 2026 scoring run finds Niger and Burkina Faso, two Sahel coup states that look identical from the outside, sitting at opposite ends of the same 58-country ranking. Here is what the algorithm is reading.",
  alternates: {
    canonical: "https://qgintelligence.com/reports/niger-burkina-divergence",
  },
  openGraph: {
    title: "Why Niger and Burkina Faso Are Not the Same Country",
    description:
      "Two Sahel coup states, same alliance, opposite structural paths. What QG Intelligence is reading that the political surface hides.",
    url: "https://qgintelligence.com/reports/niger-burkina-divergence",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: `${PUBLISH_DATE}T00:00:00Z`,
  },
  twitter: {
    card: "summary_large_image",
    title: "Why Niger and Burkina Faso Are Not the Same Country",
    description: "Two Sahel coup states, same alliance, opposite structural paths.",
  },
  robots: { index: true, follow: true },
};

// Footnotes kept as a quiet glossary for readers who want to hover. The prose
// itself is written so you can understand it without ever reading a footnote.
const FOOTNOTES = [
  {
    n: 1,
    term: "April 2026 scoring run",
    def: "A specific computation cycle of QG Intelligence on April 2026 data. Scores change as new data arrives; every claim in this piece is tied to that specific date.",
    anchor: "#what-is-a-scoring-run",
  },
  {
    n: 2,
    term: "Multilateral Agreement recipe",
    def: "A score from 0 to 100 that measures how closely a country's recent economic trajectory matches the trajectories of countries that historically went on to join international agreements.",
    anchor: "#aggregate-vs-per-recipe",
  },
  {
    n: 3,
    term: "95% cosine similarity",
    def: "A geometric measure of how similar two countries' overall risk profiles look across 8 categories. 95% means they look almost identical from above.",
    anchor: "#l1-dimensions-and-peers",
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

export default function NigerBurkinaDivergenceReportPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
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
        headline="Why Niger and Burkina Faso Are Not the Same Country (Even Though Every Map Says They Are)"
        description="Two Sahel coup states, same alliance, opposite structural paths. What QG Intelligence is reading that the political surface hides."
        url="https://qgintelligence.com/reports/niger-burkina-divergence"
        datePublished={`${PUBLISH_DATE}T00:00:00Z`}
        imageUrl="https://qgintelligence.com/reports/niger-burkina-divergence/opengraph-image"
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
            Why Niger and Burkina Faso Are Not the Same Country
          </h1>
          <p className="text-sm mb-4" style={{ color: "var(--qgi-text-muted)" }}>
            Two Sahel coup states. Same alliance. Same neighbours. Same press coverage.
            The algorithm says they are nothing alike.
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
          <Chart1DivergenceBarsHero />
          <p
            className="mt-1 text-xs text-center"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Three Sahel coup states on the same recipe. Niger ranks #4 globally. Burkina
            Faso ranks #57.
          </p>
        </div>

        <div
          className="prose-qgi text-sm sm:text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          <p>
            The conventional read of the Sahel since 2022 has been simple: three coup
            states, one shared anti-Western posture, one structural class. Niger, Burkina
            Faso, and Mali withdrew from ECOWAS together in January 2025 and declared
            themselves the Alliance of Sahel States. Every Africa desk in Washington and
            Brussels has filed them as a single analytical unit.
          </p>
          <p>
            According to QG Intelligence&apos;s <Fn n={1}>April 2026 scoring run</Fn>,
            that framing is wrong about Niger.
          </p>
          <p>
            Niger ranks fourth globally on the platform&apos;s{" "}
            <Fn n={2}>Multilateral Agreement recipe</Fn>, a model that scores how likely a
            country is to engage with international institutions based on the shape of its
            economic and governance indicators. Niger&apos;s score: 94 out of 100. Burkina
            Faso, which on every other measure looks structurally identical to Niger (a{" "}
            <Fn n={3}>95% cosine similarity</Fn> match, the algorithm&apos;s
            highest-confidence &ldquo;these two countries look the same&rdquo; reading),
            ranks 57th out of 58 on the same recipe. Burkina Faso&apos;s score: 2 out of
            100.
          </p>
          <p>
            These are not different shades of the same colour. They are opposite readings
            produced by the same model on two countries every analyst treats as twins.
          </p>

          <h2
            id="two-juntas-opposite-trajectories"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            1. Two juntas, opposite paths
          </h2>
          <p>
            The model is not reading politics. It is reading the underlying economic and
            demographic trajectories, the rate at which key indicators are changing year
            over year. And what it sees in Niger is something Burkina Faso does not show.
          </p>

          <Chart1DivergenceBars />

          <p>
            Niger&apos;s score is being pulled up by three indicators specifically: tax
            revenue as a share of GDP (the most important factor), women in the labour
            force, and a governance measure called Voice and Accountability that tracks
            press freedom and civil-society space. All three are measured as rates of
            change, not absolute levels, so a country that is still poor can score high if
            it is improving fast.
          </p>

          <Chart2IndicatorWeights />

          <p>
            For Niger, all three indicators are moving in the right direction. Tax revenue
            improved after ECOWAS sanctions lifted in February 2024. Female labour force
            participation, while still among the world&apos;s lowest in absolute terms,
            has nudged upward, and the model picks up these movements as meaningful
            because Niger&apos;s starting point is so low. Voice and Accountability is
            declining (it is a coup government, after all), but more slowly than in the
            immediate post-coup period.
          </p>
          <p>
            Burkina Faso&apos;s same three indicators are all moving the opposite
            direction.
          </p>

          <PullQuote>
            &ldquo;These are not different shades of the same colour. They are opposite
            readings produced by the same model on two countries every analyst treats as
            twins.&rdquo;
          </PullQuote>

          <h2
            id="what-the-model-reads"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            2. Why Niger and not Mali?
          </h2>
          <p>
            The third AES state, Mali, does not show this divergence at all. Mali&apos;s
            profile is a different shape entirely: deeper conflict, more diverse peer
            countries (Sudan, India, Lebanon, South Sudan), no Multilateral Agreement
            signal in the current run. Mali looks like a complicated multi-party conflict
            state. Niger looks like something else.
          </p>
          <p>Three specific things make Niger different from its two AES neighbours.</p>
          <p>
            <strong>First, uranium.</strong> Niger produces about 5% of the world&apos;s
            uranium, and France is the primary buyer. Uranium extraction cannot run
            without international contracts, international pricing, and international
            export infrastructure. Whether the junta likes it or not, the economy is
            structurally tied to foreign institutions.
          </p>
          <p>
            <strong>Second, demographics.</strong> Niger has the highest fertility rate in
            the world and one of the lowest female labour force participation rates. From
            that starting point, even small year-over-year improvements show up as large
            proportional changes. The model reads these as meaningful structural movement.
          </p>
          <p>
            <strong>Third, the sanctions cycle.</strong> Niger was hit harder by ECOWAS
            than Burkina Faso was, a near-total embargo from August 2023 to February 2024.
            When the sanctions lifted, the recovery pattern in Niger&apos;s fiscal and
            trade data is exactly the kind of trajectory the model has learned to
            associate with structural readiness for re-engagement.
          </p>

          <Chart3CosineVsRecipe />

          <h2
            id="aes-frame-misses"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            3. The Bosnia template
          </h2>
          <p>
            The model did not decide Niger looks promising from nowhere. It learned from
            countries that have already walked this path. The clearest historical analogue
            in the model&apos;s training data is Bosnia and Herzegovina, which today
            scores 99 out of 100 on the same recipe, the highest score globally.
          </p>

          <Chart4BosniaTemplate />

          <p>
            What Bosnia looked like in the mid-1990s, as it began rebuilding after the
            Dayton Agreement, is the structural pattern the model now detects in Niger:
            improving fiscal trajectory, improving labour market integration, slowly
            improving governance. By the time the international institutional framework
            formally locked in (IMF, World Bank, EU process), Bosnia&apos;s indicator
            trajectory had already been moving that direction for years.
          </p>
          <p>
            The lesson the model draws: structural readiness comes before political
            decision. Bosnia&apos;s indicators were moving toward multilateral engagement
            four years before the political agreement was signed.
          </p>

          <h2 id="forward-call" className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            4. The forward call
          </h2>
          <p>
            Based on the model&apos;s historical pattern, here is what to expect by the
            end of 2026: some form of formal or informal communication from Niger&apos;s
            CNSP government to the ECOWAS secretariat. Not asking to rejoin. Just asking
            to talk. A structured dialogue framework, not full membership.
          </p>
          <p>
            This is falsifiable. If by December 31, 2026, no such communication has
            occurred, verified by both the ECOWAS Executive Secretariat and Niger&apos;s
            foreign ministry, the structural reading was wrong.
          </p>

          <h2
            id="what-qgi-doesnt-see"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            5. What the model cannot see
          </h2>
          <p>
            The model has blind spots that matter for this call. It cannot see Wagner
            Group / Africa Corps deployments. Those do not show up in World Bank data, but
            they create powerful political incentives for continued isolation.
          </p>
          <p>
            It cannot see the AES bureaucracy itself, which has its own institutional
            momentum and creates costs for any member that wants to defect.
          </p>
          <p>
            It cannot fully trust the Voice and Accountability indicator. The data source
            for that metric was built to measure democratic institutions, and it does not
            translate cleanly to coup-government contexts. The platform flags this caveat
            explicitly.
          </p>
          <p>
            And it does not have a historical Niger case to validate against, only the
            broader 58-country cohort.
          </p>
          <p>
            Despite all that, the structural argument holds for one reason: the indicators
            driving Niger&apos;s score are not political. Tax revenue and female labour
            force participation are not moved by AES membership agreements or Russian
            security protocols. They are moved by the underlying economics, a
            uranium-export economy with an extreme demographic profile, and those
            economics are pointing in a direction the political surface contradicts.
          </p>

          <PullQuote>
            &ldquo;Tax revenue and female labour force participation are not moved by AES
            membership agreements. They are moved by the underlying economics, and those
            economics are pointing in a direction the political surface
            contradicts.&rdquo;
          </PullQuote>

          <h2
            id="implications-for-ecowas"
            className="text-xl sm:text-2xl font-semibold mt-10 mb-3"
          >
            6. What this means for Western diplomacy
          </h2>
          <p>
            The current consensus in AU and ECOWAS circles is that all three AES states
            are equally hostile to re-engagement, and that the path to Sahel reintegration
            requires regime change, not policy change. The structural reading says that
            consensus is probably wrong about Niger specifically.
          </p>
          <p>
            Niger may not need a different junta. It may need a different conversation. A
            structured dialogue framework that does not demand immediate ECOWAS re-entry.
            One that lets the structural conditions create political space without forcing
            the CNSP government to publicly break ranks with the AES.
          </p>
          <p>
            For a regional diplomacy that has spent two years treating the three states as
            one analytical unit, the divergence is a small but concrete handhold.
          </p>

          <PullQuote>
            &ldquo;Niger may not need a different junta. It may need a different
            conversation.&rdquo;
          </PullQuote>

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
                href={"/countries/niger" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Niger
              </Link>{" "}
              overall risk score: 89 out of 100 (CI 83&ndash;94), HIGH tier. Multilateral
              Agreement recipe: 94 out of 100 (CI 84&ndash;100), ranked 4th of 58.{" "}
              <Link
                href={"/countries/burkina_faso" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Burkina Faso
              </Link>
              : 90 out of 100 (CI 85&ndash;94), HIGH tier. Multilateral Agreement: 2 out
              of 100 (CI 0&ndash;5), ranked 57th of 58.{" "}
              <Link
                href={"/countries/mali" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Mali
              </Link>
              : 64 out of 100 (CI 56&ndash;72). The Multilateral Agreement recipe is the
              platform&apos;s most validated model (LOCO AUC 0.8689, calibration error
              0.009). The Niger / Burkina Faso 95% similarity is computed across all 8
              risk dimensions in the platform&apos;s overall risk profile. Data through
              the April 2026 scoring run on QG Intelligence V1.9.1.
            </p>
            <p className="mb-2">
              What QG cannot see, and what we have already noted in the piece: Wagner /
              Africa Corps deployments do not appear in World Bank data; AES institutional
              inertia is not modelled per country; the Voice and Accountability indicator
              carries a flag for &ldquo;possible country bias&rdquo; in post-coup
              contexts; the Multilateral Agreement recipe has no historical Niger case in
              the current training set, so this call rests on the cohort-wide validation
              rather than a country-specific track record.
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
              for how recipes are built, what LOCO AUC measures, and how confidence
              intervals are computed.
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
              Niger&apos;s full risk profile is at{" "}
              <Link
                href={"/countries/niger" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                qgintelligence.com/countries/niger
              </Link>
              . Burkina Faso&apos;s is at{" "}
              <Link
                href={"/countries/burkina_faso" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /countries/burkina_faso
              </Link>
              . The Multilateral Agreement recipe page (58 countries ranked) is at{" "}
              <Link
                href={"/trends/multilateral_agreement" as Route}
                className="underline underline-offset-2 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-accent)" }}
              >
                /precedents/multilateral_agreement
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
            resemblance and historical-analogue comparison. It is not a forecast.
          </p>
        </div>
      </article>
    </div>
  );
}
