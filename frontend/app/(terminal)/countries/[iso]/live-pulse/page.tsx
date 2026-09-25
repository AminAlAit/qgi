/**
 * /countries/[iso]/live-pulse — the per-country PRO TERMINAL.
 *
 * Full-screen takeover (founder 2026-06-13): a QGI × TradingView terminal that
 * matches the `qgi-console/pulse.html` (:8761) prototype — left rail to switch
 * country/topic, a center pulse stage, and a permanent LIVE NEWS column on the
 * right. Lives in the (terminal) route group so it escapes the app sidebar and
 * owns the whole viewport.
 *
 * Coverage is the NEWS layer (every country in the Topics board), NOT the
 * separate structural country-page set. Two news countries (Bangladesh,
 * Thailand) have full news + resemblance data but no curated country page;
 * they must still get a terminal, so this route never gates on that set —
 * the country name + flag come from the news data itself.
 */
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { Route } from "next";
import { getCountryByIso } from "@/lib/te-mock/countries-v4-data";
import { getHfCountryDetail, hfCoveredIso3 } from "@/lib/hf/pulse-detail";
import { getHfBoard } from "@/lib/hf/topics-data";
import { getLivePulseSeries } from "@/lib/hf/live-pulse-series";
import { getBucketSeries, getBucketArticles } from "@/lib/hf/live-pulse-buckets";
import { LivePulseTerminal } from "@/components/countries-v4-1/LivePulseTerminal";

// The terminal shell (metadata, topics, monthly history) is statically
// generated; ISR re-renders at most every 5 min so the intraday live series
// stays fresh without a blocking S3 read on every request.
export const revalidate = 300;

interface Params {
  params: Promise<{ iso: string }>;
}

// Founder 2026-07-06: standalone Live Pulse terminal disabled — route 404s everywhere. Code kept intact; flip to true (and nothing else) to restore.
const LIVE_PULSE_ROUTE_ENABLED = false;

export const dynamicParams = false;

export async function generateStaticParams() {
  if (!LIVE_PULSE_ROUTE_ENABLED) return [];
  // Every country the news layer covers — the structural country-page set is
  // a separate, broader roster and must not gate news coverage.
  return hfCoveredIso3().map((iso) => ({ iso }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  if (!LIVE_PULSE_ROUTE_ENABLED) return { title: "Not found" };
  const { iso } = await params;
  const detail = getHfCountryDetail(iso);
  const title = detail
    ? `${detail.name} · Live Pulse · QG Intelligence`
    : "Country not found · QG Intelligence";
  const description = detail
    ? `${detail.name} on the Live Pulse pro terminal: eleven years of monthly news pulse across fourteen themes, the live GDELT feed, set against structural readings and the verified event record.`
    : "Country not found.";
  return {
    title,
    description,
    ...(detail
      ? {
          openGraph: { title, description, type: "website" as const },
          alternates: {
            canonical: `/countries/${iso.toLowerCase()}/live-pulse`,
          },
        }
      : {}),
  };
}

export default async function LivePulsePage({ params }: Params) {
  if (!LIVE_PULSE_ROUTE_ENABLED) notFound();
  const { iso } = await params;
  const detail = getHfCountryDetail(iso);
  if (!detail) notFound();

  // Committed shell: topic metadata + the validated monthly (1M) history.
  // Null for countries outside coverage; the terminal falls back to monthly.
  const seriesData = await getLivePulseSeries(detail.iso3);

  // Overlay the LIVE intraday series (1H/4H/1D) read from the poller's bucket
  // cache at request time, z-scored exactly as the board's pulse, onto that
  // shell (1W/1M kept). ALWAYS replace the committed sample articles with the
  // live feed (empty until the poller emits it) — even on the monthly-fallback
  // path — so the news rail shows an honest "coming soon", never stale sample
  // headlines under "LIVE NEWS".
  //
  // Articles are fetched unconditionally so the news rail is always populated
  // from the live poller output regardless of whether a committed live-pulse
  // series JSON exists for this country (e.g. a newly added board country that
  // has articles but no prototype series file yet).
  const [liveSeries, liveArticles] = await Promise.all([
    seriesData ? getBucketSeries(detail.iso3) : null,
    getBucketArticles(detail.iso3),
  ]);

  let liveData = seriesData;
  if (seriesData) {
    const series: typeof seriesData.series = { ...seriesData.series };
    if (liveSeries) {
      for (const [topic, byRes] of Object.entries(liveSeries)) {
        series[topic] = { ...(series[topic] ?? {}), ...byRes };
      }
    }
    liveData = {
      ...seriesData,
      series,
      articles: liveArticles,
      source: liveSeries
        ? "live GDELT (hourly) · validated monthly history"
        : seriesData.source,
    };
  }

  // Rail country list — every news-covered country. Flag is resolved from the
  // name inside the terminal (FlagImg), so this stays independent of the
  // country-page set.
  const board = getHfBoard();
  const countries = board.countries.map((c) => ({
    name: c.name,
    iso3: c.iso3,
    param: c.iso3.toLowerCase(),
  }));

  // Back to the structural country profile when one exists; otherwise to the
  // news board (BGD/THA have no profile page yet).
  const hasProfile = Boolean(getCountryByIso(iso));
  const backHref: Route = hasProfile
    ? (`/countries/${iso}` as Route)
    : ("/risk-board" as Route);
  const backLabel = hasProfile ? "COUNTRY PROFILE" : "NEWS BOARD";

  return (
    <LivePulseTerminal
      detail={detail}
      seriesData={liveData}
      articles={liveArticles}
      countries={countries}
      backHref={backHref}
      backLabel={backLabel}
    />
  );
}
