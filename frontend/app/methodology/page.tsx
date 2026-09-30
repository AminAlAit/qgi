import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { PublicNav } from "@/components/PublicNav";
import { Wordmark } from "@/components/brand/Wordmark";
import { PublicFooter } from "@/components/PublicFooter";
import { SkipLink } from "@/components/SkipLink";
import StatCards from "@/components/methodology/StatCards";
import Glossary from "@/components/methodology/Glossary";
import VerificationFlow from "@/components/methodology/VerificationFlow";
import TaxonomyHorizontalTree from "@/components/methodology/TaxonomyHorizontalTree";
import IndicatorTaxonomyTree from "@/components/methodology/IndicatorTaxonomyTree";
import { CascadeFlow } from "@/components/methodology/CascadeFlow";
import { CountryFlag } from "@/components/design/CountryFlag";
import { TOTAL_INDICATORS, NEWS_COUNTRIES } from "@/lib/site-stats";

export const metadata: Metadata = {
  title: "Methodology · QG Intelligence",
  description:
    "How QGI works: two methods that read open data against history. The Cascade method distils the shapes that run ahead of events; the Trajectory Engine measures how closely each country is tracing them now.",
  alternates: { canonical: "https://qgintelligence.com/methodology" },
  openGraph: {
    title: "Methodology · QG Intelligence",
    description:
      "Two methods that read open data against history, and show you the evidence behind every reading.",
    url: "https://qgintelligence.com/methodology",
    siteName: "QG Intelligence",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "Methodology · QG Intelligence",
    description: "How QGI reads open data against history.",
  },
};

/**
 * Public methodology page (no auth). Rewritten 2026-05-31 to be simple,
 * visual and confidence-first: two named methods (the Cascade method + the
 * Trajectory Engine) carried by the CascadeFlow diagram, the indicator and
 * event taxonomies treated as peers, a worked example, and a plain-language
 * confidence note. All ML1 / audit jargon (AUC, ECE, LOCO, z-score salience,
 * the recipe correlation matrix, "LOCKed recipes") was removed; the honesty
 * stays accessible but never headlines.
 */
export default function MethodologyPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <SkipLink />
      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-4xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="nav" href={"/" as Route} title="Home" />
          <PublicNav currentPage="methodology" />
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="focus:outline-none">
        <article className="mx-auto max-w-4xl px-6 py-16">
          {/* Hero */}
          <div className="mb-12">
            <div
              className="text-[10px] tracking-widest uppercase mb-3"
              style={{ color: "var(--qgi-accent)" }}
            >
              Methodology
            </div>
            <h1 className="text-3xl font-semibold mb-4">How QGI works</h1>
            <p
              className="text-lg leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              QGI reads open data against history. We learn the signal shapes that tend to
              run ahead of the events that matter, then, across 180+ countries and
              territories, we measure how closely each country is tracing those shapes
              right now, and show you the real historical cases it most resembles.
              Evidence you can open, not a verdict.
            </p>
          </div>

          <StatCards />

          {/* Pattern to recipe — the opening worked example */}
          <Section id="pattern-to-recipe" title="From a pattern to a trend">
            <p
              className="text-sm leading-relaxed mb-6"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Start with a real one. QGI&rsquo;s pattern detector found that{" "}
              <strong style={{ color: "var(--qgi-text)" }}>Portugal</strong> and{" "}
              <strong style={{ color: "var(--qgi-text)" }}>Spain</strong> moved almost in
              lockstep across{" "}
              <strong style={{ color: "var(--qgi-text)" }}>26 indicators</strong> (a
              Pearson correlation near 0.87) for the half-century after both shed
              authoritarian rule in the mid-1970s. Each indicator that co-moves between
              two countries is a single co-movement we call an{" "}
              <strong style={{ color: "var(--qgi-text)" }}>SCDI</strong>; the bundle of
              them is a <strong style={{ color: "var(--qgi-text)" }}>pattern</strong>.
            </p>
            <div
              className="rounded-lg border p-6 mb-6"
              style={{
                borderColor: "var(--qgi-border)",
                backgroundColor: "var(--qgi-surface)",
              }}
            >
              <div
                className="flex flex-wrap items-center gap-3 text-sm font-data"
                style={{ color: "var(--qgi-text)" }}
              >
                <span className="inline-flex items-center gap-1.5">
                  <CountryFlag alpha2="PT" size={16} countryName="Portugal" /> Portugal
                </span>
                <span style={{ color: "var(--qgi-text-dim)" }}>&harr;</span>
                <span className="inline-flex items-center gap-1.5">
                  <CountryFlag alpha2="ES" size={16} countryName="Spain" /> Spain
                </span>
                <span style={{ color: "var(--qgi-text-dim)" }}>&middot;</span>
                <span style={{ color: "var(--qgi-accent)" }}>26 SCDIs</span>
                <span style={{ color: "var(--qgi-text-dim)" }}>&middot;</span>
                <span style={{ color: "var(--qgi-text-muted)" }}>r &asymp; 0.87</span>
                <span style={{ color: "var(--qgi-text-dim)" }}>&middot;</span>
                <span style={{ color: "var(--qgi-text-muted)" }}>1976 onward</span>
              </div>
            </div>
            <p
              className="text-sm leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              One pattern is not yet a trend. QGI gathers many patterns whose countries
              went on to share the same kind of event, lines them up against the verified
              record, and distils the movement they had in common. That distilled,
              canonical shape is a{" "}
              <strong style={{ color: "var(--qgi-text)" }}>trend</strong>: the fingerprint
              that tends to run ahead of, say, a democratic transition, a currency crisis,
              or a coup. The two methods below are the two ways QGI does this at scale.
            </p>
            <p className="mt-5 text-sm">
              <Link
                href={"/patterns" as Route}
                className="border-b pb-0.5 transition-colors hover:text-[var(--qgi-accent)] hover:border-[var(--qgi-accent)]"
                style={{
                  color: "var(--qgi-text-muted)",
                  borderColor: "var(--qgi-border)",
                }}
              >
                Explore the patterns we have found &rarr;
              </Link>
            </p>
          </Section>

          {/* Five terms (glossary, moved up so the methods read in plain language) */}
          <Glossary />

          {/* Two ways we get the insights */}
          <Section id="two-methods" title="Two ways we get the insights">
            <p
              className="text-sm leading-relaxed mb-6"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Everything QGI does rests on one idea: history rhymes, and the rhyme shows
              up in the data before the headline. Two methods turn that idea into a
              reading you can act on.
            </p>

            <CascadeFlow />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mt-8">
              <MethodCard title="The Cascade method" tint="#7B5EE6">
                Builds risk shapes from the ground up. Starting from {TOTAL_INDICATORS}{" "}
                public indicators and decades of curated history, it finds the signal
                relationships that recur across countries, then the country pairs whose
                whole trajectories rhyme. Fold those relationships together with verified,
                fact-checked events and you distil a{" "}
                <strong style={{ color: "var(--qgi-text)" }}>trend</strong>: the shape a
                country&rsquo;s signals tend to trace in the years before a given kind of
                event.
              </MethodCard>
              <MethodCard title="The Trajectory Engine" tint="#E68F29">
                Puts those trends to work. Each quarter it takes a trend&rsquo;s shape and
                a country&rsquo;s most recent signals and measures how closely the country
                is tracing that shape now. The result is a{" "}
                <strong style={{ color: "var(--qgi-text)" }}>resemblance reading</strong>,
                not a forecast: a structured way to say what today rhymes with, alongside
                the real cases it most echoes.
              </MethodCard>
            </div>
          </Section>

          {/* Trajectory Engine — technical detail (for readers who want the machinery) */}
          <Section id="trajectory-engine-detail" title="Inside the Trajectory Engine">
            <p
              className="text-sm leading-relaxed mb-6"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              For readers who want the machinery, here is what the Trajectory Engine
              actually does per trend. Nothing below is a black box; it is a deliberately
              conservative pipeline built to avoid fooling itself.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <DetailCard title="Per-trend model">
                Each event type gets its own supervised model trained on the countries
                that did and did not experience it. With a healthy positive base we use
                gradient-boosted trees (XGBoost); where positives are scarce we fall back
                to regularised logistic regression, so a thin trend cannot pretend to a
                complexity its data will not support.
              </DetailCard>
              <DetailCard title="Greedy indicator selection">
                Indicators are chosen by a forward walk: start from none, repeatedly add
                the single indicator that most improves cross-validated separation, and
                stop when the gains plateau. The walk also picks the window length, in
                years, over which the trajectory is read. A typical trend ends up resting
                on a handful of indicators, not all 250.
              </DetailCard>
              <DetailCard title="Resemblance scoring">
                A country&rsquo;s recent trajectory on the selected indicators is
                standardised (z-scored against its own history) and compared to the
                trend&rsquo;s canonical shape by cosine similarity, weighted by each
                indicator&rsquo;s contribution (SHAP). The closer the match, the higher
                the resemblance score.
              </DetailCard>
              <DetailCard title="Validation, honestly">
                Every trend is scored by{" "}
                <strong style={{ color: "var(--qgi-text)" }}>
                  leave-one-country-out cross-validation
                </strong>
                , so it is judged on countries it never trained on, with 95% confidence
                intervals from 2,000 bootstrap resamples. We also check calibration,
                run-to-run reliability, temporal confounding, and fold stability. Trends
                that clear the bar are marked Validated; those that only discriminate are
                Directional; those that fail are shown as Experimental, never dressed up
                as more.
              </DetailCard>
            </div>
            <p
              className="mt-6 text-sm leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              We use leave-one-country-out rather than random splits on purpose: random
              test sets leak regional structure and flatter the model. A trend has to
              generalise to a country it has never seen, or it does not earn a Validated
              mark.
            </p>
          </Section>

          {/* What we read */}
          <Section id="what-we-read" title="What we read">
            <p
              className="text-sm leading-relaxed mb-8"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Two catalogues sit underneath every reading: the indicators we track, and
              the events we hold them against. Both are public, both are organised so you
              can see exactly what goes in.
            </p>

            <h3
              className="text-xs tracking-[0.25em] uppercase mb-2 mt-2"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Indicators
            </h3>
            <p
              className="text-sm leading-relaxed mb-4"
              style={{ color: "var(--qgi-text)" }}
            >
              {TOTAL_INDICATORS} open-data indicators from eight public providers — the
              World Bank, V-Dem, UCDP and FAOSTAT among them — spanning the economy,
              governance, rights, conflict and society.
            </p>
            <IndicatorTaxonomyTree />
            <p className="mt-3 mb-12 text-sm">
              <Link
                href={"/methodology/indicators" as Route}
                className="border-b pb-0.5 transition-colors hover:text-[var(--qgi-accent)] hover:border-[var(--qgi-accent)]"
                style={{
                  color: "var(--qgi-text-muted)",
                  borderColor: "var(--qgi-border)",
                }}
              >
                Browse all indicators &rarr;
              </Link>
            </p>

            <h3
              className="text-xs tracking-[0.25em] uppercase mb-2"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Events
            </h3>
            <p
              className="text-sm leading-relaxed mb-4"
              style={{ color: "var(--qgi-text)" }}
            >
              Every reading is held against real, verified events, organised into a
              three-layer taxonomy from broad master groups down to specific event types.
            </p>
            <TaxonomyHorizontalTree />
            <p className="mt-3 text-sm">
              <Link
                href={"/methodology/events" as Route}
                className="border-b pb-0.5 transition-colors hover:text-[var(--qgi-accent)] hover:border-[var(--qgi-accent)]"
                style={{
                  color: "var(--qgi-text-muted)",
                  borderColor: "var(--qgi-border)",
                }}
              >
                Browse all verified events &rarr;
              </Link>
            </p>
          </Section>

          {/* How events are verified */}
          <Section id="verification" title="How an event earns its place">
            <p
              className="text-sm leading-relaxed mb-6"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              A trend is only as trustworthy as the events behind it. Here is how every
              event earns its place before it can shape a single reading.
            </p>
            <VerificationFlow />
          </Section>

          {/* Worked example */}
          <Section id="worked-example" title="A worked example">
            <div
              className="rounded-lg border p-6"
              style={{
                borderColor: "var(--qgi-border)",
                backgroundColor: "var(--qgi-surface)",
              }}
            >
              <p
                className="text-sm leading-relaxed mb-3"
                style={{ color: "var(--qgi-text)" }}
              >
                Take the <strong>currency crisis</strong> trend. From the indicators that
                moved together in the run-up to past currency crises, reserves drawing
                down, short-term debt climbing, confidence in the currency slipping, the
                Cascade method distils the shape those crises shared beforehand.
              </p>
              <p
                className="text-sm leading-relaxed mb-3"
                style={{ color: "var(--qgi-text)" }}
              >
                Each quarter the Trajectory Engine asks: which of today&rsquo;s 180+
                countries are tracing that same shape? It ranks every country by
                resemblance and, for the closest ones, shows the historical cases they
                most echo, each with the real event that followed and a public source.
              </p>
              <p
                className="text-sm leading-relaxed"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                You see the working at every step: the signals moving, the canonical shape
                they are measured against, and the precedents behind the reading.
              </p>
              <div className="mt-5 flex items-center gap-4 flex-wrap">
                <Link
                  href={"/trends/currency_crisis" as Route}
                  className="px-5 py-2.5 rounded text-sm font-medium tracking-wide transition-all hover:brightness-110"
                  style={{ backgroundColor: "var(--qgi-accent)", color: "var(--qgi-bg)" }}
                >
                  See the currency-crisis trend
                </Link>
                <Link
                  href={"/trends" as Route}
                  className="text-sm tracking-wide border-b pb-0.5 transition-colors hover:text-[var(--qgi-accent)] hover:border-[var(--qgi-accent)]"
                  style={{
                    color: "var(--qgi-text-muted)",
                    borderColor: "var(--qgi-border)",
                  }}
                >
                  Browse every trend &rarr;
                </Link>
              </div>
            </div>
          </Section>

          {/* Confidence */}
          <Section id="confidence" title="How confident we are">
            <p
              className="text-sm leading-relaxed mb-3"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Not every kind of event leaves the same fingerprint in the data. Some trends
              stand out sharply from everything else; others are fainter. Every trend
              carries a confidence mark for how clearly its shape separates from the
              noise, and that mark travels with it, onto every trend and every country
              reading.
            </p>
            <p
              className="text-sm leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              We lead with the cases we are most confident about and keep the fainter ones
              honestly labelled. You will never see a number presented as more certain
              than it is.
            </p>
          </Section>

          {/* The news layer — News Pulse + verdicts */}
          <Section id="news-layer" title="The news layer">
            <p
              className="text-sm leading-relaxed mb-3"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Trends are structural: shapes learned from decades of indicator history. The
              news layer adds a second, faster reading from the open global news record.
              For the trends that carry enough news to read on their own, we show a
              per-trend <strong style={{ color: "var(--qgi-text)" }}>News Pulse</strong>:
              a <strong style={{ color: "var(--qgi-text)" }}>news pressure</strong> score
              from 0 to 100 for how prominent that trend is in a country&apos;s news this
              month, counted as elevated from 60 upward. Six trends carry a live News
              Pulse today; the remaining high-salience themes sit on a published coverage
              roadmap on the Risk Board. The score is ranked across every covered country
              and month, so a 70 reads high relative to how that trend has run everywhere,
              not just locally.
            </p>
            <p
              className="text-sm leading-relaxed mb-3"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              The two readings never merge into one number. Both run from 0 to 100, and a
              reading counts as elevated from 60 upward. They combine into a verdict for
              each country and trend:
            </p>
            <ul
              className="space-y-2 text-sm leading-relaxed mb-3"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              <li>
                <strong style={{ color: "var(--qgi-warning)" }}>Both Firing.</strong>{" "}
                Structural resemblance and news pressure are both elevated. The
                combinations to open first.
              </li>
              <li>
                <strong style={{ color: "var(--qgi-accent)" }}>News-Only.</strong> The
                news is loud but the structure is not primed. Often noise; worth a glance,
                not an alarm.
              </li>
              <li>
                <strong style={{ color: "var(--qgi-text)" }}>
                  Elevated &amp; Quiet.
                </strong>{" "}
                The structure is elevated while the news stays quiet: two readings on the
                same country that don&apos;t always move together.
              </li>
              <li>
                <strong style={{ color: "var(--qgi-text)" }}>Quiet.</strong> Neither
                reading is elevated.
              </li>
            </ul>
            <p
              className="text-sm leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Each reading earns its standing against the verified event record, election
              by election, crisis by crisis. The{" "}
              <strong style={{ color: "var(--qgi-text)" }}>electoral</strong> and{" "}
              <strong style={{ color: "var(--qgi-text)" }}>economic</strong> readings are
              recall-validated: they light up consistently around known events of each
              type across the covered countries. That was established by aligning every
              verified election and economic crisis at month zero and measuring the news
              pressure in the surrounding months; the signal holds, and for elections
              strengthens, when recomputed using only information available at the time.
              Trends whose news pressure showed no consistent signal around events are not
              marked as validated, and some are shown news-only while their structural
              reading is still being validated. The layer reads {NEWS_COUNTRIES} countries
              today and grows as the signal proves out.
            </p>
          </Section>

          {/* The geopolitical risk layer (GPR) */}
          <Section id="geopolitical-risk" title="The geopolitical risk layer">
            <p
              className="text-sm leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Alongside the trends and the news layer, QGI keeps its own geopolitical-risk
              reading for more than two hundred countries, built from the global news
              record. Across the forty-four countries that carry a published academic
              benchmark, it tracks the same rises and falls in risk, which makes it a
              wider-angle confirmation layer you can set beside the readings above.
            </p>
            <p className="mt-4 text-sm">
              <Link
                href={"/methodology/gpr" as Route}
                className="border-b pb-0.5 transition-colors hover:text-[var(--qgi-accent)] hover:border-[var(--qgi-accent)]"
                style={{
                  color: "var(--qgi-text-muted)",
                  borderColor: "var(--qgi-border)",
                }}
              >
                How we built it &rarr;
              </Link>
            </p>
          </Section>

          {/* How to read a score */}
          <Section id="how-to-read" title="How to read a score">
            <ul
              className="space-y-3 text-sm leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              <li>
                <strong style={{ color: "var(--qgi-text)" }}>
                  It is resemblance, not probability.
                </strong>{" "}
                A country near the top of a trend is tracing a shape that has run ahead of
                that kind of event before. It is not a prediction that the event will
                happen.
              </li>
              <li>
                <strong style={{ color: "var(--qgi-text)" }}>
                  Higher means look closer.
                </strong>{" "}
                Read a strong score as a reason to open the evidence, the signals, the
                canonical shape, the historical analogues, not as a verdict.
              </li>
              <li>
                <strong style={{ color: "var(--qgi-text)" }}>
                  Weaker matches are flagged.
                </strong>{" "}
                When a resemblance is thin or rests on a small base of cases, we say so on
                the reading itself.
              </li>
              <li>
                <strong style={{ color: "var(--qgi-text)" }}>
                  Every reading is datable.
                </strong>{" "}
                Scores are refreshed every quarter and stamped with their date, so you
                always know how current a reading is.
              </li>
            </ul>
          </Section>
        </article>
      </main>

      <PublicFooter />
    </div>
  );
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="py-12 border-b"
      style={{ borderColor: "var(--qgi-border)" }}
    >
      <h2 className="text-xl font-semibold mb-5" style={{ color: "var(--qgi-text)" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function MethodCard({
  title,
  tint,
  children,
}: {
  title: string;
  tint: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-lg border p-5"
      style={{ borderColor: "var(--qgi-border)", backgroundColor: "var(--qgi-bg)" }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: 3,
            backgroundColor: tint,
            display: "inline-block",
          }}
        />
        <h3 className="text-base font-semibold" style={{ color: "var(--qgi-text)" }}>
          {title}
        </h3>
      </div>
      <p className="text-sm leading-relaxed" style={{ color: "var(--qgi-text-muted)" }}>
        {children}
      </p>
    </div>
  );
}

function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded-lg border p-5"
      style={{ borderColor: "var(--qgi-border)", backgroundColor: "var(--qgi-bg)" }}
    >
      <h3 className="text-sm font-semibold mb-2" style={{ color: "var(--qgi-text)" }}>
        {title}
      </h3>
      <p
        className="text-[13px] leading-relaxed"
        style={{ color: "var(--qgi-text-muted)" }}
      >
        {children}
      </p>
    </div>
  );
}
