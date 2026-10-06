import type { Metadata } from "next";
import { PublicNav } from "@/components/PublicNav";
import { Wordmark } from "@/components/brand/Wordmark";
import { PublicFooter } from "@/components/PublicFooter";
import { SkipLink } from "@/components/SkipLink";
import {
  SECTION_LABEL,
  getDisplayableReports,
  getLatestForRail,
  getLiveStats,
} from "./_data/reports-manifest";
import { PublicationMasthead } from "./_components/PublicationMasthead";
import { LatestRail } from "./_components/LatestRail";
import { ClusterProvenanceRail } from "./_components/ClusterProvenanceRail";
import { TierFilteredGrid } from "./_components/TierFilteredGrid";

export const metadata: Metadata = {
  title: `${SECTION_LABEL} · QG Intelligence`,
  description:
    "Pattern-driven analysis of sovereign risk, geopolitical alignment, and structural divergence. Reproducible by design.",
  alternates: {
    canonical: "https://qgintelligence.com/reports",
  },
  openGraph: {
    title: `${SECTION_LABEL} · QG Intelligence`,
    description:
      "Pattern-driven analysis of sovereign risk, geopolitical alignment, and structural divergence.",
    url: "https://qgintelligence.com/reports",
    siteName: "QG Intelligence",
    type: "website",
  },
};

export default async function ReportsPage() {
  const { reportCount, countryCount } = getLiveStats();
  const latest = getLatestForRail();
  const latestSlugs = new Set(latest.map((r) => r.slug));
  const browsable = getDisplayableReports().filter((r) => !latestSlugs.has(r.slug));

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
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="nav" href="/" title="Home" />
          <PublicNav currentPage="reports" />
        </div>
      </header>

      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto max-w-6xl px-6 py-12 lg:py-16 focus:outline-none"
      >
        <PublicationMasthead reportCount={reportCount} countryCount={countryCount} />

        <ClusterProvenanceRail clusters={[]} />

        <LatestRail reports={latest} />

        <TierFilteredGrid reports={browsable} />
      </main>

      <PublicFooter />
    </div>
  );
}
