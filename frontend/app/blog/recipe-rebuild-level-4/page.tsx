import type { Metadata } from "next";
import Link from "next/link";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";

// TODO: generate OG image at /public/blog/recipe-level-4.png — Amin to handle
// separately. Fallback in ArticleJsonLd is /og-default.png if file missing.

export const metadata: Metadata = {
  title: "What we mean when we say 'Recipe' · QGI Blog",
  description:
    "The word 'Recipe' on our methodology page has been doing more rhetorical work than the code. Here is the gap, why it opened, and what the V2.0 rebuild changes.",
  alternates: {
    canonical: "https://qgintelligence.com/blog/recipe-rebuild-level-4",
  },
  openGraph: {
    title: "What we mean when we say 'Recipe'",
    description:
      "The word 'Recipe' on our methodology page has been doing more rhetorical work than the code. Here is the gap, why it opened, and what the V2.0 rebuild changes.",
    url: "https://qgintelligence.com/blog/recipe-rebuild-level-4",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: "2026-04-26T00:00:00Z",
    images: [
      {
        url: "https://qgintelligence.com/blog/recipe-level-4.png",
        width: 1500,
        height: 900,
        alt: "Diagram of QGI's four-level data model: SCDI, Pattern, Pattern Instance, Recipe.",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "What we mean when we say 'Recipe'",
    description:
      "The word on our methodology page has been doing more rhetorical work than the code. Here is the gap, and the V2.0 rebuild that closes it.",
    images: ["https://qgintelligence.com/blog/recipe-level-4.png"],
  },
};

export default function RecipeRebuildLevel4Post() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <ArticleJsonLd
        headline="What we mean when we say 'Recipe'"
        description="The word 'Recipe' on our methodology page has been doing more rhetorical work than the code. Here is the gap, why it opened, and what the V2.0 rebuild changes."
        url="https://qgintelligence.com/blog/recipe-rebuild-level-4"
        datePublished="2026-04-26T00:00:00Z"
        imageUrl="https://qgintelligence.com/blog/recipe-level-4.png"
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
            <time dateTime="2026-04-26">2026-04-26</time> · Methodology · V2.0
          </div>
          <h1 className="text-4xl font-semibold mb-5 leading-tight">
            What we mean when we say &ldquo;Recipe&rdquo;
          </h1>
          <p
            className="text-lg leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            The word on our methodology page has been doing more rhetorical work than the
            code. Here is the gap we found, why it opened, and what the V2.0 rebuild
            changes.
          </p>
        </div>

        <div
          className="prose max-w-none text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          <p>
            QGI began with a single observation: two countries from different regions,
            examined across a handful of economic and governance indicators, showed
            strikingly similar trajectories in the years before major geopolitical shocks.
            The one that walked the path earlier experienced a defined shock at the end of
            its window. The one that followed the same path several years later
            experienced one too. The pitch that followed, and the pitch that has carried
            QGI for two years, is this: countries walk the same paths at different times,
            and if we can describe the path well enough we can tell a country it is on one
            before the path ends.
          </p>

          <p>
            That description (the path itself, abstracted away from any one country, with
            a typical length and a typical cast of indicators) is what we have been
            calling a <strong>Recipe</strong>. The methodology page says so. The blog
            posts assume so. Every conversation we have with an analyst, a journalist, or
            a prospective customer leans on it.
          </p>

          <p>
            Last week we did a code-vs-concept audit and found that the Recipe described
            on the methodology page is not the Recipe in the code. The two have been
            different things since the very first version. This post walks through what we
            found, why it took this long to name it, and what the next three weeks of
            engineering work (versioned as V2.0) will change.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Three levels exist; four are needed
          </h2>

          <p>
            QGI&apos;s data model has three layers today. The methodology page describes
            them faithfully. The first layer, an SCDI, is one indicator&apos;s trajectory
            in country A correlating with the same indicator in country B over a shared
            window. The second layer, a Pattern, is a bundle of those SCDIs between the
            same two countries on the same window. The third layer, the one the code
            currently labels &ldquo;Recipe,&rdquo; is a Pattern that has been matched to a
            known historical event in country B: the analogue, with its real-world ending
            attached.
          </p>

          <p>
            The fourth layer, the one the methodology page implies and the code does not
            build, is the abstraction across all of those event-matched Patterns. The
            canonical length. The indicator fingerprint. The function that takes a country
            today and asks how close its current trajectory is to the typical shape of
            those analogues. Here is the shape, side by side:
          </p>

          {/* Scroll wrapper: the ASCII diagram is ~66 chars wide; on phones it
              overflows. overflow-x-auto lets the user pan. The right-side
              gradient hint makes scrollability discoverable without JS. */}
          <div className="relative my-6">
            <div
              className="rounded-lg border overflow-x-auto"
              style={{
                borderColor: "var(--qgi-border)",
                backgroundColor: "var(--qgi-surface)",
              }}
            >
              <pre
                className="font-data text-[11px] leading-relaxed p-5 m-0 whitespace-pre"
                style={{ color: "var(--qgi-text)", minWidth: "min-content" }}
              >{`  TODAY (Level 3): one row per matched Pattern instance
  ┌──────────────────────────────────────────────────────────────┐
  │ recipe_id     country_a   country_b   start_a   length       │
  │ event_category   event_year_a   event_year_b   pps           │
  ├──────────────────────────────────────────────────────────────┤
  │  ...sa-az-2011-5-military_conflict   sa  az  2011  5  ...    │
  │  ...sa-az-2010-6-military_conflict   sa  az  2010  6  ...    │
  │  ...sa-az-2009-7-military_conflict   sa  az  2009  7  ...    │
  │  ...sa-tr-2008-8-military_conflict   sa  tr  2008  8  ...    │
  │  ...iq-az-2010-6-military_conflict   iq  az  2010  6  ...    │
  │   (millions of rows; the abstraction is implicit)            │
  └──────────────────────────────────────────────────────────────┘

  V2.0 (Level 4): one row per event category
  ┌──────────────────────────────────────────────────────────────┐
  │ event_category : military_conflict                           │
  │ canonical_length : 6 yrs (median; IQR 5-8)                   │
  │ length_distribution : [(5, 14%), (6, 31%), (7, 22%), ...]    │
  │ indicator_fingerprint :                                       │
  │   energy_exports_pct_gdp     : 78% (CI 71-84)                │
  │   external_debt_pct_gni      : 64% (CI 56-72)                │
  │   military_expenditure_share : 51% (CI 43-59)                │
  │   ...                                                        │
  │ n_distinct_country_pairs : 47                                │
  │ coverage_bias_diagnostic : 11/47 OECD, 36/47 non-OECD        │
  │ similarity(country C, this Recipe) -> 0..1                   │
  └──────────────────────────────────────────────────────────────┘`}</pre>
            </div>
            {/* Right-edge scroll hint: fades out on tablet/desktop where no
                scroll is needed (the content fits). Pure CSS, no JS. */}
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 right-0 w-8 rounded-r-lg sm:hidden"
              style={{
                background: "linear-gradient(to right, transparent, var(--qgi-surface))",
              }}
            />
          </div>

          <p>
            The level-3 table is what we have. It is not wrong: every row is a real
            country pair, a real shared trajectory, a real historical event. But it is not
            what the methodology page describes. The page promises the level-4 entity: the
            abstracted recipe, against which a country today can be scored. We have been
            computing a different thing, a count of how densely the level-3 rows cluster
            around each country, and labelling the result with the level-4 word.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">How the gap opened</h2>

          <p>
            The gap is old. It opened the first time we wrote &ldquo;Recipe&rdquo; in code
            and assumed the abstraction step would follow. The abstraction step never got
            built, partly because the level-3 table was useful enough to drive the early
            dashboards, partly because each new shipped version felt like a more urgent
            target than the one underneath it. Each release made the gap feel further from
            the next deadline. None of the V1.x backtests required the level-4 entity to
            exist. The salience score that ranks countries on the live site is built from
            the density of level-3 rows; it works as a ranking signal and is described
            honestly enough on the methodology page&apos;s scoring section. The
            methodology page&apos;s opening (&ldquo;countries walk the same path&rdquo;)
            is the part that has been ahead of the code.
          </p>

          <p>
            We do not think this is a uniquely QGI mistake. Anyone shipping a research
            product in public will recognise the pattern: a vocabulary forms early, the
            implementation chases the vocabulary at varying speeds, and the gap between
            what the words promise and what the engine produces grows quietly until
            someone audits it. We have audited it. The gap is now named.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            A worked example we already shipped
          </h2>

          <p>
            One of the audit&apos;s findings was small enough to fix on its own, and we
            did. The level-3 table contained a particular kind of duplication: for the
            same country pair ending in the same historical event, we were storing every
            possible window length that converged on that ending: a 5-year window, a
            6-year window, a 7-year window, all describing the same lead-up to the same
            event. The original spec said to keep only the longest of these and discard
            the rest. The code did not.
          </p>

          <p>
            Once we measured the cost of the bug, the size of it surprised us. Across the
            full table, the inflation factor was 77.9x: for every row that should have
            been there, roughly seventy-seven were. The factor was not uniform across
            event categories. Civil-war analogues, where each country pair&apos;s patterns
            tend to have varied natural lengths, inflated 16-32x. Pandemic-related
            analogues, which compress every historical pandemic to the COVID-19 window and
            then admit windows of every imaginable length feeding into it, inflated
            200-450x. The within-country normalisation that turns row counts into salience
            scores does not cancel a non-uniform inflation: pandemic categories were
            systematically over-weighted in our salience output relative to civil-war
            categories, by something like an order of magnitude.
          </p>

          <p>
            The fix landed this week as a deduplicated view sitting on top of the level-3
            table. Two-line SQL change in the pipeline; the live ranking will shift the
            next time a full run completes; categories like civil_war_and_insurgency and
            military_coup will rise relative to epidemic_and_pandemic and
            transitional_justice in the per-country tops. We mention it here because it is
            a concrete instance of the methodology evolution we are about to do at larger
            scale. We measured a thing the spec named two years ago, found the cost was
            real and non-trivial, and shipped the fix as soon as the measurement came
            back. V2.0 is the same pattern in larger pieces.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">What V2.0 will compute</h2>

          <p>The V2.0 rebuild adds two pipeline phases and one frontend surface.</p>

          <p>
            The first new phase aggregates the level-3 table into a level-4 Recipe table.
            One row per event category. The columns are the ones the founding observation
            implies: a canonical length (the median window length across all the level-3
            instances of this category, reported alongside its interquartile range so
            readers can see the dispersion), an indicator fingerprint (every indicator
            that appears in any of those instances, ranked by frequency, with a confidence
            interval per indicator so we are not pretending point estimates are precise),
            the count of distinct country pairs feeding the recipe, and a coverage-bias
            diagnostic that names the OECD / non-OECD composition of the corpus so a
            reader of a recipe built mostly from rich-data countries can discount it
            appropriately when applying it to a poor-data subject. Provenance metadata
            (when the recipe was last recomputed, against which pipeline version) sits
            next to those properties.
          </p>

          <p>
            The second new phase consumes the level-4 table and a single country&apos;s
            recent indicator series, and produces a similarity score between zero and one.
            This is the function the methodology page has been promising. A country does
            not need to have all the fingerprint indicators populated (partial coverage is
            a first-class case, not a failure mode), and the function has to tolerate it
            gracefully and report which fingerprint indicators were present and which were
            missing. The output passes through an explicit calibration step against a
            held-out validation set, so a similarity of 0.78 means something stable across
            countries and across pipeline runs rather than being a bare heuristic.
          </p>

          <p>
            The frontend surface is a small one: a per-country watchlist that lists the
            recipes currently scoring above threshold for that country, with the change
            since last cycle and the indicator coverage. The country profile pages will
            link to it. The methodology page will be rewritten to describe the level-4
            recipe as the primary object and the level-3 table as the underlying corpus it
            is built from, with the two no longer conflated.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What changes for the reader
          </h2>

          <p>
            The biggest difference is the addition of a per-country, per-recipe number
            that today does not exist. Today we can tell you that Yemen ranks high on
            civil_war_and_insurgency because the density of historical analogue patterns
            ending in civil-war events around Yemen is unusually concentrated. We cannot
            tell you that Yemen&apos;s indicator trajectory over the last several years
            looks like 73% of the canonical civil-war recipe with four of the seven
            fingerprint indicators present. The first kind of statement is honest about
            what today&apos;s engine actually computes. The second kind is what the
            methodology page implies and what the rebuild lets us say.
          </p>

          <p>
            Existing scoring will not vanish. Salience and ranking and the tier labels are
            calibrated against the V1.9.1 outputs and will keep running in parallel during
            and after the V2.0 build. The country profile pages will continue to render
            their analogue-density tops. The new similarity score is additive: a second,
            more directly methodologically faithful number alongside the existing one,
            with both visible long enough that we and external readers can compare them
            side by side before any decision about retiring the older score.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What is deliberately not in V2.0
          </h2>

          <p>
            The audit surfaced two scope additions we considered and chose to defer. We
            mention both for honesty and because each is a real research direction we
            intend to come back to.
          </p>

          <p>
            The first is sign retention in the underlying pattern indicator corpus. Today
            the correlation engine keeps positive correlations and discards strong
            negative ones. The founding observation that motivated this work is a
            positive-correlation case, the similarity function we are building works on
            positive correlations, and the cost of recomputing the entire 14-billion-row
            indicator table to add a sign column is non-trivial. We are deferring
            negative-correlation modelling to a separate research workstream rather than
            folding it into V2.0. One member of our internal advisory council registered a
            principled dissent on this -- the argument that dropping the sign at indicator
            creation locks us out of an entire half of the modelling space permanently --
            and we have logged that dissent against the future research workstream rather
            than letting it disappear.
          </p>

          <p>
            The second is the integration of forward-projected indicator values into the
            similarity function. The pipeline already flags individual indicator values as
            real or model-projected at the row level; the propagation of that flag through
            the rest of the pipeline is dormant. Turning it on cleanly is its own
            engineering project. The V2.0 similarity function will operate on real
            indicator values for now, and the projection-aware variant is the next major
            piece of work after V2.0 stabilises.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Timeline and what we will say next
          </h2>

          <p>
            V2.0 is a pipeline rebuild, a new frontend surface, a methodology-page
            rewrite, and a calibration deliverable. The internal estimate is roughly three
            calendar weeks of solo engineering on top of the existing live system. We are
            not going to commit to a specific ship date publicly because engineering
            estimates of three weeks have a way of becoming four; we will post here when
            the level-4 Recipe table is online and again when the similarity function
            ships.
          </p>

          <p>
            We expect to write at least one more post during the build window, most likely
            once the level-4 aggregation is running and we can show what the indicator
            fingerprints actually look like for a few of the larger event categories.
            Patterns we did not expect to see will probably surface; that is the kind of
            thing this work is for.
          </p>

          <p>
            The reason to write this post before any of that ships is straightforward. The
            methodology page has been promising the level-4 entity for as long as QGI has
            been online. We owe the people who read it an honest accounting of the gap,
            what we are doing about it, and what the new shape will look like when it
            lands. This is that accounting.
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
            Audit document and the internal advisory consultation that informed the V2.0
            scope live in our internal docs repository. The deduplication fix referenced
            above shipped as ticket #458; the V2.0 charter and its scope decisions are
            tracked under #461 onward.
          </p>
          <p>
            See also:{" "}
            <Link
              href="/blog/curation-in-practice"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Curation in practice
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
