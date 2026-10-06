import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import type { Route } from "next";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";
import { Wordmark } from "@/components/brand/Wordmark";

/**
 * Foreign Intervention recipe graduation — first ML-validated QGI recipe.
 *
 * Voice: Foreign Affairs / methodology-log register, matching the
 * Burkina Faso piece. No probability framing. Discrimination layer
 * shipped directly per M8-R5 paired-framing rider — Walk-3 ECE
 * calibration failure must accompany every external comm about this
 * recipe's risk score.
 *
 * Numbers hardcoded against the validated 2021 bake artifacts
 * (qgi-data#56). Audit chart PNGs are in /public/risk-metric/.
 */

const PUBLISH_DATE = "2026-05-23";
const BAKE_YEAR = "2021";

export const metadata: Metadata = {
  title:
    "Foreign Intervention, graduated: what eighteen years of indicator trajectories say. QGI Blog",
  description:
    "QGI's first ML-validated recipe earns its risk score. Four indicators, eighteen years, and the validation that gates publication. Discrimination layer, not calibrated probability, and the difference matters.",
  alternates: {
    canonical: "https://qgintelligence.com/blog/foreign-intervention-graduation",
  },
  openGraph: {
    title: "Foreign Intervention, graduated: what eighteen years say",
    description:
      "QGI's first ML-validated recipe earns its risk score. Discrimination layer shipped directly; calibrated probability deliberately not claimed.",
    url: "https://qgintelligence.com/blog/foreign-intervention-graduation",
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
    title: "Foreign Intervention, graduated",
    description:
      "QGI's first ML-validated recipe. Discrimination layer, not calibrated probability.",
  },
  robots: { index: true, follow: true },
};

const INDICATORS = [
  {
    code: "RQ.EST",
    label: "Regulatory Quality",
    source: "World Bank Governance",
    weightPct: "51%",
  },
  {
    code: "v2pepwrgen",
    label: "Power distribution by gender",
    source: "V-Dem",
    weightPct: "27%",
  },
  {
    code: "v2stfisccap",
    label: "State fiscal capacity",
    source: "V-Dem",
    weightPct: "17%",
  },
  {
    code: "v2elintmon",
    label: "International election monitoring",
    source: "V-Dem",
    weightPct: "5%",
  },
] as const;

const TOP_3 = [
  {
    country: "Iran",
    score: "98.1",
    band: "96.6–98.4",
    file: "Iran-vs-foreign_intervention.png",
  },
  {
    country: "Turkmenistan",
    score: "97.0",
    band: "95.6–97.2",
    file: "Turkmenistan-vs-foreign_intervention.png",
  },
  {
    country: "Equatorial Guinea",
    score: "96.9",
    band: "95.4–97.1",
    file: "Equatorial_Guinea-vs-foreign_intervention.png",
  },
] as const;

const VALIDATIONS = [
  {
    name: "V1",
    label: "Positive-instance recall",
    gate: "HARD GATE",
    detail:
      "Median similarity at one year before event vs non-event baseline. Foreign intervention: 96.0 vs 70.1, a 25.8 percentile-point separation. Gate: 20pp.",
    verdict: "PASS",
  },
  {
    name: "V2",
    label: "Discrimination-consistency correlation",
    gate: "Reporting only",
    detail:
      "Correlation between similarity score and XGBoost discriminator probability. Pearson 0.26, Spearman 0.50. Moderate; not problematic.",
    verdict: "n/a",
  },
  {
    name: "V3",
    label: "Per-cohort risk landscape",
    gate: "Reporting only",
    detail:
      "Median similarity by cohort. Stable-democracy 5.9, mid-tier 66.7, fragile-state 94.8. Cleanly discriminating across three tiers.",
    verdict: "n/a",
  },
  {
    name: "V4",
    label: "Out-of-time holdout",
    gate: "HARD GATE",
    detail:
      "Held-out historical events must hit HIGH zone (≥65) at event-Y-1. Foreign intervention: 13 of 15 holdout events (86.7%). Gate: 60%.",
    verdict: "PASS",
  },
] as const;

export default function ForeignInterventionGraduationPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <ArticleJsonLd
        headline="Foreign Intervention, graduated: what eighteen years of indicator trajectories say"
        description="QGI's first ML-validated recipe earns its risk score. Discrimination layer shipped directly; calibrated probability deliberately not claimed."
        url="https://qgintelligence.com/blog/foreign-intervention-graduation"
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
        {/* CORRECTION (2026-05-25) — graduation suspended pending re-validation */}
        <div
          role="alert"
          className="mb-10 rounded-lg p-5"
          style={{
            backgroundColor: "rgba(230,69,69,0.08)",
            border: "1px solid rgba(230,69,69,0.4)",
            borderLeft: "4px solid #E64545",
          }}
        >
          <div
            className="text-xs tracking-widest uppercase font-semibold mb-2"
            style={{ color: "#E64545" }}
          >
            Correction · 2026-05-25 · Graduation suspended
          </div>
          <p
            className="text-sm leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            A subsequent audit of our evaluation pipeline found that the LOCO-AUC of
            0.9147 reported below was computed on only 10 of this recipe&apos;s 174
            positive events, roughly 94% were silently dropped because several of the
            selected indicators lack older-year data coverage. On the full historical
            evidence base the discrimination collapses to ≈0.50, i.e. not yet
            distinguishable from chance. The graduation is therefore{" "}
            <strong>suspended pending a corrected re-walk</strong>. The analysis below is
            retained for transparency but is <strong>superseded</strong> and should not be
            cited. We are correcting the pipeline (minimum data-coverage and
            minimum-evidence gates) and will re-validate honestly before any graduation
            claim is restored. We publish this correction openly because the integrity of
            the method is the product.
          </p>
        </div>
        {/* Eyebrow + title + dek */}
        <div className="mb-8">
          <div
            className="text-[10px] tracking-widest uppercase mb-3 font-semibold"
            style={{ color: "var(--qgi-accent)" }}
          >
            Methodology · Published {PUBLISH_DATE}
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold leading-tight mb-4">
            Foreign Intervention, graduated: what eighteen years of indicator trajectories
            say
          </h1>
          <p
            className="text-base sm:text-lg leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            QGI&apos;s first ML-validated recipe earns its risk score today. Four
            indicators, eighteen years, two hard validation gates cleared. The mechanic is
            similarity to a historical pre-crisis trajectory, and the line between
            similarity and probability is where this piece spends most of its time.
          </p>
        </div>

        <div
          className="prose-qgi text-sm sm:text-base leading-relaxed space-y-5"
          style={{ color: "var(--qgi-text)" }}
        >
          {/* A recipe is now graduated */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            A recipe is now graduated
          </h2>
          <p>
            For most of QGI&apos;s history, the word <em>recipe</em> on our methodology
            page has been doing more work than the code. We&apos;ve scored countries
            against patterns we believed were valid; we hadn&apos;t formally validated, in
            held-out historical data, the five components that a recipe must specify. As
            of today, one has been validated. The recipe is{" "}
            <strong>foreign_intervention</strong>. Both hard validation gates cleared.
            Risk scores derived from it are now published for the {BAKE_YEAR} bake.
          </p>
          <p>
            This piece is the long version of that announcement. It explains what
            graduated, what the underlying mechanic does, and (more importantly) what it
            cannot do. The validation that earned the graduation tells one specific thing:
            our scoring mechanic can discriminate pre-crisis trajectories from
            non-pre-crisis trajectories. It does not tell us, and we do not claim, a
            calibrated probability of the event itself.
          </p>

          {/* What QGI means by "recipe" */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            What QGI means by &ldquo;recipe&rdquo;
          </h2>
          <p>
            The Methodology Charter defines a recipe as five components. Every recipe must
            specify all five before it can carry a published score:
          </p>
          <ol className="list-decimal pl-6 space-y-2">
            <li>
              <strong>Key indicators</strong>: the small handful of substrate indicators
              (out of 104 we track) that carry the strongest discriminative signal for
              this crisis class.
            </li>
            <li>
              <strong>Canonical length</strong>: how many years (3–25y) the predictive
              signal accumulates over. Some crises develop over three years; some over
              twenty-five. The recipe says which.
            </li>
            <li>
              <strong>Canonical movement shape</strong>: the average trajectory of those
              indicators across the canonical length, computed from all historical
              positive instances in our corpus.
            </li>
            <li>
              <strong>Aggregation rule</strong>: how the per-indicator measurements
              combine into a single country-recipe number.
            </li>
            <li>
              <strong>Terminating event</strong>: the crisis type that defines the recipe.
              For foreign_intervention, a curated foreign-intervention event in our
              corpus.
            </li>
          </ol>
          <p>
            Validation is the part that didn&apos;t exist before. An XGBoost classifier
            trained on our historical corpus produces the indicator selection and the
            canonical length. Cosine similarity on the z-scored trajectories produces the
            aggregation. Held-out historical events test whether the resulting score
            actually recovers the cases it was supposed to.
          </p>

          {/* What graduated, in numbers */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            What graduated, in numbers
          </h2>
          <p>For foreign_intervention, the validated five components look like this:</p>

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
                    Indicator
                  </th>
                  <th
                    scope="col"
                    className="text-left px-4 py-2 text-[10px] tracking-widest uppercase font-semibold"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    Source
                  </th>
                  <th
                    scope="col"
                    className="text-right px-4 py-2 text-[10px] tracking-widest uppercase font-semibold font-data"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    SHAP weight
                  </th>
                </tr>
              </thead>
              <tbody>
                {INDICATORS.map((ind) => (
                  <tr key={ind.code} style={{ borderTop: "1px solid var(--qgi-border)" }}>
                    <th
                      scope="row"
                      className="text-left px-4 py-2 font-medium"
                      style={{ color: "var(--qgi-text)" }}
                    >
                      {ind.label}{" "}
                      <span
                        className="font-data text-[11px]"
                        style={{ color: "var(--qgi-text-dim)" }}
                      >
                        ({ind.code})
                      </span>
                    </th>
                    <td
                      className="text-left px-4 py-2"
                      style={{ color: "var(--qgi-text-dim)" }}
                    >
                      {ind.source}
                    </td>
                    <td
                      className="text-right px-4 py-2 font-data tabular-nums"
                      style={{ color: "var(--qgi-text)" }}
                    >
                      {ind.weightPct}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p>
            <strong>Canonical length: eighteen years.</strong> The classifier&apos;s
            discriminative AUC peaked at this window. A country&apos;s score is computed
            from its trajectory across the four indicators over the eighteen years
            preceding the evaluation date.
          </p>
          <p>
            <strong>Canonical movement shape:</strong> the mean z-scored trajectory of
            each indicator, averaged across all historical foreign-intervention positives
            in the training set.
          </p>
          <p>
            <strong>Aggregation rule:</strong> cosine similarity is computed between each
            country&apos;s trajectory and the canonical trajectory, per indicator. The
            four per-indicator similarities are combined as a weighted average, with the
            SHAP-derived weights shown above. The result, in [-1, +1], is rescaled to [0,
            100] for publication.
          </p>
          <p>
            <strong>Terminating event:</strong> a curated foreign-intervention entry in
            our corpus, vetted by hand, timestamped to the year the intervention began.
          </p>

          {/* What the risk score actually says */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            What the risk score actually says
          </h2>
          <p>
            For every country, on every recipe that has graduated, QGI publishes a score
            in [0, 100]. The score reads:
          </p>
          <blockquote
            className="border-l-4 pl-4 py-1 my-4 italic"
            style={{
              borderColor: "rgba(167, 139, 250, 0.5)",
              color: "var(--qgi-text-muted)",
            }}
          >
            Over the past eighteen years, how closely does this country&apos;s trajectory
            across the four key indicators align with the average pre-crisis trajectory of
            historical foreign interventions?
          </blockquote>
          <p>
            65 or higher is HIGH. Below 40 is LOW. Between is MODERATE. 50 is the point
            where the country&apos;s trajectory is geometrically orthogonal to the
            canonical shape: neither matching nor opposite.
          </p>
          <p>
            In the {BAKE_YEAR} bake, sixty-eight countries had complete coverage across
            the four indicators over the eighteen-year window. The three highest scores:
          </p>

          {/* Top 3 country charts */}
          <div className="space-y-8 my-8">
            {TOP_3.map((entry) => (
              <figure key={entry.country}>
                <figcaption className="mb-2">
                  <div className="flex items-baseline justify-between mb-1">
                    <h3 className="text-base font-semibold">
                      {entry.country}{" "}
                      <span
                        className="font-data tabular-nums text-sm font-normal ml-2"
                        style={{ color: "#f87171" }}
                      >
                        {entry.score} · HIGH
                      </span>
                      <span
                        className="font-data tabular-nums text-xs font-normal ml-2"
                        style={{ color: "var(--qgi-text-dim)" }}
                      >
                        (80% band {entry.band})
                      </span>
                    </h3>
                  </div>
                  <p className="text-xs" style={{ color: "var(--qgi-text-dim)" }}>
                    Indicator trajectory overlay: {entry.country} vs the
                    foreign_intervention canonical pre-crisis profile.
                  </p>
                </figcaption>
                {/* Scroll container: on phones the chart PNG is wider than the
                    viewport; overflow-x-auto lets the user pan to see all panels.
                    On tablet/desktop the Image fills the figure width naturally. */}
                <div
                  className="overflow-x-auto rounded border"
                  style={{ borderColor: "var(--qgi-border)" }}
                >
                  <Image
                    src={`/risk-metric/foreign_intervention/${entry.file}`}
                    alt={`Indicator trajectory overlay for ${entry.country} versus the foreign_intervention canonical crisis profile`}
                    width={900}
                    height={400}
                    className="min-w-[640px] w-full block"
                    style={{
                      backgroundColor: "var(--qgi-surface)",
                    }}
                    unoptimized
                  />
                </div>
              </figure>
            ))}
          </div>

          <p>
            Each chart overlays one country&apos;s trajectory across the four key
            indicators (faint coloured lines) against the canonical pre-crisis trajectory
            (heavier line). The closer the overlay, the higher the cosine similarity. In
            Iran&apos;s case, three of the four indicators trace the canonical shape
            closely across the full eighteen-year window. In Equatorial Guinea&apos;s
            case, the alignment is most pronounced on regulatory quality and fiscal
            capacity. The aggregate is similar; the substrate is country-specific.
          </p>

          <p>
            The band after each score (e.g. Iran &ldquo;98.1, 80% band
            96.6&ndash;98.4&rdquo;) is a margin of error, not decoration. We compute it by
            bootstrap-resampling the historical events that define the canonical shape and
            watching how much each country&apos;s score moves. It is honest about a real
            limit: the canonical shape for this recipe rests on far fewer events than the
            headline count suggests, with its most heavily-weighted indicator, regulatory
            quality, is anchored on 46 historical instances. The band makes that
            uncertainty visible rather than hiding it behind a single confident number.
            Iran stays firmly in the HIGH zone even at the low end of its band.
          </p>

          {/* The validation that earned the graduation */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            The validation that earned the graduation
          </h2>
          <p>
            Graduation is not automatic. Before a recipe&apos;s scores are published, four
            validations run. Two are hard gates: if either fails, the recipe does not
            graduate. The other two produce evidence but do not block.
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
                    Validation
                  </th>
                  <th
                    scope="col"
                    className="text-left px-4 py-2 text-[10px] tracking-widest uppercase font-semibold"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    Type
                  </th>
                  <th
                    scope="col"
                    className="text-right px-4 py-2 text-[10px] tracking-widest uppercase font-semibold"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    Result
                  </th>
                </tr>
              </thead>
              <tbody>
                {VALIDATIONS.map((v) => (
                  <tr key={v.name} style={{ borderTop: "1px solid var(--qgi-border)" }}>
                    <th
                      scope="row"
                      className="text-left px-4 py-2 align-top"
                      style={{ color: "var(--qgi-text)" }}
                    >
                      <span className="font-semibold">{v.name}</span>{" "}
                      <span style={{ color: "var(--qgi-text-dim)" }}>: {v.label}</span>
                      <p
                        className="text-xs mt-1 font-normal"
                        style={{ color: "var(--qgi-text-dim)" }}
                      >
                        {v.detail}
                      </p>
                    </th>
                    <td
                      className="text-left px-4 py-2 align-top text-[11px] tracking-wider"
                      style={{
                        color: v.gate === "HARD GATE" ? "#f87171" : "var(--qgi-text-dim)",
                      }}
                    >
                      {v.gate}
                    </td>
                    <td
                      className="text-right px-4 py-2 align-top font-data text-[11px] tracking-wider"
                      style={{
                        color: v.verdict === "PASS" ? "#34d399" : "var(--qgi-text-dim)",
                      }}
                    >
                      {v.verdict}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p>Both hard gates cleared. The recipe graduates.</p>

          {/* What this score is NOT */}
          <aside
            role="note"
            aria-label="What this score does not mean"
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
              What this score does not mean
            </div>
            <ul className="space-y-2 text-sm leading-relaxed">
              <li>
                <strong>This is a similarity score, not a calibrated probability.</strong>{" "}
                We do not claim &ldquo;country X has Y% probability of foreign
                intervention in N years.&rdquo; The validation that cleared discrimination
                (telling pre-crisis from non-pre-crisis trajectories) is a different claim
                from calibrated probability. Earlier this same week, the same recipe
                attempted a calibrated probability output via Beta calibration on the same
                XGBoost backbone; the expected calibration error (ECE) failed the hard
                threshold across multiple cohort × recipe cells. Rather than ship a
                probability the methodology does not stand behind, we ship the
                discrimination layer directly. Discriminative AUC: 0.9147. Calibrated
                probability: deferred.
              </li>
              <li>
                <strong>A HIGH score is not a forecast.</strong> It is interpretable as:
                &ldquo;this country&apos;s trajectory looks like the historical
                pre-intervention pattern.&rdquo; Pattern resemblance is not causal
                mechanism. The four indicators did not name a trigger; they identify a
                shape.
              </li>
              <li>
                <strong>A LOW score is not &ldquo;safe.&rdquo;</strong> A country may face
                foreign intervention for reasons not captured by the four indicators:
                idiosyncratic shocks, new actors, regional contagion. Low similarity is
                &ldquo;the methodology has not flagged this pattern,&rdquo; not &ldquo;the
                methodology has cleared this country.&rdquo;
              </li>
              <li>
                <strong>The score is bake-relative.</strong> The {BAKE_YEAR} evaluation
                reflects what was in our {BAKE_YEAR} indicator corpus. Prospective use
                beyond {BAKE_YEAR} requires further out-of-time validation as data lands.
              </li>
            </ul>
          </aside>

          {/* Why we are publishing this */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            Why we are publishing this
          </h2>
          <p>
            The methodology pause that preceded this graduation was deliberate. For most
            of QGI&apos;s life, the scoring pipeline produced numbers without an
            ML-validated recipe substrate. The numbers were useful upstream of the
            validation gates the Methodology Charter demanded (and we said so), but they
            did not constitute a graduated recipe.
          </p>
          <p>
            Foreign intervention is the first to clear those gates. Two parallel walks
            (civil_war, econ_recession) on the same framework returned different verdicts:
            both demonstrated that the indicator-selection mechanic worked, but neither
            cleared the additional thresholds the per-recipe pre-registration demanded.
            Foreign intervention cleared discrimination. The mechanism that earned this
            graduation (XGBoost-derived indicator selection, SHAP-weighted cosine
            similarity on z-scored trajectory profiles, held-out out-of-time validation)
            is now provenance for any subsequent recipe to use.
          </p>
          <p>
            We expect more graduations in the coming weeks. We do not expect every recipe
            to clear. The validation framework is designed to fail recipes when the
            historical signal isn&apos;t there. That is the point. Recipes that fail are
            not published; recipes that pass are.
          </p>

          {/* For the reader who wants more */}
          <h2 className="text-xl sm:text-2xl font-semibold mt-10 mb-3">
            For the reader who wants more
          </h2>
          <ul className="list-disc pl-6 space-y-2 text-sm">
            <li>
              <Link
                href={"/methodology" as Route}
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
              >
                Methodology page
              </Link>{" "}
              : full derivation of the similarity-as-risk-metric framework, what the score
              is and is not, and the validation flow before any recipe&apos;s scores
              publish.
            </li>
            <li>
              <a
                href="https://github.com/AminAlAit/docs/specs/blob/main/methodology/similarity-as-risk-metric.md"
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
                target="_blank"
                rel="noopener noreferrer"
              >
                Similarity-as-risk-metric long-form (docs-specs)
              </a>{" "}
              : the methodology document the page above is built from.
            </li>
            <li>
              <a
                href="https://github.com/AminAlAit/docs/specs/blob/main/internal/decisions/f-ml-1-foreign-intervention-DECISION.md"
                className="underline underline-offset-2"
                style={{ color: "var(--qgi-accent)" }}
                target="_blank"
                rel="noopener noreferrer"
              >
                Foreign intervention recipe DECISION
              </a>{" "}
              : the formal eight-of-eight ratified decision document with the validation
              dossier and the rider package.
            </li>
          </ul>

          <p
            className="text-xs mt-12 pt-6 border-t"
            style={{
              color: "var(--qgi-text-dim)",
              borderColor: "var(--qgi-border)",
            }}
          >
            Published {PUBLISH_DATE} · QG Intelligence · Indicator weights, validation
            statistics, and country scores cited from the validated {BAKE_YEAR} bake of
            the foreign_intervention recipe. The discrimination layer is shipped directly;
            calibrated probability is deliberately not claimed. This piece reports the
            first formal ML recipe graduation and the validation that earned it. It is not
            a forecast.
          </p>
        </div>
      </article>
    </div>
  );
}
