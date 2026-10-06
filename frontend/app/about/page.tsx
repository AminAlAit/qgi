import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { PublicNav } from "@/components/PublicNav";
import { PublicFooter } from "@/components/PublicFooter";
import { SkipLink } from "@/components/SkipLink";
import { Wordmark } from "@/components/brand/Wordmark";

export const metadata: Metadata = {
  title: "About · QG Intelligence",
  description:
    "QG Intelligence is built by Amin Al-Ait, a cloud data engineer bridging data science and geopolitical risk assessment.",
  alternates: {
    canonical: "https://qgintelligence.com/about",
  },
  openGraph: {
    title: "About · QG Intelligence",
    description:
      "Meet the founder. QG Intelligence bridges data engineering and quantitative geopolitical analysis.",
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

/* /about, public marketing page. Redesigned 2026-05-23 by Sard mini-Majles
   3-seat synthesis (Rodrigo / Sunita / Tomás). Hero stays as founder block;
   approved mission + vision live in a structurally separate institutional
   band between hero and bio; bio rewritten around the founder's authentic
   origin moment (TU Dortmund + EA FC) and the platform's OSINT framing.

   Old page lives at app/about/_classic-backup/page.tsx for single-rename
   revert. */

export default function AboutPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <SkipLink />
      {/* Top nav */}
      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="nav" href="/" title="Home" />
          <PublicNav currentPage="about" />
        </div>
      </header>

      <main
        id="main-content"
        tabIndex={-1}
        className="max-w-4xl mx-auto px-6 py-10 sm:py-16 focus:outline-none"
      >
        {/* Hero: founder block */}
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
              Founder, QG Intelligence{" "}
              <span style={{ color: "var(--qgi-text-dim)" }}>
                (Quantitative Geopolitical Intelligence)
              </span>{" "}
              · Cloud Data Engineer
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
                href="https://medium.com/@AminAlAit"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded px-4 py-2 text-sm font-medium border transition-all hover:brightness-110"
                style={{
                  borderColor: "var(--qgi-border)",
                  color: "var(--qgi-text)",
                }}
              >
                <MediumIcon />
                Medium
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

        {/* Mission + Vision: institutional band, structurally separated. */}
        <section
          aria-label="Platform mission and vision"
          className="mt-12 py-10 grid gap-10 md:gap-12"
          style={{
            borderTop: "1px solid var(--qgi-border)",
            borderBottom: "1px solid var(--qgi-border)",
          }}
        >
          <div>
            <div
              className="text-[10px] tracking-[0.25em] uppercase mb-3 font-data"
              style={{ color: "var(--qgi-text-dim)" }}
              aria-hidden="true"
            >
              Mission
            </div>
            <p
              className="text-[15px] sm:text-base leading-[1.7]"
              style={{ color: "var(--qgi-text)" }}
            >
              QG Intelligence finds the structural fingerprints countries leave across
              their economic, political, and governance indicators before major events,
              matches them against a curated historical record, and surfaces reproducible
              precedents that analysts can evaluate on the evidence.
            </p>
          </div>
          <div>
            <div
              className="text-[10px] tracking-[0.25em] uppercase mb-3 font-data"
              style={{ color: "var(--qgi-text-dim)" }}
              aria-hidden="true"
            >
              Vision
            </div>
            <p
              className="text-[15px] sm:text-base leading-[1.7]"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              A world where geopolitical risk is read from the data, patterns, and
              precedents themselves, where every assessment is clear and grounded, and
              where the evidence does the talking rather than the pundit or the black box.
            </p>
          </div>
        </section>

        {/* Bio: How QGI came to be */}
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
              The question that started QG Intelligence came from a football video game.
              As a Data Science student at TU Dortmund, I was playing EA FC (formerly
              FIFA) and found myself more interested in the underlying player ratings than
              the game itself. EA had built a system that could represent the performance
              and behavior of individual footballers as a structured, comparable score
              from a dense set of observable indicators. I kept returning to a single
              question: could you do the same for countries? Not their GDP, not their
              headline political classification, but their behavioral fingerprint across
              dozens of economic, political, and governance dimensions, tracked over time.
            </p>
            <p>
              That question sat in the background through my engineering work. The version
              I kept coming back to was more specific: if you could encode a
              country&apos;s indicator trajectory in the years before a major event, could
              you find other countries that had followed the same path? Not as a
              simulation, and not as a causal claim. Simply as a structural match, the way
              a diagnostician looks for a clinical picture in the historical record.
            </p>
            <p>
              The earliest patterns I found were cross-regional: two countries from
              different governance traditions and different economic structures that
              nonetheless showed striking convergence across governance and economic
              indicators in the years before significant geopolitical events. That
              convergence was not a prediction. It was a pattern that surfaced from the
              data, that a trained analyst could interrogate, contest, or rule out. That
              is what I wanted QGI to surface.
            </p>
            <p>
              Early versions were rough. The platform has gone through six major rebuilds
              since 2021. The honest number I track is the lift in the top-50 country
              rankings over a random baseline: it has moved from 0.07 to 0.14 to 0.19
              across successive methodology iterations. That is not a dramatic figure. It
              represents incremental, evidence-accountable improvement in the core task.
            </p>
            <p>
              The data infrastructure behind QGI draws on Open Source Intelligence
              sourcing across the full set of countries the platform covers. The
              integration spans political, economic, governance, and institutional
              indicators from multiple public providers. No single source dominates. The
              methodology is designed to be auditable: every precedent match comes with
              the indicators that drove it, the historical record it was matched against,
              and the scoring logic that produced the result.
            </p>
            <p>
              The intended audience is not the general public. I built QGI for analysts
              who already work in geopolitical risk: insurance underwriters pricing
              sovereign exposure, policy analysts building scenario frameworks, sovereign
              risk teams at financial institutions, writers who cover political
              instability for audiences with real budgets. These are professionals who are
              skeptical of black-box outputs and need to understand the evidence chain
              behind any conclusion. QGI is designed to show its work.
            </p>
            <p>
              I am a Cloud Data Engineer by background. I built QGI because the question
              from that TU Dortmund afternoon never stopped being interesting. The
              infrastructure, the methodology, and the platform are the result of working
              on that question seriously for five years without the pressure of a
              commercial deadline. Whether QGI becomes a product or a research
              contribution, the analytical core will remain the same: structural
              fingerprints, historical precedents, and reproducible evidence.
            </p>
            <p>
              The platform is still expanding. It is also imperfect, and thorny in places.
              If any of that resonates, or if you work somewhere QGI could be useful, I
              would enjoy hearing from you.
            </p>
          </div>
        </section>

        {/* Footer onward-links */}
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
              href="/reports"
              className="hover:underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Browse reports →
            </Link>
            <Link
              href="/blog"
              className="hover:underline"
              style={{ color: "var(--qgi-accent)" }}
            >
              Latest development updates →
            </Link>
          </div>
        </section>
      </main>
      <PublicFooter />
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

function MediumIcon() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      {/* Modern Medium "M" mark (2017+), angular letterform with V-notch.
          Replaces the older three-ellipses logo (2015-17) which is no
          longer Medium's brand mark. */}
      <path d="M2.846 6.887c.03-.295-.083-.586-.303-.784l-2.24-2.7v-.403h6.958l5.378 11.795 4.728-11.795H24v.403l-1.916 1.837c-.165.126-.247.333-.213.538v13.498c-.034.204.048.411.213.537l1.871 1.837v.403h-9.412v-.403l1.939-1.882c.19-.19.19-.246.19-.537V7.794L11.227 20.769h-.713L4.39 7.794v8.697c-.052.385.076.774.347 1.052l2.521 3.058v.404H0v-.404l2.521-3.058c.27-.279.39-.67.325-1.052V6.887z" />
    </svg>
  );
}
