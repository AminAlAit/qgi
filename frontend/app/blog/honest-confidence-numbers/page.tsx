import type { Metadata } from "next";
import Link from "next/link";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";

export const metadata: Metadata = {
  title: "Why our confidence numbers just went down — on purpose · QGI Blog",
  description:
    "34 of our 42 live recipe confidence scores were overstated, a multiple-comparisons artifact from picking the best of nine candidate windows. We re-measured every recipe with one honest protocol, corrected the 34 that didn't hold up, and left the 8 that did.",
  alternates: {
    canonical: "https://qgintelligence.com/blog/honest-confidence-numbers",
  },
  openGraph: {
    title: "Why our confidence numbers just went down — on purpose",
    description:
      "34 of 42 live recipe confidence scores were overstated. We re-measured every one with a single honest protocol, corrected 34, and left 8 unchanged. Here's the method and the evidence.",
    url: "https://qgintelligence.com/blog/honest-confidence-numbers",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: "2026-07-12T00:00:00Z",
  },
  twitter: {
    card: "summary",
    title: "Why our confidence numbers just went down — on purpose",
    description:
      "34 of 42 live recipe confidence scores were overstated. We re-measured every one honestly and corrected them. A number you can't reproduce is worse than a lower one you can.",
  },
};

export default function HonestConfidenceNumbersPost() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <ArticleJsonLd
        headline="Why our confidence numbers just went down — on purpose"
        description="34 of our 42 live recipe confidence scores were overstated, a multiple-comparisons artifact from picking the best of nine candidate windows. We re-measured every recipe with one honest protocol, corrected the 34 that didn't hold up, and left the 8 that did."
        url="https://qgintelligence.com/blog/honest-confidence-numbers"
        datePublished="2026-07-12T00:00:00Z"
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
            <time dateTime="2026-07-12">2026-07-12</time> · Methodology · Fleet audit
          </div>
          <h1 className="text-4xl font-semibold mb-5 leading-tight">
            Why our confidence numbers just went down — on purpose
          </h1>
          <p
            className="text-lg leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            Thirty-four of our forty-two live recipe confidence scores were quietly
            overstating themselves, a textbook multiple-comparisons artifact, not a bug
            and not fraud. We re-measured every recipe with one honest protocol, corrected
            the thirty-four that didn&apos;t hold up, and left the eight that did. Here is
            the method, the evidence, and why we think a number you can reproduce beats
            one you can&apos;t.
          </p>
        </div>

        <div
          className="prose max-w-none text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          <p>
            Every live QGI recipe carries one headline number: a discrimination score, an
            AUC, rendered on its trend page as a percentage. &ldquo;This recipe scores
            78%.&rdquo; That number is supposed to answer one question honestly: across
            historical crises, how well did this recipe separate the years before an event
            from the ordinary years in a country it had never seen? We just re-measured
            all 42 of them, found that 34 were overstating themselves, and turned every
            one of those numbers down. This post explains why we consider that an
            improvement.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            How a confidence number gets flattered
          </h2>

          <p>
            Building a recipe means testing a shortlist of candidate time-windows against
            the historical record, three years, eight, eighteen, and keeping the one that
            discriminates best. That step, on its own, is ordinary and legitimate model
            selection. The problem was what happened next: the AUC we published was the
            score from the winning window, measured on the same walk that picked it.
          </p>

          <p>
            That is the textbook shape of an optimistic estimate. Imagine testing a drug
            on nine separate patient cohorts and reporting the result from whichever
            cohort happened to respond best, without disclosing the other eight. The
            number you would publish is real, in the sense that some cohort genuinely did
            respond that well. It is also systematically too good, because it survived a
            filter built to find the best-looking result out of nine tries. Our
            recipe-fleet walk had the same shape: nine candidate windows, one argmax, one
            published number.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            One honest protocol, the whole fleet
          </h2>

          <p>
            We re-measured every one of the 42 live recipes with a single honest protocol:
            leave-one-country-out cross-validation. For each recipe, we held out one
            country at a time, refit the recipe on everyone else, and asked how well it
            separated that held-out country&apos;s pre-crisis years from its quiet ones,
            repeated across every country in the recipe&apos;s evidence base. The
            candidate window is still chosen the same way as before; what changed is that
            the published number now comes from a walk that never saw the held-out
            country, rather than from the walk that picked the window.
          </p>

          <p>
            This is not a new method invented for this exercise. It is the same protocol
            we had already used to correct two recipes individually:{" "}
            <strong>banking_and_financial_crisis</strong>, whose live number came down
            from 77% to 64% after we found its original evidence set skewed toward
            advanced economies and missing most of the major emerging-market crises, and{" "}
            <strong>military_coup</strong>, which nudged from 69% to 65% on the same
            re-measurement. Applying that protocol to the rest of the fleet was the
            obvious next step. This time we ran it against all 42 live recipes at once
            rather than one at a time.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What the honest measurement found
          </h2>

          <p>
            34 of the 42 recipes were overstating themselves. The typical drop was about 6
            points of AUC; the worst was 17. Eight recipes held up with no meaningful
            change at all.
          </p>

          <p>
            We did not take that at face value either. Two checks ran before anything
            shipped:
          </p>

          <ul className="list-disc pl-6 space-y-2">
            <li>
              <strong>Window-fragility sweep.</strong> For each of the 34, we swept every
              one of the nine candidate windows against the current evidence base and
              asked whether the originally published number was reachable anywhere. It was
              not, on any window, for any of the 34. Zero exceptions.
            </li>
            <li>
              <strong>Recipe-specificity check.</strong> If the honest protocol itself
              were simply biased downward, it would drag every recipe down by roughly the
              same amount. It did not: eight recipes reproduced their original number
              almost exactly under the identical method. The gap is a property of each
              recipe&apos;s original window-selection, not an artifact of how we are
              measuring it now.
            </li>
          </ul>

          <p>
            The two recipes we had already corrected individually gave us a clean sanity
            check for the fleet-wide pass: run the same honest protocol at scale, and
            banking_and_financial_crisis and military_coup should land back on the numbers
            we had already published for them. They did, 0.638 and 0.652, to the decimal,
            with no fitting required to get there. That is the strongest piece of evidence
            we have that the fleet-wide correction is measuring the same thing, at scale,
            that we had already stood behind at retail.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">What changed on the site</h2>

          <p>
            Three things changed, together, as one update rather than three separate ones.
          </p>

          <p>
            The 34 overstated numbers came down, on every surface that shows them: the
            trend tiles, each recipe&apos;s detail page, and the fleet-wide{" "}
            <Link
              href="/blog/trend-tracker"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Trend Tracker
            </Link>
            . Among the corrected 34, eight had an extra property worth flagging on its
            own: their honest AUC is not just lower, it is less stable, moving by three
            points or more depending on which countries happen to land in the held-out
            sample. For those, we widened the published confidence band rather than
            presenting a clean point estimate that implies more precision than the
            measurement actually has.
          </p>

          <p>
            And we changed the words around the numbers. Recipe pages used to describe a
            recipe&apos;s key indicators as what is &ldquo;driving&rdquo; a trend. These
            are statistical associations between a country&apos;s trajectory and a
            historical outcome, not a demonstrated causal mechanism, and the language now
            says so: indicators that move with a trend, not indicators that drive it.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Why a lower number is the better number
          </h2>

          <p>
            We are not in the business of publishing the highest number a recipe can be
            made to produce. We are in the business of publishing the number that will
            still be there the next time someone checks. A confidence score you can&apos;t
            reproduce is not a lower-quality version of a good number; it is a different
            kind of thing, and it is worse than an honest number that happens to be
            smaller.
          </p>

          <p>
            What is left, honestly measured, is modest. Across the corrected fleet the
            honest AUCs run from roughly 0.55 to 0.75: meaningfully better than a coin
            flip, in some cases considerably so, nowhere close to a crystal ball.
            We&apos;d rather say exactly that than let a flattering percentage imply more
            than the recipe has earned.
          </p>

          <p>
            We also checked the other direction before settling on this. Separately from
            the correction itself, we spent time trying to raise these numbers honestly:
            adding new indicators to recipes and re-measuring under the same protocol,
            across five trends. None of the five produced an honest gain. That is not
            proof that every recipe is at its absolute ceiling forever, but it is evidence
            that the honest numbers we are publishing now are not the result of giving up
            early on a higher, true number. We tried the legitimate way up, and it did not
            move. Telling the truth about where that leaves us is the more useful thing to
            publish than pretending otherwise.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">What didn&apos;t change</h2>

          <p>
            The recipes themselves are the same: the same key indicators, the same
            aggregation logic, the same historical corpus each one draws on. The
            validation gates every recipe has to clear before it ships are the same, if
            anything more strictly enforced now that we have run this audit. Country
            coverage did not change. What changed is the number attached to each recipe,
            and the words we use to describe what that number means. We would rather ship
            42 numbers we can defend than 42 numbers that look better and do not survive a
            second look.
          </p>

          <p>
            The corrected numbers are live now across every trend page and on the{" "}
            <Link
              href="/blog/trend-tracker"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Trend Tracker
            </Link>
            , which will keep tracking every recipe&apos;s status the same honest way
            going forward.
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
            The audit behind this correction, the window-fragility sweep, the
            recipe-specificity check, and the per-recipe confidence bands, is preserved in
            our internal ML repository. Every number in this post traces back to it.
          </p>
          <p>
            See also:{" "}
            <Link
              href="/blog/trend-tracker"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Trend Tracker
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
