import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About · QG Intelligence",
  description:
    "QG Intelligence is built by Amin Al-Ait, a cloud data engineer bridging data science and geopolitical risk assessment. QGI emerged after six project iterations since 2021.",
  alternates: {
    canonical: "https://qgintelligence.com/about",
  },
  openGraph: {
    title: "About · QG Intelligence",
    description:
      "Meet the founder. QG Intelligence bridges data engineering and geopolitical risk.",
    url: "https://qgintelligence.com/about",
    images: [
      {
        url: "/about/amin.jpg",
        width: 768,
        height: 1024,
        alt: "Amin Al-Ait, founder of QG Intelligence",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "About · QG Intelligence",
    description: "Meet the founder of QG Intelligence.",
  },
};

/* Founder page (Q2 decision, ship with full bio + photo + LinkedIn).
   Bio content provided by Amin in decisions-form 2026-04-18 Q2 comment,
   polished into prose here.

   2026-04-19: moved from app/(app)/about to app/about so the page
   lives in the PUBLIC marketing surface (no sidebar/dashboard chrome).
   Users landing from the header "About" nav link now see a clean
   standalone page rather than being dropped into the app shell.

   2026-04-19 (later): purged all em-dashes from the visible bio
   per user. Copy now uses commas, colons, and period breaks. */

export default function AboutPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      {/* ─── Navbar (mirrors landing) ─────────────────────────────────── */}
      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-baseline gap-1" title="Home">
            <span
              className="font-data text-sm tracking-[0.25em] font-semibold"
              style={{
                color: "var(--qgi-accent)",
                marginRight: "-0.25em",
              }}
            >
              QG
            </span>
            <span
              className="text-[11px] tracking-widest uppercase"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Intelligence
            </span>
          </Link>
          <nav className="flex items-center gap-3 sm:gap-6">
            <Link
              href="/reports"
              className="hidden md:inline-flex text-xs tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Reports
            </Link>
            <Link
              href="/methodology"
              className="text-[10px] sm:text-xs tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Methodology
            </Link>
            <Link
              href="/about"
              className="text-[10px] sm:text-xs tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-accent)" }}
            >
              About
            </Link>
            <Link
              href="/dashboard"
              className="text-[10px] sm:text-xs tracking-wider uppercase px-3 sm:px-4 py-1.5 sm:py-2 rounded transition-colors whitespace-nowrap"
              style={{
                backgroundColor: "var(--qgi-accent)",
                color: "var(--qgi-bg)",
              }}
            >
              Open Dashboard
            </Link>
          </nav>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-10 sm:py-16">
        {/* Hero */}
        <div className="grid gap-8 md:grid-cols-[220px_1fr] md:items-start">
          <div className="flex-shrink-0 mx-auto md:mx-0">
            <div
              className="relative w-[200px] h-[200px] md:w-[220px] md:h-[220px] rounded-full overflow-hidden border-2"
              style={{ borderColor: "var(--qgi-accent)" }}
            >
              <Image
                src="/about/amin-square.jpg"
                alt="Amin Al-Ait, founder of QG Intelligence"
                width={512}
                height={512}
                priority
                className="object-cover w-full h-full"
              />
            </div>
          </div>

          <div>
            <div
              className="text-[10px] font-mono tracking-[0.2em] uppercase mb-2"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Founder
            </div>
            <h1 className="text-4xl sm:text-5xl font-semibold leading-tight tracking-tight">
              Amin Al-Ait
            </h1>
            <p className="mt-3 text-base" style={{ color: "var(--qgi-text-muted)" }}>
              Founder, QG Intelligence · Cloud Data Engineer
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <a
                href="https://www.linkedin.com/in/aminalait/"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded px-4 py-2 text-sm font-medium transition-all hover:brightness-110"
                style={{
                  backgroundColor: "var(--qgi-accent)",
                  color: "var(--qgi-bg)",
                }}
              >
                <LinkedInIcon />
                LinkedIn
              </a>
              <a
                href="mailto:amin@qgintelligence.com"
                className="inline-flex items-center gap-2 rounded px-4 py-2 text-sm font-medium border transition-all hover:brightness-110"
                style={{
                  borderColor: "var(--qgi-border)",
                  color: "var(--qgi-text)",
                }}
              >
                amin@qgintelligence.com
              </a>
            </div>
          </div>
        </div>

        {/* Bio */}
        <section className="mt-12 max-w-3xl">
          <h2
            className="text-[10px] font-mono tracking-[0.2em] uppercase mb-4"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            How QGI came to be
          </h2>
          <div
            className="space-y-4 text-[15px] leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            <p>
              I have always been drawn to two things that rarely meet: the quiet,
              measurable <em>behavior of countries</em>, the indicators, the trajectories,
              the trends hiding under the headlines, and the loud, human shape of{" "}
              <em>geopolitics</em>, the crises, the transitions, the inflection points
              that redraw the map.
            </p>
            <p>
              My professional path has been data science and data engineering. Building
              pipelines, taming messy telemetry, shipping systems that distill noise into
              signal. For years I wondered whether the craft I practiced every day could
              bridge into the domain I quietly read about every night: whether cloud-scale
              data could say something honest about geopolitical risk, without
              overclaiming, without the pundit reflex.
            </p>
            <p>
              QGI is the answer I arrived at, after six project iterations since 2021. The
              idea is simple, even if the execution took years: every country leaves a
              structural trace in its economic indicators. Trajectories repeat. Events
              that happened to one country in 1998 sometimes correlate with another
              country&apos;s current path, quietly, decades later. QGI systematically
              finds those correlations at scale, pairs them with a curated historical
              record, and surfaces <em>precedents</em>, not forecasts, that analysts can
              examine on the evidence.
            </p>
            <p>
              The product is open-methodology by design. The data foundation is World
              Bank, CC BY 4.0. The backtest numbers are documented, flaws and all. The
              platform is still expanding: indicators, curated countries, partnerships.
              I&apos;m building it in the open, one regeneration at a time.
            </p>
            <p>
              The ambition reaches further than the current product. I want QGI to serve
              the buyers who quietly shape risk decisions, the insurance underwriters, the
              policy analysts, the sovereign risk teams, the writers who cover political
              instability for audiences with real budgets. The incumbents who serve them
              today are expensive, closed, and often inflexible. I believe there is room
              for something different: data-driven and human-curated at once, transparent
              rather than authoritative, continually improving against honest benchmarks
              rather than selling polished certainty.
            </p>
            <p>
              The early numbers are modest and I publish them as they are, including the
              misses. What I can point to with confidence is a trajectory. The margin by
              which QGI beats the simplest baseline has grown across three releases, from
              0.07 to 0.14 to 0.19. The next twelve to eighteen months are about turning
              that trajectory into something a sophisticated analyst would stake a
              decision on.
            </p>
            <p>
              If any of that resonates, or if you work somewhere QGI could be useful,
              I&apos;d enjoy hearing from you.
            </p>
          </div>
        </section>

        {/* Footer links */}
        <section
          className="mt-12 pt-8 border-t"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          <div className="flex flex-wrap gap-6 text-sm">
            <Link
              href="/methodology"
              className="hover:underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Read the methodology →
            </Link>
            <Link
              href="/countries"
              className="hover:underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Browse country profiles →
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}

function LinkedInIcon() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.852 3.37-1.852 3.601 0 4.267 2.37 4.267 5.455v6.288zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.063 2.063 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  );
}
