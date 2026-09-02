/**
 * Dashboard JSON cache reader (#146).
 *
 * Reads pre-computed dashboard JSONs from S3 instead of running Athena queries.
 * The pipeline-recipe-engine Lambda writes these on every monthly pipeline run
 * to s3://{S3_DATA_BUCKET}/dashboard/{ranking,early-warning,recipes-top50}.json.
 *
 * Routes that use this should still keep an Athena fallback for the case where
 * the pre-compute hasn't run yet (fresh environment) or is stale.
 */
import { GetObjectCommand, S3Client, NoSuchKey } from "@aws-sdk/client-s3";

const REGION = "eu-central-1";
const BUCKET = process.env.S3_DATA_BUCKET ?? "qgi-data-lake-771606957899";
const PREFIX = "dashboard";

// In-process cache so the same Lambda instance doesn't re-fetch on every request.
// Stored on globalThis so it survives `next dev` HMR (same trick as lib/athena.ts).
type CacheEntry<T> = { value: T; expiresAt: number };
const globalForDashboard = globalThis as typeof globalThis & {
  __qgiDashboardCache?: Map<string, CacheEntry<unknown>>;
};
const cache =
  globalForDashboard.__qgiDashboardCache ?? new Map<string, CacheEntry<unknown>>();
if (!globalForDashboard.__qgiDashboardCache) {
  globalForDashboard.__qgiDashboardCache = cache;
}
const CACHE_TTL_MS = 600_000; // 10 minutes

let _client: S3Client | undefined;
function getClient(): S3Client {
  if (!_client) _client = new S3Client({ region: REGION });
  return _client;
}

/**
 * Fetch a pre-computed dashboard JSON.
 * Priority: in-memory cache → local data/ file → S3 → null (caller falls back to Athena).
 */
export async function getDashboardJson<T>(filename: string): Promise<T | null> {
  const cacheKey = `${BUCKET}/${PREFIX}/${filename}`;
  const now = Date.now();
  const cached = cache.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    return cached.value as T;
  }

  // Try local baked file first (works in dev and Vercel)
  try {
    const fs = await import("fs/promises");
    const path = await import("path");
    const localPath = path.join(process.cwd(), "data", filename);
    const body = await fs.readFile(localPath, "utf-8");
    const parsed = JSON.parse(body) as T;
    cache.set(cacheKey, { value: parsed, expiresAt: now + CACHE_TTL_MS });
    return parsed;
  } catch {
    // Local file not found — try S3
  }

  // Fallback to S3
  try {
    const res = await getClient().send(
      new GetObjectCommand({ Bucket: BUCKET, Key: `${PREFIX}/${filename}` })
    );
    const body = await res.Body?.transformToString("utf-8");
    if (!body) return null;
    const parsed = JSON.parse(body) as T;
    cache.set(cacheKey, { value: parsed, expiresAt: now + CACHE_TTL_MS });
    return parsed;
  } catch (err) {
    if (err instanceof NoSuchKey) return null;
    const e = err as {
      name?: string;
      Code?: string;
      $metadata?: { httpStatusCode?: number };
    };
    if (
      e.name === "NoSuchKey" ||
      e.Code === "NoSuchKey" ||
      e.$metadata?.httpStatusCode === 404
    ) {
      return null;
    }
    // S3 connection error (no creds in local dev) — return null, let caller fall back
    return null;
  }
}

// Strongly-typed payload shapes that mirror what pipeline-recipe-engine writes.
// Keep these in sync with qgi-pipeline/lambdas/pipeline-recipe-engine/lambda_function.py.

// #122: PatternTier and ConvergenceTier unified in lib/types.ts; re-export for
// callers that import them from this module.
import type {
  PatternTier as _PatternTier,
  ConvergenceTier as _ConvergenceTier,
  SignalRow,
} from "@/lib/types";
export type PatternTier = _PatternTier;
export type ConvergenceTier = _ConvergenceTier;

export type RankingPayload = {
  generated_at: string;
  limit: number;
  results: Array<{
    country_a: string;
    country_b: string;
    country_a_id: string;
    country_b_id: string;
    start_year_a: number;
    start_year_b: number;
    pattern_length: number;
    avg_correlation: number;
    pattern_power_score: number;
    num_indexes: number;
    pattern_tier: PatternTier | null; // #128
    predicted: boolean;
  }>;
};

export type EarlyWarningPayload = {
  generated_at: string;
  as_of_year: number;
  results: Array<{
    country_a: string;
    country_b: string;
    start_year_a: string | number;
    start_year_b: string | number;
    pattern_length: string | number;
    avg_correlation: number;
    pattern_power_score: number;
    num_indexes: number;
    pattern_tier: PatternTier | null; // #128
  }>;
};

/**
 * #122: RecipesTop50Payload rows are the canonical V1.5.3 signal shape —
 * SignalRow with every optional V1.5.3 field marked as required. A
 * top50-entry ALWAYS has pps, pattern_tier, convergence_*, lead_time
 * because the recipe-engine CTAS populates all of them.
 */
export type RecipesTop50Payload = {
  generated_at: string;
  as_of_year: number;
  results: Array<
    SignalRow & {
      pps: number;
      pattern_tier: PatternTier | null;
      median_lead_time: number | null;
      min_lead_time: number | null;
      max_lead_time: number | null;
      convergence_score: number;
      convergence_tier: ConvergenceTier;
      n_predictors: number;
      n_regions: number;
      predictor_country_ids: number[];
      composite_sort_key: number;
    }
  >;
};
