import type { Metadata, Route } from "next";
import Link from "next/link";
import { PublicNav } from "@/components/PublicNav";
import { PublicFooter } from "@/components/PublicFooter";
import { SkipLink } from "@/components/SkipLink";
import { Wordmark } from "@/components/brand/Wordmark";

export const metadata: Metadata = {
  title: "Blog · QG Intelligence",
  description:
    "Development notes on building QGI: scoring releases, backtest results, methodology shifts, and what the numbers actually mean.",
  alternates: { canonical: "https://qgintelligence.com/blog" },
  openGraph: {
    title: "Blog · QG Intelligence",
    description:
      "Development notes on building QGI: scoring releases, backtest results, methodology shifts, and what the numbers actually mean.",
    url: "https://qgintelligence.com/blog",
    siteName: "QG Intelligence",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "Blog · QG Intelligence",
    description: "Development notes on building QGI.",
  },
};

// Hand-curated post index. New posts get appended here + their own route
// under app/blog/<slug>/page.tsx. Intentionally no CMS / MDX pipeline yet
// — shipping something honest beats architecting something grand.
// Ghana piece moved to /reports/ghana-mauritania-mirror (2026-05-19).
// Original /blog/ghana-mauritania-mirror 301-redirects via next.config.ts.
const POSTS: Array<{
  slug: string;
  title: string;
  date: string;
  dek: string;
  tags: string[];
}> = [
  {
    slug: "honest-confidence-numbers",
    title: "Why our confidence numbers just went down — on purpose",
    date: "2026-07-12",
    dek: "34 of our 42 live recipe confidence scores were overstated, a multiple-comparisons artifact from picking the best of nine candidate windows. We re-measured every recipe with one honest protocol, corrected the 34, and left the 8 that held up untouched.",
    tags: ["methodology", "validation", "recipe fleet"],
  },
  {
    slug: "twelve-to-thirty",
    title: "Twelve to thirty, in one scan",
    date: "2026-06-25",
    dek: "We expanded the news board from twelve countries to thirty. Adding a country cost essentially nothing, nine of the thirty still show no live pulse, and the next twenty are a one-line change. What we did, and what it means.",
    tags: ["news layer", "GDELT", "scaling"],
  },
  {
    slug: "foreign-intervention-graduation",
    title:
      "Foreign Intervention, graduated: what eighteen years of indicator trajectories say",
    date: "2026-05-23",
    dek: "QGI's first ML-validated recipe earns its risk score. Four indicators, eighteen years, two hard validation gates cleared. The mechanic is similarity to a historical pre-crisis trajectory, and the line between similarity and probability is where this piece spends most of its time.",
    tags: ["methodology", "ML", "graduation"],
  },
  {
    slug: "recipe-rebuild-level-4",
    title: "What we mean when we say 'Recipe'",
    date: "2026-04-26",
    dek: "The word 'Recipe' on our methodology page has been doing more rhetorical work than the code. Here is the gap, why it opened, and what the V2.0 rebuild changes.",
    tags: ["methodology", "V2.0"],
  },
  {
    slug: "curation-in-practice",
    title: "Curation in practice: Iran, Ukraine, Venezuela",
    date: "2026-04-24",
    dek: "Three countries, three different gaps in our existing event coverage, three parallel curation passes in one afternoon. What we changed, what we didn't, and why this work sits upstream of every score we publish.",
    tags: ["methodology", "curation"],
  },
  {
    slug: "cross-country-normalization",
    title: "Cross-country normalization meets the data",
    date: "2026-04-22",
    dek: "We proposed replacing per-country z-score normalization with a cross-country global approach. An Athena-backed simulation surfaced three problems before we shipped. Here's the finding, and why we're shelving V1.9.2 until event-curation coverage grows.",
    tags: ["methodology", "simulation", "V1.9.2"],
  },
  {
    slug: "margin-over-persistence-trajectory",
    title: "The margin keeps widening",
    date: "2026-04-22",
    dek: "V1.8 → V1.8.1 → V1.9. The gap between QGI and the naïve baseline has grown at every release. Here's why, and what the number does and doesn't prove.",
    tags: ["methodology", "backtest", "V1.9"],
  },
];

export default function BlogIndexPage() {
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
          <Wordmark variant="nav" href="/" title="Home" />
          <PublicNav currentPage="blog" />
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="focus:outline-none">
        <article className="mx-auto max-w-4xl px-6 py-16">
          <div className="mb-12">
            <div
              className="text-[10px] tracking-widest uppercase mb-3"
              style={{ color: "var(--qgi-accent)" }}
            >
              Blog
            </div>
            <h1 className="text-3xl font-semibold mb-4">Development notes</h1>
            <p
              className="text-lg leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Honest writeups of what we shipped, what we measured, and what the numbers
              actually mean. Not a product blog. Not marketing copy. Closer to a lab
              notebook that happens to be public.
            </p>
          </div>

          {/* Pinned: Recipe Tracker — always at the top, above all posts */}
          <div className="mb-10">
            <Link
              href={"/blog/trend-tracker" as Route}
              className="group block rounded-lg overflow-hidden transition-transform hover:-translate-y-0.5"
              style={{
                backgroundColor: "var(--qgi-surface)",
                border: "1px solid var(--qgi-border)",
                borderLeft: "3px solid var(--qgi-accent)",
                boxShadow: "0 0 12px rgba(56, 189, 248, 0.08)",
              }}
            >
              <div className="p-5">
                {/* Eyebrow with LIVE badge */}
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className="text-[10px] tracking-widest uppercase font-semibold"
                    style={{ color: "var(--qgi-accent)" }}
                  >
                    Pinned
                  </span>
                  <span
                    className="text-[10px] tracking-widest uppercase"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    &middot;
                  </span>
                  {/* LIVE badge */}
                  <span className="flex items-center gap-1.5">
                    <span
                      aria-hidden="true"
                      style={{
                        display: "inline-block",
                        width: "7px",
                        height: "7px",
                        borderRadius: "50%",
                        backgroundColor: "var(--qgi-success)",
                        animation: "qgi-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
                      }}
                    />
                    <span
                      className="text-[10px] tracking-widest uppercase font-semibold"
                      style={{ color: "var(--qgi-success)" }}
                    >
                      Live
                    </span>
                  </span>
                </div>
                <h2
                  className="text-xl font-semibold mb-2 group-hover:underline"
                  style={{ color: "var(--qgi-text)" }}
                >
                  Trend Tracker
                </h2>
                <p
                  className="text-sm leading-relaxed"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  Live status board for all 69 QGI trends, across 8 geopolitical families.
                  Forty-two in play on the dashboard, graded on a confidence ladder;
                  twenty-seven coming soon. Every trend walks the same validation gates in
                  held-out historical data, and most will not top the ladder on a given
                  walk.
                </p>
              </div>
            </Link>

            {/* Inline keyframe for the pulsing dot */}
            <style>{`
            @keyframes qgi-pulse {
              0%, 100% { opacity: 1; }
              50% { opacity: 0.3; }
            }
          `}</style>
          </div>

          <ul className="space-y-8">
            {POSTS.map((p) => (
              <li
                key={p.slug}
                className="border-b pb-8"
                style={{ borderColor: "var(--qgi-border)" }}
              >
                <Link href={`/blog/${p.slug}` as Route} className="group block">
                  <div
                    className="text-[10px] tracking-wider uppercase mb-2"
                    style={{ color: "var(--qgi-text-dim)" }}
                  >
                    <time dateTime={p.date}>{p.date}</time>
                    {" · "}
                    {p.tags.join(" · ")}
                  </div>
                  <h2
                    className="text-2xl font-semibold mb-3 transition-colors"
                    style={{ color: "var(--qgi-text)" }}
                  >
                    <span className="group-hover:underline">{p.title}</span>
                  </h2>
                  <p
                    className="text-base leading-relaxed"
                    style={{ color: "var(--qgi-text-muted)" }}
                  >
                    {p.dek}
                  </p>
                </Link>
              </li>
            ))}
          </ul>

          <footer
            className="mt-16 pt-8 border-t text-sm"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-dim)",
            }}
          >
            Want the full technical trail? See{" "}
            <Link
              href="/methodology"
              className="underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              our methodology page
            </Link>
            .
          </footer>
        </article>
      </main>
      <PublicFooter />
    </div>
  );
}
