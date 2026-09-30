import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Reports · QG Intelligence",
  description:
    "Pre-computed analytical reports demonstrating QGI's risk analysis capabilities. Sample reports available for download.",
  alternates: {
    canonical: "https://qgintelligence.com/reports",
  },
  openGraph: {
    title: "Reports · QG Intelligence",
    description:
      "Pre-computed analytical reports demonstrating QGI's risk analysis capabilities.",
    url: "https://qgintelligence.com/reports",
    siteName: "QG Intelligence",
    type: "website",
  },
};

/**
 * /reports — public page listing downloadable QGI analytical reports.
 *
 * Phase 1: placeholder with the FSI demo report slot (not yet generated).
 * Phase 2: actual PDF download + email capture gate.
 */
export default function ReportsPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      {/* Navbar (same as methodology/legal) */}
      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-4xl flex items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-baseline gap-1" title="Home">
            <span
              className="font-data text-sm tracking-[0.25em] font-semibold"
              style={{ color: "var(--qgi-accent)", marginRight: "-0.25em" }}
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
          <nav className="flex items-center gap-4">
            <Link
              href="/methodology"
              className="text-xs tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Methodology
            </Link>
            <Link
              href="/dashboard"
              className="text-xs tracking-wider uppercase px-4 py-2 rounded transition-colors"
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

      <article className="mx-auto max-w-4xl px-6 py-16">
        <div className="mb-12">
          <div
            className="text-[10px] tracking-widest uppercase mb-3"
            style={{ color: "var(--qgi-accent)" }}
          >
            Reports
          </div>
          <h1 className="text-3xl font-semibold mb-4">Analytical Reports</h1>
          <p
            className="text-lg leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            Pre-computed pattern analyses demonstrating what QGI delivers to risk analysts
            and institutional clients. Each report is generated from live pipeline data
            and is fully reproducible.
          </p>
        </div>

        {/* Report Cards */}
        <div className="space-y-6">
          {/* R8 podium #1 — Daniel Mensah, Niger-Burkina divergence (2026-05-21) */}
          <Link
            href="/reports/niger-burkina-divergence"
            className="block rounded-lg border p-6 transition-colors hover:border-[var(--qgi-accent)]"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            <div
              className="text-[10px] tracking-widest uppercase mb-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Country Analysis · May 2026
            </div>
            <h2 className="text-lg font-semibold mb-1">
              The Junta That Cannot Stay Isolated: Niger&apos;s Structural Divergence
              Inside the AES Bloc
            </h2>
            <p className="text-sm" style={{ color: "var(--qgi-text-dim)" }}>
              QGI places Niger at #4 of 58 on its Multilateral Agreement recipe at 94/100.
              Its closest structural peer, Burkina Faso (95% cosine similarity at the L1
              composite), sits at #57 with 2/100. The two AES juntas are on opposite
              structural paths.
            </p>
          </Link>

          {/* R8 podium #2 — Rajesh Iyer, India-Pakistan structural mirror (2026-05-21) */}
          <Link
            href="/reports/india-pakistan-mirror"
            className="block rounded-lg border p-6 transition-colors hover:border-[var(--qgi-accent)]"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            <div
              className="text-[10px] tracking-widest uppercase mb-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Country Analysis · May 2026
            </div>
            <h2 className="text-lg font-semibold mb-1">
              India and Pakistan Are 99% the Same Risk, and Neither Risk Framework Wants
              to Hear It
            </h2>
            <p className="text-sm" style={{ color: "var(--qgi-text-dim)" }}>
              QGI places India and Pakistan at 99% cosine similarity, each other&apos;s #1
              structural peer in the 156-country cohort. Civil War &amp; Insurgency recipe
              fires on both with the same fingerprint. The convergence is recent, not
              decades-embedded.
            </p>
          </Link>

          {/* R8 podium #3 — Dmitri Volkov, Ukraine-Bosnia sovereign credit (2026-05-21) */}
          <Link
            href="/reports/ukraine-bosnia-mirror"
            className="block rounded-lg border p-6 transition-colors hover:border-[var(--qgi-accent)]"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            <div
              className="text-[10px] tracking-widest uppercase mb-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Sovereign Credit Note · May 2026
            </div>
            <h2 className="text-lg font-semibold mb-1">
              Ukraine&apos;s Structural Mirror: What Bosnia 1996 Tells the Credit Desk
              About UKRAIN 2027
            </h2>
            <p className="text-sm" style={{ color: "var(--qgi-text-dim)" }}>
              QGI places Ukraine&apos;s closest structural twin at Bosnia and Herzegovina
              (81% cosine, 16-point gap above the next-closest cluster at 65%). A
              falsifiable structural-credit thesis: Multilateral Agreement crossing 70/100
              is the entry trigger, 60/100 floor with no CI narrowing is the exit.
            </p>
          </Link>

          {/* Ghana report — elevated from /blog 2026-05-19 */}
          <Link
            href="/reports/ghana-mauritania-mirror"
            className="block rounded-lg border p-6 transition-colors hover:border-[var(--qgi-accent)]"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            <div
              className="text-[10px] tracking-widest uppercase mb-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Country Analysis · May 2026
            </div>
            <h2 className="text-lg font-semibold mb-1">
              Ghana&apos;s Double Signal: The Ballot Box, the Barracks, and the Country
              Nobody Expected
            </h2>
            <p className="text-sm" style={{ color: "var(--qgi-text-dim)" }}>
              QGI places Ghana at the 99th percentile of global election-stress in its
              April 2026 scoring run. Its closest structural peer is Mauritania at 99%
              cosine similarity, not Mali, not Burkina Faso. What that structural
              resemblance means for the six-month forward call.
            </p>
          </Link>

          {/* 2026-04-24 (#430): FSI demo report re-linked here. Agent 7
              QA audit verified the report renders fully (27K chars, 9 h2
              + 19 h3 sections, proper @media print CSS, correct canonical).
              The #264 "needs rework" concern was editorial polish, not
              functional — shipping the link back so it's reachable from
              its own index rather than undiscoverable by direct URL only.
              Rewrite can ship as /reports/fsi-qgi-report-v2 later without
              breaking this link. */}
          <Link
            href="/reports/fsi-qgi-report"
            className="block rounded-lg border p-6 transition-colors hover:border-[var(--qgi-accent)]"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            <div
              className="text-[10px] tracking-widest uppercase mb-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              Demo Report · April 2026
            </div>
            <h2 className="text-lg font-semibold mb-1">
              FSI × QGI: Fragile-State Pattern Overlay
            </h2>
            <p className="text-sm" style={{ color: "var(--qgi-text-dim)" }}>
              How QGI&apos;s structural-analogue patterns align with Fund for Peace&apos;s
              Fragile States Index, where they diverge, and what the divergence flags for
              analysts.
            </p>
          </Link>

          {/* Burkina Faso — listed but intentionally not yet linked. */}
          <div
            className="block rounded-lg border p-6 cursor-not-allowed opacity-60"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
            aria-disabled="true"
          >
            <div
              className="text-[10px] tracking-widest uppercase mb-2"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Country Analysis · May 2026
            </div>
            <h2 className="text-lg font-semibold mb-1">
              Burkina Faso&apos;s risk signature mirrors Mali 2010-2012 and CAR 2011-2013
            </h2>
            <p className="text-sm" style={{ color: "var(--qgi-text-dim)" }}>
              Five risk domains light up together on Burkina Faso in our current bake. The
              same combination preceded the 2012 Mali coup and the 2013 Central African
              Republic collapse. What that structural resemblance means, and what it
              doesn&apos;t.
            </p>
          </div>

          {/* Upcoming report placeholder */}
          <div
            className="rounded-lg border p-6 opacity-50"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            <h2 className="text-lg font-semibold mb-1">
              Regional Risk Brief: Middle East & North Africa
            </h2>
            <p className="text-sm" style={{ color: "var(--qgi-text-dim)" }}>
              Planned Q3 2026. Regional pattern analysis across 20 MENA countries with
              cross-border contagion scoring.
            </p>
          </div>

          <div
            className="rounded-lg border p-6 opacity-50"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            <h2 className="text-lg font-semibold mb-1">
              Structural Twins Deep Dive: BRICS+
            </h2>
            <p className="text-sm" style={{ color: "var(--qgi-text-dim)" }}>
              Planned Q4 2026. Which non-BRICS economies share structural trajectories
              with the bloc&apos;s members?
            </p>
          </div>
        </div>
      </article>

      {/* Footer */}
      <footer
        className="border-t"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-surface)",
        }}
      >
        <div className="mx-auto max-w-4xl px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <Link href="/" className="flex items-baseline gap-1">
            <span
              className="font-data text-xs tracking-[0.25em] font-semibold"
              style={{ color: "var(--qgi-accent)", marginRight: "-0.25em" }}
            >
              QG
            </span>
            <span
              className="text-[10px] tracking-widest uppercase"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Intelligence
            </span>
          </Link>
          <div className="flex items-center gap-4">
            <Link
              href="/methodology"
              className="text-[10px] tracking-wider transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Methodology
            </Link>
            <Link
              href="/legal"
              className="text-[10px] tracking-wider transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Legal
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function ReportStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-center">
      <div className="font-data text-lg font-bold" style={{ color: "var(--qgi-accent)" }}>
        {value}
      </div>
      <div
        className="text-[10px] tracking-wider uppercase"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        {label}
      </div>
    </div>
  );
}
