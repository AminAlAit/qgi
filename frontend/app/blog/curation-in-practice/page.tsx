import type { Metadata } from "next";
import Link from "next/link";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";

export const metadata: Metadata = {
  title: "Curation in practice: Iran, Ukraine, Venezuela · QGI Blog",
  description:
    "Three countries, three different gaps in our existing event coverage, three parallel curation passes in one afternoon. What we changed, what we didn't, and why this work is upstream of every score we publish.",
  alternates: {
    canonical: "https://qgintelligence.com/blog/curation-in-practice",
  },
  openGraph: {
    title: "Curation in practice: Iran, Ukraine, Venezuela",
    description:
      "Three countries, three different failure modes, one afternoon of curation. What quality curation actually looks like.",
    url: "https://qgintelligence.com/blog/curation-in-practice",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: "2026-04-24T00:00:00Z",
  },
  twitter: {
    card: "summary",
    title: "Curation in practice: Iran, Ukraine, Venezuela",
    description:
      "Three countries, three different gaps. One afternoon. What quality curation actually looks like.",
  },
};

export default function CurationInPracticePost() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <ArticleJsonLd
        headline="Curation in practice: Iran, Ukraine, Venezuela"
        description="Three countries, three different gaps in our existing event coverage, three parallel curation passes in one afternoon."
        url="https://qgintelligence.com/blog/curation-in-practice"
        datePublished="2026-04-24T00:00:00Z"
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
            <time dateTime="2026-04-24">2026-04-24</time> · Methodology · Curation
          </div>
          <h1 className="text-4xl font-semibold mb-5 leading-tight">
            Curation in practice: Iran, Ukraine, Venezuela
          </h1>
          <p
            className="text-lg leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            Three countries, three different gaps in our existing coverage, three parallel
            curation passes in one afternoon. Here&apos;s what we changed, what we
            didn&apos;t, and why this work sits upstream of every score we publish.
          </p>
        </div>

        <div
          className="prose max-w-none text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          <p>
            Most of the writing on this blog is about scoring methodology: what algorithm
            turns data into a country tier, why one version replaces another. That&apos;s
            the visible half of the work. The invisible half is the data itself. Every
            score QGI publishes is computed from a corpus of hand-verified historical
            events that someone had to collect, classify, and check. If that corpus is
            wrong, the scoring math is irrelevant.
          </p>

          <p>
            This post is about what that data work looked like on one particular afternoon
            for three particular countries.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">Why these three</h2>

          <p>
            Each of the three had a different kind of problem, and that&apos;s why we did
            them together. Seeing three failure modes side-by-side is more useful than
            three passes on variants of the same issue.
          </p>

          <p>
            <strong>Iran</strong> had volume but missed the last decade. The existing 146
            events were heavy on the Revolution, the Iran–Iraq war, and the Ahmadinejad
            years, and thin on the post-JCPOA period: the 2017–18 protests, the 2019
            fuel-price protests, the 2022 Mahsa Amini unrest, the 2024 presidential
            transition, the post-October-2023 regional escalation. A scoring engine that
            doesn&apos;t know 2017 happened can&apos;t tell you anything useful about
            2026.
          </p>

          <p>
            <strong>Ukraine</strong> was thin on everything. Forty-three events total,
            mostly post-2014. A country where the 20th century alone produced more
            regime-defining ruptures than most states manage in two hundred years, the
            1991 independence, the 2004 Orange Revolution, the 2014 Maidan, Crimea,
            Donbas, the 2022 full-scale invasion, and we had forty-three entries.
            That&apos;s not coverage. That&apos;s a stub.
          </p>

          <p>
            <strong>Venezuela</strong> had the most interesting failure: volume was fine
            (51 events) but the categories were wrong. Chávez-and-Maduro-era Venezuela had
            exactly one event coded as <code>political_repression</code> in our entire
            curated history. Zero
            <code> humanitarian_crisis </code>
            entries for a country where six million people emigrated. The events existed
            in the file: RCTV&apos;s forced closure, the 2014 SEBIN detentions, the 2017
            protest deaths, the 2019 blackouts, the Tun Tun operation, but most were coded
            as <code>social_unrest</code> or <code>economic_crisis</code>, which
            understates what was happening. The engine was getting the right country with
            the wrong labels.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">The process</h2>

          <p>
            We ran three curation passes in parallel, one per country, each using the same
            canonical template. The template is the same one we rolled out across all
            curation work two weeks ago: it inlines the 71-category taxonomy directly in
            the prompt, which dropped the confabulation rate from roughly 20% (agents
            inventing plausible-sounding categories that aren&apos;t in the schema) to
            effectively zero when we re-audited. Every candidate event had to come with a
            verifiable web source, a real date, and a category from the fixed set. We then
            manually spot-checked each file before syncing to S3 and re-ingesting into the
            events table.
          </p>

          <p>
            Total wall time: about an afternoon. Total cost: the API calls, a few dollars.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">The results</h2>

          <p>
            <strong>Iran: 146 → 181</strong> (+35 net after dedup). The additions are
            dominated by the 2010s protests wave, the 2015 JCPOA and its 2018 unwinding,
            the 2022 protests, and the 2023–24 regional escalation. Top categories now:{" "}
            <code>civil_war_and_insurgency</code> (21), <code>bilateral_treaty</code>{" "}
            (20), <code>political_repression</code> (16),{" "}
            <code>foreign_intervention</code> (12). The shape now matches Iran as it
            actually is: a state whose history is dominated by internal security, foreign
            alignment shifts, and contested domestic legitimacy.
          </p>

          <p>
            <strong>Ukraine: 43 → 85</strong> (+42 net, done in two passes). First pass
            targeted 100 events. It produced 67, and on review we rejected several as not
            meeting the verification bar: events that happened but couldn&apos;t be pinned
            to a single clear source, or that were already covered by a broader entry.
            Second pass brought it to 85 at the quality bar we wanted rather than 100 at a
            softer one. Coverage now spans 1991 independence through the 2024 battlefield
            situation, with proper weight on the 2004 Orange Revolution, the 2013–14
            Maidan sequence, the 2015 Minsk II period, and the 2022–24 full-scale war. Top
            categories: <code>civil_war_and_insurgency</code> (12),{" "}
            <code>foreign_intervention</code> (7), <code>interstate_war</code> (6).
          </p>

          <p>
            <strong>Venezuela: 51 → 71</strong> (+20 net, with a category rebalance). This
            was the most interesting of the three because the headline number understates
            the change. The three high-signal categories that were previously almost empty
            (<code>political_repression</code>, <code>banking_and_financial_crisis</code>,{" "}
            <code>humanitarian_crisis</code>) went from a combined 2 events to 14. The
            events are real things that happened to real people: the migration crisis, the
            bolívar collapse, the ANC period, the 2017 and 2024 detention waves. They were
            missing not because they were obscure but because the original curation had
            used softer labels.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            Where we didn&apos;t hit the target
          </h2>

          <p>
            Ukraine&apos;s 85 versus the 100-event target is worth naming. We set the
            target before we knew what the verifiable-source pool looked like. By the time
            we got to event 85, further additions would have meant either duplicates of
            existing entries at finer granularity (three different Donbas offensives
            instead of one) or events we couldn&apos;t cleanly source. Neither of those
            helps the scoring engine. A broader spread of verified rare events beats a
            denser cluster of borderline ones.
          </p>

          <p>
            The same logic applied to Iran&apos;s +35 rather than a bigger number: the
            goal isn&apos;t to maximize event count, it&apos;s to produce a history the
            engine can learn from. Events that repeat the same underlying signal at
            different resolutions add noise, not information.
          </p>

          <h2 className="text-2xl font-semibold mt-10 mb-4">
            What this doesn&apos;t solve
          </h2>

          <p>
            Three countries curated in an afternoon is not a scalable plan for the 198
            countries we want to cover. Three things still missing from this story:
          </p>

          <ul className="list-disc pl-6 space-y-2">
            <li>
              <strong>Automation.</strong> We don&apos;t have a pipeline that pulls
              candidate events from GDELT or ACLED, auto-classifies them against the
              taxonomy, and queues the uncertain ones for human review. That&apos;s the
              next-wave curation system. Until it exists, every new country requires a
              parallel agent pass and human review.
            </li>
            <li>
              <strong>Back-coding.</strong> Venezuela&apos;s problem, under-labeled
              categories in an existing file, probably exists in other files we
              haven&apos;t re-audited. Category-stratified retrospective coding is on the
              roadmap; we haven&apos;t started.
            </li>
            <li>
              <strong>Scale.</strong> The methodology fix we shelved last week
              (cross-country normalization) needs closer to 190 curated countries to
              validate properly. We&apos;re at 173 in the curated working set and 138
              actually ingested into Athena. The gap between those two numbers is its own
              piece of work.
            </li>
          </ul>

          <h2 className="text-2xl font-semibold mt-10 mb-4">Why this matters</h2>

          <p>
            The scoring pages on this site talk in terms of z-scores and recipe fusion and
            tier thresholds. All of that math runs on events like the 185 we added today.
            If the events are wrong (missing, miscategorized, unsourced, made up), no
            clever scoring choice can repair it. The math computes faithfully from the
            input. It doesn&apos;t know the input is bad.
          </p>

          <p>
            Most forecasting products keep their event corpora opaque. Ours isn&apos;t
            opaque, and one of the reasons it isn&apos;t is that it can&apos;t hide from
            anybody who wants to look. The files are in the repository. When Iran goes
            from 146 to 181 events, that&apos;s a line-item change in a JSON file anyone
            can diff. When Venezuela&apos;s
            <code> political_repression </code> count goes from 1 to 5, the five events
            are individually verifiable and come with URLs.
          </p>

          <p>
            That transparency is uncomfortable to maintain. It means you can&apos;t paper
            over a thin country by writing a confident-sounding methodology page. It also
            means when the scoring produces a HIGH tier for Venezuela, there&apos;s a
            documented history underneath the number. Something to argue with, rather than
            something to take on faith.
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
            Curated event files live in our public data repository. The prompt template
            used for these passes is internal; the taxonomy it inlines is documented on
            our methodology page.
          </p>
          <p>
            See also:{" "}
            <Link
              href="/blog/cross-country-normalization"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Cross-country normalization meets the data
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
