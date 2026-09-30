import type { Metadata } from "next";
import Link from "next/link";
import { PublicNav } from "@/components/PublicNav";
import { Wordmark } from "@/components/brand/Wordmark";
import { PublicFooter } from "@/components/PublicFooter";
import { SkipLink } from "@/components/SkipLink";
import IndicatorTaxonomyTree from "@/components/methodology/IndicatorTaxonomyTree";
import IndicatorsTable from "@/components/methodology/IndicatorsTable";
import StatPie from "@/components/methodology/StatPie";
import { PIE_PALETTE, type PieSlice } from "@/components/methodology/pie-data";
import catalog from "@/data/indicator-catalog.json";
import { PROVIDER_COLOR } from "@/lib/indicator-providers";

interface CatEntry {
  provider: string;
  theme: string;
}
const ENTRIES = (catalog as { indicators: CatEntry[] }).indicators;
const TOTAL = ENTRIES.length;

function countBy(key: "provider" | "theme"): PieSlice[] {
  const m = new Map<string, number>();
  for (const e of ENTRIES) m.set(e[key], (m.get(e[key]) || 0) + 1);
  return [...m.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([label, value], i) => ({
      label,
      value,
      color:
        key === "provider"
          ? PROVIDER_COLOR[label] || PIE_PALETTE[i]
          : PIE_PALETTE[i % PIE_PALETTE.length],
    }));
}

const PROVIDER_SLICES = countBy("provider");
const THEME_SLICES = countBy("theme");

export const metadata: Metadata = {
  title: "All indicators · QGI Methodology",
  description:
    "Every open-data indicator QGI currently tracks, with its provider, theme, and how many trends it feeds. Eight providers: World Bank, V-Dem, UCDP, FAOSTAT, UNHCR, ILOSTAT, OWID and UNDP.",
  alternates: { canonical: "https://qgintelligence.com/methodology/indicators" },
  openGraph: {
    title: "All indicators · QGI Methodology",
    description: "Every open-data indicator QGI currently tracks, by provider and theme.",
    url: "https://qgintelligence.com/methodology/indicators",
    siteName: "QG Intelligence",
    type: "article",
  },
};

export default function MethodologyIndicatorsPage() {
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
        <div className="mx-auto max-w-5xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="nav" href="/" title="Home" />
          <PublicNav currentPage="methodology" />
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="focus:outline-none">
        <article className="mx-auto max-w-5xl px-6 py-16">
          <div className="mb-10">
            <div
              className="text-[10px] tracking-widest uppercase mb-3"
              style={{ color: "var(--qgi-accent)" }}
            >
              Methodology · Indicators
            </div>
            <h1 className="text-3xl font-semibold mb-4">
              The indicators behind every score
            </h1>
            <p
              className="text-lg leading-relaxed max-w-2xl"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              QGI reads {TOTAL} open-data indicators, every one public and citable, drawn
              from eight providers — the World Bank, V-Dem, UCDP and FAOSTAT among them.
              They span the economy, governance, rights, conflict and society, the raw
              signals a trend is built from.
            </p>
            <p className="mt-4 text-sm">
              <Link
                href="/methodology"
                className="border-b pb-0.5 transition-colors hover:text-[var(--qgi-accent)] hover:border-[var(--qgi-accent)]"
                style={{
                  color: "var(--qgi-text-muted)",
                  borderColor: "var(--qgi-border)",
                }}
              >
                &larr; Back to the methodology
              </Link>
            </p>
          </div>

          <section className="mb-10">
            {/* Single column on phones so each donut gets full width (avoids the
                two-donuts-side-by-side legend clip). StatPie's inner row already
                wraps + truncates; min-w-0 stops grid-cell blowout. */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="min-w-0">
                <StatPie title="Indicators by provider" slices={PROVIDER_SLICES} />
              </div>
              <div className="min-w-0">
                <StatPie title="Indicators by theme" slices={THEME_SLICES} />
              </div>
            </div>
          </section>

          <section className="mb-14">
            <h2
              className="text-xs tracking-[0.25em] uppercase mb-4"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              By provider and theme
            </h2>
            <IndicatorTaxonomyTree />
          </section>

          <section>
            <h2
              className="text-xs tracking-[0.25em] uppercase mb-4"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Every indicator
            </h2>
            <IndicatorsTable />
          </section>
        </article>
      </main>

      <PublicFooter />
    </div>
  );
}
