import type { Metadata } from "next";
import Link from "next/link";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";

export const metadata: Metadata = {
  title: "Twelve to thirty, in one scan · QGI Blog",
  description:
    "We expanded the news board from twelve countries to thirty. Adding a country turned out to cost essentially nothing, around nine of the thirty still show no live pulse on any given day, and the next twenty are a one-line change. Here's what we did and what it means.",
  alternates: {
    canonical: "https://qgintelligence.com/blog/twelve-to-thirty",
  },
  openGraph: {
    title: "Twelve to thirty, in one scan",
    description:
      "Scaling the news board from twelve countries to thirty. Why the marginal cost of a country is zero, why around nine still show no live pulse on a given day, and the registry that makes the next twenty trivial.",
    url: "https://qgintelligence.com/blog/twelve-to-thirty",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: "2026-06-25T00:00:00Z",
  },
  twitter: {
    card: "summary",
    title: "Twelve to thirty, in one scan",
    description:
      "Scaling the news board to thirty countries. The marginal cost of a country is zero. Around nine still show no live pulse on a given day, and that's the point.",
  },
};

export default function TwelveToThirtyPost() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <ArticleJsonLd
        headline="Twelve to thirty, in one scan"
        description="We expanded the news board from twelve countries to thirty. Adding a country cost essentially nothing, nine of the thirty still show no live pulse, and the next twenty are a one-line change."
        url="https://qgintelligence.com/blog/twelve-to-thirty"
        datePublished="2026-06-25T00:00:00Z"
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
            <time dateTime="2026-06-25">2026-06-25</time> · News layer · GDELT
          </div>
          <h1 className="text-4xl font-semibold mb-5 leading-tight">
            Twelve to thirty, in one scan
          </h1>
          <p
            className="text-lg leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            We expanded the news board from twelve countries to thirty. The interesting
            parts weren&apos;t the eighteen new flags. They were that adding a country
            cost essentially nothing, that nine of the thirty still show no live pulse on
            a given day, and that the next twenty will be a one-line change. Here is what
            we did and what it means.
          </p>
        </div>

        <div
          className="prose max-w-none text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          <p>
            The{" "}
            <Link
              href="/risk-board"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              news board
            </Link>{" "}
            is the high-frequency half of QGI. Each cell pairs two readings for a
            country-and-theme: a <strong>structural</strong> score, how closely that
            country&apos;s indicator trajectory resembles the historical run-up to a given
            kind of event, and a <strong>news pulse</strong>, how loud that theme is in
            the current news stream, measured as a z-score against the country&apos;s own
            baseline. When both are high the cell reads ACTIVE; when only the news is
            loud, SIGNAL; only the structure, LATENT; neither, QUIET. Until this week it
            covered twelve countries. Now it covers thirty.
          </p>

          <p>
            The eighteen we added are an instability-first set: Ukraine, Russia, Syria,
            Iraq, Yemen, Israel, Afghanistan, Libya, Ethiopia, DR Congo, Somalia, Mali,
            Haiti, the Central African Republic, Mozambique, Zimbabwe, Turkey, and
            Indonesia. The board tracks where conditions are moving, not where we have an
            opinion; Russia and Israel are on it because they are primary conflict
            theaters, for the same reason Yemen and Sudan already were.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            The marginal cost of a country is zero
          </h2>

          <p>
            Here is the part that changed how we think about coverage. The news pulse is
            built on the GDELT Global Knowledge Graph, eleven years of it, every news
            document since 2015 tagged with the countries and themes it touches. To bring
            a new country onto the board we scan that history once and tally its themes
            month by month.
          </p>

          <p>
            A query against that history is billed by the bytes it reads, and it reads the
            same columns whether you filter to one country or forty. The country filter is
            applied <em>after</em> the read; it is free. So the scan that backfilled all
            eighteen new countries cost exactly what a scan for a single country would
            have: one pass, about 2.8 terabytes, somewhere between eleven and seventeen
            dollars depending on BigQuery&apos;s free-tier usage that month. The marginal
            cost of the nineteenth country, or the fiftieth, is essentially nothing.
          </p>

          <p>
            That inverts the usual default. When each new country has a fixed price, you
            ration. When the price is a flat one-time scan no matter how many you add, the
            limit stops being the budget and becomes the question of which countries are
            worth a row on the board. We chose a wide net deliberately.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Why nine countries still show no live pulse
          </h2>

          <p>
            On top of the monthly board runs an hourly poller that nowcasts the same
            signal off the raw GDELT feed. It has a rule we consider non-negotiable: if a
            country produces too little news in the trailing twenty-four hours, fewer than
            two hundred English-language documents, its live cells go blank. Not zero.
            Blank, a dash. <strong>Absence of news is not calm; it is unknown</strong>,
            and we will not paint unknown as quiet.
          </p>

          <p>
            On a normal day that gate blanks the live pulse for about nine of the thirty:
            Yemen, Libya, Somalia, Mali, the Central African Republic, Mozambique, and,
            already, three of the original twelve, Myanmar, Sudan, and Tunisia. These are
            real wars and real crises that the English-language news stream simply
            undercovers. The Central African Republic generated thirteen documents in the
            day we checked. Yemen, about a hundred. Their <em>monthly</em> board pulse is
            fine, there is enough signal over thirty days, but their live intraday cell
            honestly reports that right now, we don&apos;t have enough to say. Nothing
            about the expansion changed that behavior; it just added more countries that
            live near the floor.
          </p>

          <p>
            A short detour worth admitting, because it is the kind of thing that bites
            you. Our first pass at checking whether a country had enough volume used a
            quick regular expression that pulled every two-letter token out of
            GDELT&apos;s location field. It happily counted region codes and feature codes
            as if they were countries, and inflated the numbers by something like
            thirty-fold. Yemen looked like it had thousands of documents a day. The honest
            per-country count is a hundred. The lesson is the boring one: the cheap
            measurement and the real measurement disagreed, and the real one is the one
            that ships.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            No special-casing on the structural side
          </h2>

          <p>
            The structural score is the other half of every cell, and the new countries
            get it for free, but not because we hand-tuned anything. QGI&apos;s recipe
            fleet already scores 216 countries; a country&apos;s resemblance to the run-up
            of a civil war or a currency crisis is computed the same way for Ukraine as
            for Lebanon. So the new rows arrive on the board with both readings live from
            day one, structure and pulse, scored by the same machinery as the original
            twelve. There is no probationary tier where a new country shows news but no
            structure.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">One file, the next twenty</h2>

          <p>
            The unglamorous reason this expansion took a day instead of a week is that we
            stopped to remove the duplication first. The country list used to be
            copy-pasted across eight scripts, the backfill, the rollups, the score join,
            the baseline, the live poller. Adding a country meant editing all eight and
            hoping you matched the spelling each time. Now there is one registry file.
            Every stage reads it; the backfill even auto-detects which countries are new
            and scans only those. Going from thirty to fifty is adding rows to that file
            and following a runbook. The marginal cost being zero only matters if the
            marginal effort is small too.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What this does and doesn&apos;t mean
          </h2>

          <p>
            A fuller board is not a more confident board. Every cell still says what it
            always said: how closely a country&apos;s structure rhymes with a historical
            pattern, and how loud the matching theme is in the news right now. It is
            resemblance and pressure, not a probability of an event. Thirty countries
            means we are watching thirty places that way, not that we have a forecast for
            thirty places. The blank cells are part of that honesty, not an exception to
            it.
          </p>

          <p>
            And the choice of <em>which</em> thirty is a product judgment, not a
            measurement. We picked an instability watchlist, the places where the
            structure or the news is most likely to be doing something, and skipped the
            quiet high-income world that the board would only ever render QUIET. That is a
            curation call. It is the kind of call we would rather make in the open than
            launder through an algorithm.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">Why this matters</h2>

          <p>
            The boring version of this post is &ldquo;we added eighteen countries.&rdquo;
            The real version is that scaling a measurement forces you to decide what you
            do when the measurement is thin, and the answer that protects the reader is
            the one that costs you coverage: show the dash, not the zero. A product
            optimizing for looking comprehensive fills every cell. We left nine of them
            blank on purpose, and wrote down why.
          </p>

          <p>
            The thirty-country board is{" "}
            <Link
              href="/risk-board"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              live now
            </Link>
            . The next twenty are a registry edit away.
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
            The news board pairs a structural resemblance score with a live news pulse for
            every country and theme. How both are built is described on the methodology
            page.
          </p>
          <p>
            See also:{" "}
            <Link
              href="/risk-board"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              The news board
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
