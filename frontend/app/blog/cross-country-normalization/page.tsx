import type { Metadata } from "next";
import Link from "next/link";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";

export const metadata: Metadata = {
  title: "Cross-country normalization meets the data · QGI Blog",
  description:
    "We proposed replacing per-country z-score normalization with a cross-country global approach. An Athena-backed simulation surfaced three problems. Here's the finding, and why we're shelving V1.9.2 until event-curation coverage grows.",
  alternates: {
    canonical: "https://qgintelligence.com/blog/cross-country-normalization",
  },
  openGraph: {
    title: "Cross-country normalization meets the data",
    description:
      "We proposed a structural calibration rewrite. An Athena-backed simulation surfaced three problems before we shipped. Here's what we found.",
    url: "https://qgintelligence.com/blog/cross-country-normalization",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: "2026-04-22T00:00:00Z",
  },
  twitter: {
    card: "summary",
    title: "Cross-country normalization meets the data",
    description:
      "A proposed rewrite for V1.9.2. An Athena-backed simulation. Three problems. Shelved.",
  },
};

export default function CrossCountryNormalizationPost() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <ArticleJsonLd
        headline="Cross-country normalization meets the data"
        description="We proposed replacing per-country z-score normalization with a cross-country global approach. An Athena-backed simulation surfaced three problems before we shipped."
        url="https://qgintelligence.com/blog/cross-country-normalization"
        datePublished="2026-04-22T00:00:00Z"
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
            <time dateTime="2026-04-22">2026-04-22</time> · Methodology · V1.9.2
          </div>
          <h1 className="text-4xl font-semibold mb-5 leading-tight">
            Cross-country normalization meets the data
          </h1>
          <p
            className="text-lg leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            We proposed replacing per-country z-score normalization with a cross-country
            global approach. An Athena-backed simulation surfaced three problems before we
            shipped. Here&apos;s the finding, and why we&apos;re shelving the release
            until the data grows.
          </p>
        </div>

        <div
          className="prose max-w-none text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          <p>
            The{" "}
            <Link
              href="/blog/margin-over-persistence-trajectory"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              previous post
            </Link>{" "}
            described V1.9.1 as a tactical band-aid, with V1.9.2 as the real structural
            fix coming in two or three weeks. That V1.9.2 is not going to ship on that
            timeline. Not because the idea is bad, but because a simulation we ran today
            found three problems with it that only show up when you look at real data
            across enough countries. The release is shelved.
          </p>

          <p>This post walks through what we did, what we found, and what it changes.</p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What the rewrite was supposed to do
          </h2>

          <p>
            V1.9.1 shipped with a diagnostic bug: <em>per-country</em> z-score
            normalization inflated a few signals that didn&apos;t deserve it. Cape
            Verde&apos;s elections-and-voting signal sat 2.78 standard deviations above
            Cape Verde&apos;s own other categories, but globally, Cape Verde&apos;s
            elections activity is ordinary. A small country with one noisy category looked
            like a crisis; a large country with five elevated categories looked average.
          </p>

          <p>
            The proposed V1.9.2 rewrite was to repair the math. Instead of normalizing{" "}
            <em>within</em> each country, normalize each category <em>across</em> all
            countries, what we call <strong>cross-country normalization</strong>.
            Syria&apos;s civil war signal gets compared to every country&apos;s civil war
            signal, not to Syria&apos;s own other categories. Under this approach, every
            category lives on the same standardized scale, and a single threshold
            separates HIGH from MODERATE. No three-layer patch.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">The test</h2>

          <p>
            Before shipping, we ran the new math against staging data. A first pass used
            an approximation: the per-country z-scores from V1.9.1 as input. That failed:
            the output JSON only carries the top ten categories per country, so the full
            population of low-signal countries wasn&apos;t available to compute a
            meaningful global mean.
          </p>

          <p>
            A second pass queried Athena directly for raw recipe scores across every
            country in every category, including zeros. This is what the math actually
            needs. We applied the cross-country normalization, swept a single HIGH
            threshold from 0 to 5 in 0.1-point steps, and measured two things:
            face-validity (do known crisis countries still rank HIGH?) and tier
            distribution (does HIGH share land in our target 25–45% band?). Total spend:
            under a dollar in Athena queries. Total time: about thirty minutes.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Finding 1: rare-signal countries outranked active war zones
          </h2>

          <p>
            Under the cross-country approach, the top of the global salience distribution
            looks like this: Bhutan (top signal: <code>economic_liberalization</code> from
            the 1970s), Argentina and Chile (<code>economic_nationalization</code>),
            Guatemala (<code>volcanic_eruption</code>), South Korea (historical{" "}
            <code>humanitarian_crisis</code>). Syria, Yemen, Afghanistan, Somalia (all
            with active armed conflict) ranked below them.
          </p>

          <p>
            The mechanism: rare categories have a handful of non-zero countries against a
            floor of zeros. A category where only five countries have any data pulls
            global mean close to zero and lets those five countries score many standard
            deviations above the mean. Meanwhile, common crisis categories like{" "}
            <code>civil_war_and_insurgency</code> are populated across fifty-plus
            countries with varying elevations: Syria&apos;s civil war signal is elevated,
            but so is Yemen&apos;s and Somalia&apos;s. No single country reaches the
            extreme z-scores that rare-category outliers do.
          </p>

          <p>
            Category severity weighting was supposed to correct for this: low-severity
            categories like <code>economic_liberalization</code> are weighted at 0.4 or
            0.6, not 1.0. It didn&apos;t correct enough. The numerical floor of each
            weighted z was still dominant.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Finding 2: face validity and the HIGH-share band are incompatible
          </h2>

          <p>
            At threshold 3.2, 11 out of 11 testable face-validity countries rank
            correctly. But 82% of scored countries land HIGH. At threshold 4.0, HIGH share
            drops to 44% (inside target band), but Syria, Somalia, Yemen, Afghanistan,
            Lebanon, Iran, and Ukraine all demote to MODERATE. Face validity falls to
            4/11.
          </p>

          <p>
            There is no threshold in the sweep where both constraints hold. The shape of
            the distribution (a tail of rare-signal outliers at the top, a dense cluster
            of active-conflict countries in the middle) forbids it.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Finding 3: the test cases aren&apos;t in the data
          </h2>

          <p>
            Cape Verde, Denmark, and Germany, the false-positive test cases that motivated
            V1.9.1&apos;s patch and would be the primary validation for V1.9.2,
            aren&apos;t in the staging recipes table. They filter out because they
            don&apos;t have enough curated events to hit the scoring floor. We cannot
            validate the fix for the exact problem the fix was designed to solve until
            event-curation coverage expands.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            One prediction that did hold
          </h2>

          <p>
            Venezuela. V1.9.1 scored Venezuela INDICATIVE, which was a known face-validity
            miss. The cross-country approach flipped Venezuela to HIGH, via{" "}
            <code>currency_crisis</code> at the XL pattern length, with a salience of
            4.09. The direction matched our design-doc prediction; the specific driving
            category was different (we predicted political_repression, not
            currency_crisis). The simulation picked up the right answer through a slightly
            different path, which is the kind of thing a simulation is for.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Why we&apos;re shelving instead of patching
          </h2>

          <p>Three options were on the table after the simulation:</p>

          <ul className="list-disc pl-6 space-y-2">
            <li>
              <strong>Patch cross-country normalization.</strong> Log-transform the raw
              scores before the z-score calculation (compresses rare-category outliers).
              Or filter out low-severity categories entirely. Or only score against a
              whitelist of risk-relevant categories.
            </li>
            <li>
              <strong>Abandon and escalate to a hierarchical model.</strong> A partial
              pooling approach that shrinks small-country scores toward regional priors.
              It addresses the Cape Verde symptom more directly, but is a larger
              engineering project.
            </li>
            <li>
              <strong>Wait for more data, then re-simulate.</strong> 89 staging countries
              is a biased sample. More countries will shift the global distribution shape
              in ways that may resolve the outlier problem without structural changes.
            </li>
          </ul>

          <p>
            We&apos;re choosing the third option, with the decision revisited once our
            curated-event coverage reaches 190+ countries (up from 89 in staging today,
            ~173 in the curated working set). Here&apos;s why:
          </p>

          <ul className="list-disc pl-6 space-y-2">
            <li>
              More countries means more zero-fill for crisis categories, which pushes
              global mean down and gives real crisis signals more room to separate from
              the pack.
            </li>
            <li>
              The countries we can&apos;t currently test (Cape Verde, Denmark, Germany)
              re-enter the data as curation catches up. Without them, we can&apos;t
              honestly claim the rewrite fixes anything.
            </li>
            <li>
              Several of the structural patches may turn out to be unnecessary at higher
              N. Understanding the data shape before committing to a patch avoids
              re-patching later.
            </li>
          </ul>

          <p>
            The evidence package from today&apos;s simulation is preserved. When data
            coverage reaches threshold, an internal methodology review picks up from
            today&apos;s findings; the decision tree doesn&apos;t reset.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What&apos;s shipping next instead
          </h2>

          <p>
            V1.9.1 stays in production. The tier distribution, drift monitoring, and
            methodology page are all calibrated against it. We have the numbers we have.
          </p>

          <p>
            The top priority moves to event curation on Ukraine and Venezuela, the two
            known V1.9.1 face-validity misses that the rewrite was supposed to absorb.
            Iran stays deferred. These aren&apos;t glamorous; they&apos;re adding verified
            events per country one batch at a time. They&apos;re also what actually
            unblocks the next iteration.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">Why this matters</h2>

          <p>
            Most forecasting products don&apos;t publish failed simulations. The incentive
            is to ship the version number and claim the win. The alternative is what
            happened this week: test the next release before shipping, find that it
            doesn&apos;t work the way the design doc claimed, decide honestly.
          </p>

          <p>
            If we hadn&apos;t run the simulation, in three weeks we would have shipped
            V1.9.2 on schedule and quietly hoped nobody noticed that Bhutan was flagged
            HIGH. Instead we spent less than a dollar on Athena queries, changed our mind,
            and wrote this post.
          </p>

          <p>
            That&apos;s the process. The version numbers we publish are what we actually
            believe. When the answer is &ldquo;we don&apos;t know yet, we&apos;re waiting
            for better data,&rdquo; that&apos;s what we say.
          </p>
        </div>

        <footer
          className="mt-16 pt-8 border-t text-sm leading-relaxed space-y-2"
          style={{
            borderColor: "var(--qgi-border)",
            color: "var(--qgi-text-dim)",
          }}
        >
          <p>
            Simulation code and results are preserved in our internal ML repository. The
            design doc with the shelved-findings addendum is public; it lives alongside
            the methodology page.
          </p>
          <p>
            See also:{" "}
            <Link
              href="/blog/margin-over-persistence-trajectory"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              The margin keeps widening
            </Link>
            {" · "}
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
