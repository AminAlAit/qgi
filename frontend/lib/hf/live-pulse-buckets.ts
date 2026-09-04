/**
 * live-pulse-buckets — server-only runtime reader for the intraday news-pulse
 * SERIES (and, once the poller emits it, the live article feed).
 *
 * Same S3 pattern as lib/hf/live-pulse.ts: read at request time (the terminal
 * page is ISR with a short revalidate), OIDC role on Vercel via AWS_ROLE_ARN,
 * default credential chain locally, an optional committed local fallback, and
 * NEVER throws — any failure yields null/[] so the terminal degrades to its
 * committed monthly history. The pure transform lives in live-pulse-buckets-core.
 */
import "server-only";

import {
  buildBucketSeries,
  type BaselineDoc,
  type BucketRes,
  type BucketsDoc,
  type PulseSeries,
} from "@/lib/hf/live-pulse-buckets-core";
import type { LiveArticle } from "@/lib/hf/live-pulse-series";

const BUCKET = process.env.QGI_DATA_LAKE_BUCKET ?? "qgi-data-lake-771606957899";
const REGION = process.env.AWS_REGION ?? "eu-central-1";
const BUCKETS_KEY = "dashboard/hf-pulse-buckets.json";
const BASELINE_KEY = "dashboard/hf-pulse-baseline.json";
// Written by a future poller extension; absent today -> articles stay empty.
const ARTICLES_KEY = "dashboard/hf-pulse-articles.json";
const RESOLUTIONS: BucketRes[] = ["1H", "4H", "1D"];

/** topic id -> resolution -> live series. */
export type BucketSeries = Record<string, Partial<Record<BucketRes, PulseSeries>>>;

interface ArticlesDoc {
  generated_at?: string;
  /** iso3 -> recent article rows. */
  articles: Record<string, LiveArticle[]>;
}

let _cache: {
  ts: number;
  buckets: BucketsDoc | null;
  baseline: BaselineDoc | null;
  articles: ArticlesDoc | null;
} | null = null;
const TTL = 5 * 60 * 1000; // 5 min — the poller writes hourly

/** Read+parse one S3 JSON object, falling back to a committed local file. */
async function readJson<T>(key: string): Promise<T | null> {
  try {
    const { S3Client, GetObjectCommand } = await import("@aws-sdk/client-s3");
    const roleArn = process.env.AWS_ROLE_ARN;
    const credentials = roleArn
      ? (await import("@vercel/oidc-aws-credentials-provider")).awsCredentialsProvider({
          roleArn,
        })
      : undefined;
    const s3 = new S3Client({ region: REGION, ...(credentials ? { credentials } : {}) });
    const resp = await s3.send(new GetObjectCommand({ Bucket: BUCKET, Key: key }));
    const body = await resp.Body?.transformToString();
    if (body) return JSON.parse(body) as T;
  } catch {
    // S3 miss / no creds / not applied yet — fall through to the local file.
  }
  try {
    const fs = await import("fs/promises");
    const path = await import("path");
    const base = key.split("/").pop() as string;
    const raw = await fs.readFile(path.join(process.cwd(), "data", base), "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

async function load(nowMs: number) {
  if (_cache && nowMs - _cache.ts < TTL) return _cache;
  const [buckets, baseline, articles] = await Promise.all([
    readJson<BucketsDoc>(BUCKETS_KEY),
    readJson<BaselineDoc>(BASELINE_KEY),
    readJson<ArticlesDoc>(ARTICLES_KEY),
  ]);
  _cache = { ts: nowMs, buckets, baseline, articles };
  return _cache;
}

/**
 * Intraday (1H/4H/1D) live pulse series for one country, or null when the
 * bucket cache or baseline is unavailable (caller keeps the monthly fallback).
 */
export async function getBucketSeries(
  iso3: string,
  nowMs: number = Date.now()
): Promise<BucketSeries | null> {
  try {
    const { buckets, baseline } = await load(nowMs);
    if (!buckets?.buckets || !baseline?.stats) return null;
    const key = iso3.toUpperCase();
    const out: BucketSeries = {};
    for (const res of RESOLUTIONS) {
      const built = buildBucketSeries(buckets.buckets, baseline, key, res);
      if (!built) return null; // country absent from the cache
      for (const [topic, series] of Object.entries(built)) {
        (out[topic] ??= {})[res] = series;
      }
    }
    return out;
  } catch {
    return null;
  }
}

/**
 * The live 24h article feed for one country. Empty until the poller is extended
 * to emit dashboard/hf-pulse-articles.json — so the terminal shows an honest
 * "live headlines coming soon" state rather than stale sample headlines.
 */
export async function getBucketArticles(
  iso3: string,
  nowMs: number = Date.now()
): Promise<LiveArticle[]> {
  try {
    const { articles } = await load(nowMs);
    return articles?.articles?.[iso3.toUpperCase()] ?? [];
  } catch {
    return [];
  }
}
