import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";

/**
 * #733 — First pipeline-derived QGI content piece.
 *
 * Burkina Faso's five-domain firing on the 2026-04-30 V1.9.1 bake mirrors
 * the pre-crisis signature in Mali 2010-2012 and Central African Republic
 * 2011-2013. Both produced humanitarian crises within 12-18 months.
 *
 * Voice: Foreign Affairs register (Ingrid). 800-1200 words target. Sipho
 * Lloyd's-style "what this doesn't mean" callout. No probability framing —
 * "pattern resemblance" and "structural similarity" only.
 *
 * Salience numbers hardcoded against the 2026-04-30 bake (cited
 * explicitly) so external citations stay stable. /signals/burkina_faso
 * link surfaces the current bake's numbers for the reader who wants live
 * data.
 */

const BAKE_DATE = "2026-04-30";
const PUBLISH_DATE = "2026-05-16";

export const metadata: Metadata = {
  title:
    "Burkina Faso's risk signature: a structural pattern shared with Mali 2010-2012 and CAR 2011-2013 | QGI Blog",
  description:
    "Five risk domains fire simultaneously on Burkina Faso in our 2026-04-30 bake. The same five-domain signature preceded the 2012 Mali coup and the 2013 Central African Republic collapse. What that structural resemblance means, and what it doesn't.",
  alternates: {
    canonical: "https://qgintelligence.com/blog/burkina-faso-mali-car-precedent",
  },
  openGraph: {
    title: "Burkina Faso's risk signature mirrors Mali 2010-2012 and CAR 2011-2013",
    description:
      "Five risk domains firing simultaneously on Burkina Faso match the pre-crisis structural pattern of two historical analogues. What that resemblance does and does not mean.",
    url: "https://qgintelligence.com/blog/burkina-faso-mali-car-precedent",
    siteName: "QG Intelligence",
    type: "article",
    publishedTime: `${PUBLISH_DATE}T00:00:00Z`,
    images: [
      {
        url: "/og-default.png",
        width: 1200,
        height: 630,
        alt: "QG Intelligence · Quantitative Geopolitical Intelligence",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Burkina Faso's risk signature mirrors two historical pre-crisis patterns",
    description:
      "Five risk domains firing simultaneously match Mali 2010-2012 and CAR 2011-2013. Structural similarity, not prediction.",
  },
  robots: { index: true, follow: true },
};

const SIGNATURE_ROWS = [
  { name: "Civil War & Insurgency", salience: "2.22σ", tier: "MODERATE" },
  { name: "Military Coup", salience: "1.85σ", tier: "MODERATE" },
  { name: "Mass Protest", salience: "1.24σ", tier: "MODERATE" },
  { name: "Political Repression", salience: "1.22σ", tier: "MODERATE" },
  { name: "Elections & Voting", salience: "1.16σ", tier: "MODERATE" },
] as const;

export default function BurkinaFasoPrecedentPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <ArticleJsonLd
        headline="Burkina Faso's risk signature mirrors Mali 2010-2012 and CAR 2011-2013"
        description="Five risk domains firing simultaneously on Burkina Faso match the pre-crisis structural pattern of two historical analogues."
        url="https://qgintelligence.com/blog/burkina-faso-mali-car-precedent"
        datePublished={`${PUBLISH_DATE}T00:00:00Z`}
        imageUrl="https://qgintelligence.com/og-default.png"
      />

      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-4xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="nav" href={"/" as Route} title="Home" />
          <Link
            href={"/blog" as Route}
            className="text-xs tracking-wider uppercase"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            ← All posts
          </Link>
        </div>
      </header>

      <article className="mx-auto max-w-3xl px-6 py-16">
        {/* Eyebrow + title + dek */}
        <div className="mb-8">
          <div
            className="text-[10px] tracking-widest uppercase mb-3 font-semibold"
            style={{ color: "var(--qgi-accent)" }}
          >
            Field note · Published {PUBLISH_DATE}
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold leading-tight mb-4">
            Burkina Faso&apos;s risk signature mirrors Mali 2010-2012 and CAR 2011-2013
          </h1>
          <p
            className="text-base sm:text-lg leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            Five risk domains light up together in our current bake. The same combination
            preceded the 2012 Mali coup and the 2013 Central African Republic collapse.
            The pattern is structural, the outcomes are historical, and the gap between
            resemblance and prediction is where this piece spends most of its time.
          </p>
        </div>

        <div
          className="prose-qgi text-sm sm:text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          {/* The pattern */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            What QGI sees on Burkina Faso right now
          </h2>
          <p>
            QGI&apos;s 2026-04-30 bake places Burkina Faso in the MODERATE tier overall.
            The aggregate score is unremarkable for the Sahel: moderate scores on
            individual risk dimensions are common in a band where structural fragility is
            the regional baseline. What is unusual, and what this piece is about, is which
            five domains are firing at once.
          </p>

          <div
            className="my-6 rounded-lg border overflow-hidden"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            <table className="w-full text-sm">
              <thead>
                <tr style={{ backgroundColor: "var(--qgi-surface-2)" }}>
                  <th
                    scope="col"
                    className="text-left px-4 py-2 text-[10px] tracking-widest uppercase font-semibold"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    Risk category
                  </th>
                  <th
                    scope="col"
                    className="text-right px-4 py-2 text-[10px] tracking-widest uppercase font-semibold font-data"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    Max-salience
                  </th>
                  <th
                    scope="col"
                    className="text-right px-4 py-2 text-[10px] tracking-widest uppercase font-semibold"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    Tier
                  </th>
                </tr>
              </thead>
              <tbody>
                {SIGNATURE_ROWS.map((r) => (
                  <tr key={r.name} style={{ borderTop: "1px solid var(--qgi-border)" }}>
                    <th
                      scope="row"
                      className="text-left px-4 py-2 font-medium"
                      style={{ color: "var(--qgi-text)" }}
                    >
                      {r.name}
                    </th>
                    <td
                      className="text-right px-4 py-2 font-data tabular-nums"
                      style={{ color: "var(--qgi-text)" }}
                    >
                      {r.salience}
                    </td>
                    <td
                      className="text-right px-4 py-2 font-data tracking-wider text-[11px]"
                      style={{ color: "#fbbf24" }}
                    >
                      {r.tier}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p>
            Civil-war salience above 2σ, military-coup salience above 1.8σ, three further
            categories elevated together: this is a five- domain firing, not a single
            dominant signal. The aggregate tier is MODERATE because none of these scores
            individually crosses the 2.5σ HIGH cutoff. Looking only at the headline
            number, you would not notice. Looking at the five rows together, you see
            something that resembles two specific historical episodes from QGI&apos;s
            corpus.
          </p>

          {/* Mali analogue */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            Mali, 2010-2012
          </h2>
          <p>
            From late 2010 through early 2012, Mali&apos;s indicator trajectory carried
            the same five-row firing: civil conflict, coup, protest, repression, and
            electoral salience all elevated simultaneously. Mali&apos;s headline tier
            through that period was, like Burkina Faso&apos;s today, not HIGH. It was the
            combination that was distinctive.
          </p>
          <p>
            In March 2012, junior officers led by Captain Amadou Sanogo seized power in
            Bamako, four weeks before scheduled presidential elections. The Tuareg-led
            MNLA, taking advantage of the post-coup vacuum, declared the independent state
            of Azawad in the north on 6 April 2012. By January 2013, French Operation
            Serval was underway. Around 1.2 million Malians were displaced over the
            eighteen months that followed. The five- domain signature preceded the coup by
            roughly fifteen months.
          </p>

          {/* CAR analogue */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            Central African Republic, 2011-2013
          </h2>
          <p>
            CAR carried the same five-row firing (civil conflict, coup potential, protest,
            repression, elections) through 2011 and 2012. The aggregate tier was not HIGH.
            The combination was unusual.
          </p>
          <p>
            On 24 March 2013, the Séléka coalition captured Bangui; President François
            Bozizé fled. The humanitarian crisis that followed displaced roughly half the
            country&apos;s population at peak and brought a French and African Union
            intervention. The five-domain signature preceded the takeover by roughly
            eighteen months.
          </p>

          {/* The bridge */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">Two of two</h2>
          <p>
            QGI&apos;s corpus carries the five-domain firing pattern in two country-year
            windows that are historically resolvable: Mali 2010-2012 and CAR 2011-2013.
            Both produced humanitarian crises within twelve-to-eighteen months of the
            equivalent signature appearing. That is a two-of-two outcome.
          </p>
          <p>
            Two cases are not a probability. They are a structural resemblance with a
            historical record. Burkina Faso&apos;s current pattern is recognizable from
            those two cases. The outcomes are not.
          </p>

          {/* Lloyd's callout */}
          <aside
            role="note"
            aria-label="What this doesn't mean"
            className="my-8 rounded-lg p-5"
            style={{
              backgroundColor: "rgba(245, 158, 11, 0.06)",
              border: "1px solid rgba(245, 158, 11, 0.25)",
              borderLeftWidth: 3,
              borderLeftColor: "rgba(245, 158, 11, 0.6)",
            }}
          >
            <div
              className="text-[10px] tracking-widest uppercase font-semibold mb-2"
              style={{ color: "rgba(245, 158, 11, 0.95)" }}
            >
              What this doesn&apos;t mean
            </div>
            <ul className="space-y-2 text-sm leading-relaxed">
              <li>
                <strong>This is not a prediction.</strong> QGI does not forecast that
                Burkina Faso will experience a coup or a humanitarian crisis. It surfaces
                that the current indicator trajectory resembles two cases that did.
              </li>
              <li>
                <strong>Two cases are suggestive, not definitive.</strong> The sample of
                historically resolved five-domain firings in QGI&apos;s 2026-04-30 corpus
                is small. Mali and CAR are visible because they happened. Cases where a
                similar signature appeared and dissipated without crisis are
                under-represented by the same logic; they are harder to anchor to a single
                named event.
              </li>
              <li>
                <strong>Structural similarity is not causal mechanism.</strong> The
                five-domain firing is a pattern observed across indicators that QGI
                tracks. It does not specify which indicator is driving which outcome, and
                it does not name a trigger.
              </li>
              <li>
                <strong>The score is bake-relative.</strong> Numbers in this piece come
                from the 2026-04-30 V1.9.1 bake. Live values may have shifted; see{" "}
                <Link
                  href={"/countries/bfa" as Route}
                  className="underline underline-offset-2"
                  style={{ color: "var(--qgi-accent)" }}
                >
                  /signals/burkina_faso
                </Link>{" "}
                for the current bake.
              </li>
            </ul>
          </aside>

          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            Why we are publishing this
          </h2>
          <p>
            QGI&apos;s purpose is to surface historical precedents that an analyst can use
            as a starting point, not to issue forecasts. Burkina Faso&apos;s current
            five-domain firing is the kind of structural pattern our pipeline is designed
            to find. Mali and CAR are the kind of historical analogues that earn that
            structural pattern its weight.
          </p>
          <p>
            A risk analyst reading this should not change a contingency plan on the
            strength of one blog post. They should look at the five rows above, check our
            methodology, look at the historical cases on their own terms, and decide
            whether the resemblance warrants closer attention. We think it does. The point
            of publishing is to make the case visible, not to settle it.
          </p>

          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            For the reader who wants more
          </h2>
          <ul className="list-disc pl-6 space-y-2 text-sm">
            <li>
              <Link
                href={"/countries/bfa" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Burkina Faso signal page
              </Link>
              : current bake&apos;s salience values per category, refreshed monthly.
            </li>
            <li>
              <Link
                href={"/trends/civil_war_and_insurgency" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Civil-war-and-insurgency precedent
              </Link>
              : the ML-validated recipe behind the 2.22σ score on that row.
            </li>
            <li>
              <Link
                href={"/methodology" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Methodology
              </Link>
              : how the bake is computed, what salience means, where the cohort comes
              from.
            </li>
          </ul>

          <p
            className="text-xs mt-12 pt-6 border-t"
            style={{
              color: "var(--qgi-text-dim)",
              borderColor: "var(--qgi-border)",
            }}
          >
            Published {PUBLISH_DATE} · QG Intelligence · Salience values cited from the{" "}
            {BAKE_DATE} V1.9.1 bake. Pattern matching against QGI&apos;s historical corpus
            is described on the methodology page; this piece reports a single observation
            and its two historical analogues. It is not a forecast.
          </p>
        </div>
      </article>
    </div>
  );
}
