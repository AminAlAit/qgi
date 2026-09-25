/**
 * Home ("/") — the public landing. Promoted from /landing-v2 on 2026-05-31
 * (founder direction). Confidence-first: real fleet data in the live preview,
 * no method internals in the headline copy. The old marketing landing it
 * replaced is retired; /landing-v2 now redirects here (next.config).
 */
import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { PublicNav } from "@/components/PublicNav";
import { PublicFooter } from "@/components/PublicFooter";
import { SkipLink } from "@/components/SkipLink";
import { RotatingWordmark } from "@/components/landing-v2/RotatingWordmark";
import { Wordmark } from "@/components/brand/Wordmark";
import { ClosestMatches } from "@/components/dashboard-v4-1/ClosestMatches";
import { buildClosestMatches } from "@/lib/te-mock/dashboard-v4-1-data";
import NewsletterForm from "@/components/NewsletterForm";
import { FeaturedReportCard } from "@/components/highlights/FeaturedReportCard";
import { GemCard } from "@/components/highlights/GemCard";
import { AnalogSpotlight } from "@/components/highlights/AnalogSpotlight";

export const metadata: Metadata = {
  title: "QG Intelligence · Geopolitics, measured",
  description:
    "Every country's multi-decade indicator trajectory read against the historical record, and the past cases it most resembles. Open data, documented methods, evidence not opinion.",
  alternates: { canonical: "/" },
};

const STEPS = [
  {
    num: "01",
    title: "We learn the shapes",
    desc: "From decades of the historical record, we learn the signal shapes that tend to run ahead of each kind of event, a currency crisis, a coup, a wave of unrest. We call each shape a trend.",
  },
  {
    num: "02",
    title: "We watch every country",
    desc: "Across 180+ countries and territories, we track how each one's recent signals are moving and compare them, quarter by quarter, against every trend.",
  },
  {
    num: "03",
    title: "We show you the evidence",
    desc: "See how closely a country is tracing a trend right now, signal by signal, and the real historical cases it most resembles. A measure of resemblance, not a forecast.",
  },
];

export default async function HomePage() {
  const matches = buildClosestMatches(6);

  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <SkipLink />

      {/* Header */}
      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "color-mix(in srgb, var(--qgi-bg) 85%, transparent)",
        }}
      >
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="nav" href={"/" as Route} title="Home" />
          <PublicNav />
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="focus:outline-none">
        {/* Hero */}
        <section className="mx-auto max-w-6xl px-6 pt-24 pb-16">
          <div className="max-w-3xl">
            <RotatingWordmark />
            <p
              className="mt-8 text-lg leading-relaxed max-w-xl"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Across 180+ countries and territories, every country is scored against the
              shapes that came before the events that matter, and shown alongside the real
              historical cases it most resembles. Evidence you can open, not a black box.
            </p>
            <div className="mt-9 flex items-center gap-4 flex-wrap">
              <Link
                href={"/dashboard" as Route}
                className="px-6 py-3 rounded text-sm font-medium tracking-wide transition-all hover:brightness-110"
                style={{ backgroundColor: "var(--qgi-accent)", color: "var(--qgi-bg)" }}
              >
                Open Dashboard
              </Link>
              <a
                href="#how-it-works"
                className="px-6 py-3 rounded text-sm tracking-wide border transition-colors hover:bg-[var(--qgi-surface-2)]"
                style={{
                  borderColor: "var(--qgi-border)",
                  color: "var(--qgi-text-muted)",
                }}
              >
                How it works
              </a>
            </div>
          </div>
        </section>

        {/* Live preview — real fleet data */}
        <section className="mx-auto max-w-6xl px-6 pb-20">
          <div className="flex items-center gap-2 mb-5">
            <span className="relative flex h-2 w-2" aria-hidden="true">
              <span
                className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
                style={{ backgroundColor: "#3FBF8F" }}
              />
              <span
                className="relative inline-flex h-2 w-2 rounded-full"
                style={{ backgroundColor: "#3FBF8F" }}
              />
            </span>
            <span
              className="text-[10px] tracking-widest uppercase"
              style={{
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              Live
            </span>
          </div>
          <ClosestMatches matches={matches} />
          <div className="mt-8">
            <Link
              href={"/dashboard" as Route}
              className="text-sm tracking-wide border-b pb-0.5 transition-colors hover:text-[var(--qgi-accent)] hover:border-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-muted)", borderColor: "var(--qgi-border)" }}
            >
              Open the full dashboard &rarr;
            </Link>
          </div>
        </section>

        {/* Highlights — Featured Report + Structural Gems */}
        <section
          id="highlights"
          className="border-t"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          <div className="mx-auto max-w-6xl px-6 py-20 flex flex-col gap-16">
            {/* Block A — Featured Report */}
            <FeaturedReportCard />

            {/* Divider */}
            <div style={{ borderTop: "1px solid var(--qgi-border)" }} />

            {/* Block B — Structural Gems strip */}
            <div>
              <p
                className="text-[10px] tracking-widest uppercase mb-2"
                style={{
                  color: "var(--qgi-text-dim)",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                Structural Resemblances
              </p>
              <h2
                className="text-xl font-semibold mb-8"
                style={{ color: "var(--qgi-text)" }}
              >
                Where countries rhyme
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <GemCard
                  eyebrow="Civil War & Insurgency"
                  headline="India & Pakistan: 99% structural resemblance."
                  body="Each other's #1 structural peer on Civil War & Insurgency in the 156-country cohort. The convergence is recent, not decades-embedded."
                  href="/reports/india-pakistan-mirror"
                  accentColor="#E64545"
                />
                <GemCard
                  eyebrow="Multilateral Agreement"
                  headline="Niger scores 94, Burkina 2. Same structural fingerprint. Opposite trajectories."
                  body="Two AES juntas with near-identical profiles are moving in opposite directions on multilateral engagement. 95% structural match, 92 points apart."
                  href="/reports/niger-burkina-divergence"
                  accentColor="#5B7E99"
                />
                <GemCard
                  eyebrow="Sovereign Credit Note"
                  headline="Ukraine's structural twin is Bosnia 1996."
                  body="The largest gap in the 156-country analogue corpus — 16 points above the next cluster. A falsifiable credit thesis anchored in the historical record."
                  href="/reports/ukraine-bosnia-mirror"
                  accentColor="#7B5EE6"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Analog Spotlight — full-bleed surface band */}
        <section
          style={{
            backgroundColor: "var(--qgi-surface)",
            borderTop: "1px solid var(--qgi-border)",
            borderBottom: "1px solid var(--qgi-border)",
          }}
        >
          <div className="mx-auto max-w-6xl px-6 py-20">
            <AnalogSpotlight />
          </div>
        </section>

        {/* How it works */}
        <section
          id="how-it-works"
          className="border-t"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          <div className="mx-auto max-w-6xl px-6 py-24">
            <h2
              className="text-xs tracking-widest uppercase mb-12"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              How it works
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {STEPS.map((step) => (
                <div key={step.num}>
                  <div
                    className="text-3xl font-bold mb-4"
                    style={{
                      color: "var(--qgi-accent)",
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    {step.num}
                  </div>
                  <h3 className="text-lg font-medium mb-3">{step.title}</h3>
                  <p
                    className="text-sm leading-relaxed"
                    style={{ color: "var(--qgi-text-muted)" }}
                  >
                    {step.desc}
                  </p>
                </div>
              ))}
            </div>
            <p className="mt-10 text-sm" style={{ color: "var(--qgi-text-dim)" }}>
              Want the full picture?{" "}
              <Link
                href={"/methodology" as Route}
                className="border-b pb-0.5 transition-colors hover:text-[var(--qgi-accent)] hover:border-[var(--qgi-accent)]"
                style={{
                  color: "var(--qgi-text-muted)",
                  borderColor: "var(--qgi-border)",
                }}
              >
                Read the methodology
              </Link>
              .
            </p>
          </div>
        </section>

        {/* Why QGI */}
        <section
          className="border-t"
          style={{
            borderColor: "var(--qgi-border)",
            backgroundColor: "var(--qgi-surface)",
          }}
        >
          <div className="mx-auto max-w-6xl px-6 py-24">
            <h2
              className="text-xs tracking-widest uppercase mb-12"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Why QGI
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <WhyCard
                label="Evidence, not a black box"
                body="Every score opens to the signals behind it and the real historical cases it resembles. You see the working, not a verdict."
              />
              <WhyCard
                label="History, not opinion"
                body="Scores come from the historical record, not from analyst hunches or curated country lists. The same method runs on every country."
              />
              <WhyCard
                label="180+ countries & territories"
                body="Global coverage, refreshed every quarter. Every country is read against the full catalogue of event trends, every release."
              />
              <WhyCard
                label="Resemblance, not a forecast"
                body="We tell you what today rhymes with, honestly. Tracing a trend is a structural analogue an analyst can weigh, not a prediction."
              />
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="mx-auto max-w-6xl px-6 py-24 text-center">
          <h2 className="text-2xl font-semibold mb-4">
            See what the world is rhyming with
          </h2>
          <p className="mb-8 max-w-md mx-auto" style={{ color: "var(--qgi-text-muted)" }}>
            Open Dashboard for today&rsquo;s closest matches, or browse every country and
            trend.
          </p>
          <div className="flex items-center justify-center gap-4 flex-wrap">
            <Link
              href={"/dashboard" as Route}
              className="inline-block px-8 py-3 rounded text-sm font-medium tracking-wide transition-all hover:brightness-110"
              style={{ backgroundColor: "var(--qgi-accent)", color: "var(--qgi-bg)" }}
            >
              Open Dashboard
            </Link>
            <Link
              href={"/countries" as Route}
              className="inline-block px-8 py-3 rounded text-sm tracking-wide border transition-colors hover:bg-[var(--qgi-surface-2)]"
              style={{ borderColor: "var(--qgi-border)", color: "var(--qgi-text-muted)" }}
            >
              Browse countries
            </Link>
          </div>
        </section>

        {/* Newsletter */}
        <section
          className="border-t"
          style={{
            borderColor: "var(--qgi-border)",
            backgroundColor: "var(--qgi-surface)",
          }}
        >
          <div className="mx-auto max-w-6xl px-6 py-20">
            <div className="max-w-2xl">
              <h2
                className="text-xs tracking-widest uppercase mb-4"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                Stay updated
              </h2>
              <p
                className="text-lg font-medium mb-2"
                style={{ color: "var(--qgi-text)" }}
              >
                Newsletter
                <span
                  className="ml-2 align-middle text-[10px] tracking-widest uppercase px-2 py-0.5 rounded"
                  style={{
                    color: "var(--qgi-accent)",
                    border: "1px solid var(--qgi-border)",
                  }}
                >
                  Coming soon
                </span>
              </p>
              <p
                className="text-sm leading-relaxed mb-6"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                We are putting together a monthly digest of new country readings and
                notable resemblances. Leave your email and you will be the first to get
                it, plus early word as new features go live. No marketing, no noise.
              </p>
              <NewsletterForm />
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}

function WhyCard({ label, body }: { label: string; body: string }) {
  return (
    <div
      className="rounded-lg border p-6"
      style={{ backgroundColor: "var(--qgi-bg)", borderColor: "var(--qgi-border)" }}
    >
      <h3 className="text-base font-semibold mb-2" style={{ color: "var(--qgi-text)" }}>
        {label}
      </h3>
      <p className="text-sm leading-relaxed" style={{ color: "var(--qgi-text-muted)" }}>
        {body}
      </p>
    </div>
  );
}
