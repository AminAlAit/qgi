import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";

export const metadata: Metadata = {
  title: "The margin keeps widening · QGI Blog",
  description:
    "V1.8 → V1.8.1 → V1.9: the gap between QGI's F1 and the naïve persistence baseline has grown at every release. A walk-through of what the number does, doesn't, and shouldn't prove.",
  alternates: {
    canonical: "https://qgintelligence.com/blog/margin-over-persistence-trajectory",
  },
  openGraph: {
    title: "The margin keeps widening",
    description:
      "V1.8 → V1.8.1 → V1.9: the gap between QGI's F1 and the naïve persistence baseline has grown at every release.",
    url: "https://qgintelligence.com/blog/margin-over-persistence-trajectory",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: "2026-04-22T00:00:00Z",
    images: [
      {
        url: "https://qgintelligence.com/blog/margin_trajectory.png",
        width: 1500,
        height: 900,
        alt: "Margin-over-persistence trajectory chart",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "The margin keeps widening",
    description:
      "V1.8 → V1.8.1 → V1.9: the gap between QGI and the naïve baseline has grown at every release.",
    images: ["https://qgintelligence.com/blog/margin_trajectory.png"],
  },
};

export default function MarginTrajectoryPost() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <ArticleJsonLd
        headline="The margin keeps widening"
        description="V1.8 → V1.8.1 → V1.9: the gap between QGI's F1 and the naïve persistence baseline has grown at every release."
        url="https://qgintelligence.com/blog/margin-over-persistence-trajectory"
        datePublished="2026-04-22T00:00:00Z"
        imageUrl="https://qgintelligence.com/blog/margin_trajectory.png"
      />
      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-4xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="nav" href="/" title="Home" />
          <Link
            href="/blog"
            className="text-xs tracking-wider uppercase"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            ← All posts
          </Link>
        </div>
      </header>

      <article className="mx-auto max-w-3xl px-6 py-16">
        <div className="mb-10">
          <div
            className="text-[10px] tracking-widest uppercase mb-3"
            style={{ color: "var(--qgi-accent)" }}
          >
            <time dateTime="2026-04-22">2026-04-22</time> · Backtest · V1.9
          </div>
          <h1 className="text-4xl font-semibold mb-5 leading-tight">
            The margin keeps widening
          </h1>
          <p
            className="text-lg leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            Raw F1 is the wrong number to look at. Here&apos;s the one we watch instead,
            and why it has grown at every QGI release since February.
          </p>
        </div>

        <div
          className="prose max-w-none text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          <p>
            Every time a forecasting model ships a new version, the question is the same:
            is it actually better? F1 is the default answer: a single number between 0 and
            1 summarising precision and recall.
          </p>

          <p>
            The problem with F1 alone is that it depends on how hard the evaluation set
            is. If you change the set of countries you evaluate on, or the set of events
            you score against, F1 moves for reasons that have nothing to do with the model
            itself. You can watch F1 tick up while your model is quietly getting worse:
            the eval just got easier.
          </p>

          <p>
            <strong>Margin over persistence</strong> is the metric that keeps us honest.
            It subtracts the F1 of a trivial baseline (&ldquo;next year&apos;s events
            equal this year&apos;s events&rdquo;, i.e. persistence) from the model&apos;s
            F1. If the eval set changes, both numbers move together. The gap is what the
            model is actually contributing.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">The last three releases</h2>

          <p>Here is the trajectory for QGI&apos;s scoring releases since February:</p>

          <div
            className="rounded-lg border overflow-hidden my-6"
            style={{
              borderColor: "var(--qgi-border)",
              backgroundColor: "var(--qgi-surface)",
            }}
          >
            <Image
              src="/blog/margin_trajectory.png"
              alt="Margin-over-persistence trajectory across QGI V1.8 (+0.067), V1.8.1 (+0.143), and V1.9 (+0.189). Model F1 roughly flat around 0.48-0.50; persistence F1 falling from 0.438 to 0.292 as the eval harness tightened."
              width={1500}
              height={900}
              className="w-full h-auto"
              priority
            />
            <div className="px-4 py-3 text-xs" style={{ color: "var(--qgi-text-dim)" }}>
              Backtest: walk-forward, validate on 2015, test on 2020. Test ground-truth:
              649 (country, category) pairs.
            </div>
          </div>

          <p>
            Three releases, three margins: <strong>+0.067</strong> (V1.8, mid-April),{" "}
            <strong>+0.143</strong> (V1.8.1, a week later), <strong>+0.189</strong> (V1.9,
            this past week). Model F1 has oscillated between 0.48 and 0.51 the entire
            time. Persistence F1 has been crushed: 0.438 → 0.336 → 0.292.
          </p>

          <p>
            That pattern is load-bearing. It says the model has kept its absolute
            performance while the eval has gotten progressively harder on the naïve
            baseline. The naïve baseline is what we have to beat to justify shipping. The
            gap is the amount of real signal in the output.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Where the widening actually came from
          </h2>

          <p>
            This is the part where it&apos;s tempting to claim the model is getting
            smarter. It isn&apos;t, or at least not in proportion to the margin growth.
            Most of the gap widening comes from the{" "}
            <em>evaluation harness getting more honest</em>:
          </p>

          <ul className="list-disc pl-6 space-y-2">
            <li>
              <strong>V1.8 → V1.8.1</strong> introduced category-stratified risk-tier
              labels. The ground-truth set grew from 294 to 403 pairs as more countries
              came into curated coverage. Persistence tanked because the new harder
              countries were exactly the ones that don&apos;t repeat year-over-year.
            </li>
            <li>
              <strong>V1.8.1 → V1.9</strong> moved to verified-only events (a stricter
              labelling invariant, ~7,500 events from ~13,500 candidates), added 5 FAO
              food-security indicators to the 69 World Bank ones, and widened the country
              scope from the 55 curated to all 214. Ground truth grew again to 649 pairs.
              Persistence dropped another 0.04.
            </li>
          </ul>

          <p>
            So the honest read is: we&apos;re not producing a dramatically better model,
            but we are producing a model that holds up under a substantially more
            adversarial evaluation harness. For a statistical recipe system that
            hasn&apos;t changed its core algorithm since V1.8, that&apos;s the right kind
            of durability.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What this number does not prove
          </h2>

          <p>
            Margin over persistence is a ranking-quality metric. It tells you the model
            orders predictions usefully. It does <strong>not</strong> tell you the
            probability estimates are well-calibrated: that &ldquo;HIGH&rdquo; actually
            corresponds to 70% realisation rates rather than 40%.
          </p>

          <p>
            For that, we look at Brier Skill Score. V1.9 crossed positive BSS on short-
            and medium-pattern tiers during validation (+0.017 and +0.009, first time in
            QGI&apos;s history). Test-phase BSS remained negative across every tier (−0.16
            to −0.24). The validation-to-test gap is the clearest signal that the
            statistical recipe system is at a calibration ceiling.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What V1.9.1 changes, and what it doesn&apos;t
          </h2>

          <p>
            The release that shipped the same day as this post,{" "}
            <strong>V1.9.1 (Fix C)</strong>, tightens the threshold logic that decides
            which countries end up in the HIGH risk tier. It fixed a diagnostic bug where
            68% of scored countries were rated HIGH, including stable democracies whose
            top category was nothing more severe than &ldquo;elections and voting.&rdquo;
            The fix dropped the share to ~37%, inside the target band.
          </p>

          <p>
            Because the fix changes tier-labeling rather than ranking, it doesn&apos;t
            move F1, doesn&apos;t move margin, and doesn&apos;t move any of the numbers in
            the chart above. The backtest metrics for V1.9.1 are identical to V1.9. We
            could have re-run the backtest and produced a V1.9.1 JSON with exactly the
            same numbers; we chose not to, since the run would have cost AWS credits for
            zero information gain.
          </p>

          <p>
            The <em>next</em> release, V1.9.2 (Fix D), will change the actual salience
            scores: it replaces per-country z-score normalization with cross-country
            per-category normalization. That one we will re-backtest, because the ranking
            changes. If the calibration ceiling moves, it&apos;ll show up in the next
            version of this trajectory chart.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What we&apos;re watching next
          </h2>

          <p>
            Two things. First, whether V1.9.2 lifts test-phase BSS into positive territory
            on at least one tier: that would be the first evidence the calibration ceiling
            is breakable without switching to a gradient-boosted model. Second, whether
            the margin keeps widening. Four releases with monotonically growing margin is
            a pattern worth watching; five would start to be a track record.
          </p>

          <p>We&apos;ll post the V1.9.2 numbers when they land. Probably in 2-3 weeks.</p>
        </div>

        <footer
          className="mt-16 pt-8 border-t text-sm leading-relaxed space-y-2"
          style={{
            borderColor: "var(--qgi-border)",
            color: "var(--qgi-text-dim)",
          }}
        >
          <p>
            Source data and chart generator: <code>qgi-ml/backtest_v19_results.json</code>{" "}
            + <code>qgi-ml/scripts/plot_pr_curve.py</code>. Full V1.9 backtest
            retrospective lives in the internal repo; the methodology page carries the
            public version.
          </p>
          <p>
            See also:{" "}
            <Link
              href="/methodology"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Methodology
            </Link>
            {" · "}
            <Link
              href="/blog"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              All posts
            </Link>
            .
          </p>
        </footer>
      </article>
    </div>
  );
}
