/**
 * Indicator value reads (#148)
 *
 * Pattern detail pages need the time series for several (indicator, country)
 * pairs at once — typically 5-25 indicators per pattern. The original
 * implementation issued one Athena query per (indicator, country) which
 * meant 5-25 cold-start round-trips, each 2-10s. A pattern with 22
 * indicators took 30+ seconds to fully render charts.
 *
 * This module migrates the read path to DynamoDB:
 *
 *   Table:  qgi-indicator-values
 *   PK:     indicator_country : S   (e.g. "SP.POP.TOTL#South Korea")
 *   SK:     year              : N
 *   attr:   value             : N
 *
 * The detail route is expected to call `getIndicatorValuesBatch(...)` once
 * with the full list of (indicator, country, startYear, length) tuples it
 * needs. We expand each tuple into the explicit (PK, SK) keys, batch them
 * 100 at a time into BatchGetItem, and return a per-tuple values array.
 *
 * The legacy `getIndicatorValues(indicator, country, startYear, length)`
 * function is kept for backwards compatibility — it just calls the batch
 * helper with a single tuple. Existing call sites don't need to change.
 *
 * On any DDB error, or when the requested keys are entirely missing from
 * DDB (fresh environment, backfill not yet run), we fall back to the
 * original Athena query path so the page still renders. The Athena
 * fallback is logged so we can spot environments that haven't been
 * backfilled.
 */

import {
  DynamoDBClient,
  BatchGetItemCommand,
  type BatchGetItemCommandOutput,
  type AttributeValue,
} from "@aws-sdk/client-dynamodb";
import { runQuery } from "@/lib/athena";

const REGION = "eu-central-1";
const TABLE_NAME = process.env.QGI_INDICATOR_VALUES_TABLE ?? "qgi-indicator-values";

// Per-(indicator, country) cache, surviving HMR via globalThis. Same trick
// as lib/athena.ts and lib/dashboard-cache.ts (#143/#146).
type CountryYearMap = Map<number, number>;
const globalForIndicators = globalThis as typeof globalThis & {
  __qgiIndicatorCache?: Map<string, CountryYearMap>;
};
const cache =
  globalForIndicators.__qgiIndicatorCache ?? new Map<string, CountryYearMap>();
if (!globalForIndicators.__qgiIndicatorCache) {
  globalForIndicators.__qgiIndicatorCache = cache;
}

let _ddbClient: DynamoDBClient | undefined;
function getDdbClient(): DynamoDBClient {
  if (!_ddbClient) _ddbClient = new DynamoDBClient({ region: REGION });
  return _ddbClient;
}

function cacheKey(indicatorId: string, country: string): string {
  return `${indicatorId}::${country}`;
}

function ddbPk(indicatorId: string, country: string): string {
  return `${indicatorId}#${country}`;
}

/**
 * Public single-tuple API. Backwards compatible with the original signature.
 * Just delegates to the batch helper with one entry.
 */
export async function getIndicatorValues(
  indicatorId: string,
  countryName: string,
  startYear: number,
  length: number
): Promise<number[]> {
  const result = await getIndicatorValuesBatch([
    { indicatorId, countryName, startYear, length },
  ]);
  return result[0] ?? [];
}

export interface IndicatorRequest {
  indicatorId: string;
  countryName: string;
  startYear: number;
  length: number;
}

/**
 * Public batch API. Returns one number[] per request, in the same order as
 * the input. Each array has length === request.length, with NaN for any
 * year that has no data on either side.
 *
 * #148: Single DDB BatchGetItem replaces what used to be N Athena cold
 * starts. Falls back to the per-request Athena query path if DDB returns
 * nothing for a (indicator, country) pair (fresh environment, backfill
 * not yet run).
 */
export async function getIndicatorValuesBatch(
  requests: IndicatorRequest[]
): Promise<number[][]> {
  if (requests.length === 0) return [];

  // 1. Build the (indicator, country) → year-set we need to fetch, after
  //    consulting the in-process cache.
  type Pair = { indicatorId: string; countryName: string };
  const pairsToFetch = new Map<string, { pair: Pair; years: Set<number> }>();
  for (const req of requests) {
    const key = cacheKey(req.indicatorId, req.countryName);
    const cached = cache.get(key);
    for (let y = req.startYear; y < req.startYear + req.length; y++) {
      if (cached?.has(y)) continue;
      let entry = pairsToFetch.get(key);
      if (!entry) {
        entry = {
          pair: { indicatorId: req.indicatorId, countryName: req.countryName },
          years: new Set(),
        };
        pairsToFetch.set(key, entry);
      }
      entry.years.add(y);
    }
  }

  // 2. Issue DynamoDB BatchGetItem. The wire format requires individual
  //    (PK, SK) tuples — flatten the per-pair year sets and chunk into 100s.
  type DdbKey = { indicator_country: { S: string }; year: { N: string } };
  const allKeys: DdbKey[] = [];
  for (const { pair, years } of pairsToFetch.values()) {
    const pk = ddbPk(pair.indicatorId, pair.countryName);
    for (const year of years) {
      allKeys.push({
        indicator_country: { S: pk },
        year: { N: String(year) },
      });
    }
  }

  if (allKeys.length > 0) {
    try {
      await fetchKeysFromDdb(allKeys);
    } catch (err) {
      console.warn(
        `[#148] DDB BatchGetItem failed (${(err as Error).message}); falling back to Athena per-pair`
      );
    }
  }

  // 3. For any (pair) that still has no cache entry at all (DDB miss or
  //    DDB unavailable), fall back to the legacy Athena query so the page
  //    still renders. This is the graceful degradation path used during
  //    fresh environments / backfill periods.
  const ddbMissPairs: Pair[] = [];
  for (const { pair } of pairsToFetch.values()) {
    if (!cache.has(cacheKey(pair.indicatorId, pair.countryName))) {
      ddbMissPairs.push(pair);
    }
  }
  if (ddbMissPairs.length > 0) {
    console.warn(
      `[#148] ${ddbMissPairs.length} (indicator, country) pairs missing from DDB — falling back to Athena. ` +
        `This usually means the qgi-pipeline-a-completer hasn't backfilled yet.`
    );
    await Promise.all(
      ddbMissPairs.map((pair) =>
        athenaFallback(pair.indicatorId, pair.countryName).catch((err) => {
          console.warn(
            `[#148] Athena fallback failed for ${pair.indicatorId}/${pair.countryName}: ${(err as Error).message}`
          );
        })
      )
    );
  }

  // 4. Assemble per-request output arrays from the cache.
  return requests.map((req) => {
    const key = cacheKey(req.indicatorId, req.countryName);
    const series = cache.get(key);
    const out: number[] = [];
    for (let y = req.startYear; y < req.startYear + req.length; y++) {
      const v = series?.get(y);
      out.push(v ?? NaN);
    }
    return out;
  });
}

/**
 * Issue one or more BatchGetItem calls covering the supplied keys. Splits
 * into 100-key chunks (the BatchGetItem hard limit) and merges the results
 * into the in-process cache. Handles DDB's UnprocessedKeys retry contract.
 */
async function fetchKeysFromDdb(
  keys: Array<{ indicator_country: { S: string }; year: { N: string } }>
): Promise<void> {
  const client = getDdbClient();
  const CHUNK = 100;

  for (let i = 0; i < keys.length; i += CHUNK) {
    let pendingKeys = keys.slice(i, i + CHUNK);
    let attempt = 0;
    while (pendingKeys.length > 0) {
      attempt++;
      if (attempt > 5) {
        console.warn(
          `[#148] DDB BatchGetItem still has ${pendingKeys.length} unprocessed keys after 5 attempts; abandoning`
        );
        break;
      }

      const res: BatchGetItemCommandOutput = await client.send(
        new BatchGetItemCommand({
          RequestItems: { [TABLE_NAME]: { Keys: pendingKeys } },
        })
      );

      const items = res.Responses?.[TABLE_NAME] ?? [];
      for (const item of items) {
        ingestDdbItem(item);
      }

      const unprocessed = res.UnprocessedKeys?.[TABLE_NAME]?.Keys;
      if (!unprocessed || unprocessed.length === 0) break;
      // Exponential backoff before retrying unprocessed keys
      await new Promise((r) => setTimeout(r, 50 * attempt));
      pendingKeys = unprocessed as typeof pendingKeys;
    }
  }
}

function ingestDdbItem(item: Record<string, AttributeValue>): void {
  const pkAttr = item.indicator_country;
  const yearAttr = item.year;
  const valueAttr = item.value;
  if (!pkAttr || !("S" in pkAttr) || !pkAttr.S) return;
  if (!yearAttr || !("N" in yearAttr) || !yearAttr.N) return;
  if (!valueAttr || !("N" in valueAttr) || !valueAttr.N) return;

  const pk = pkAttr.S;
  const hashIdx = pk.indexOf("#");
  if (hashIdx < 0) return;
  const indicatorId = pk.slice(0, hashIdx);
  const country = pk.slice(hashIdx + 1);
  const year = Number(yearAttr.N);
  const value = Number(valueAttr.N);
  if (!Number.isFinite(year) || !Number.isFinite(value)) return;

  const key = cacheKey(indicatorId, country);
  let series = cache.get(key);
  if (!series) {
    series = new Map();
    cache.set(key, series);
  }
  series.set(year, value);
}

/**
 * Legacy Athena fallback path. Identical to the original implementation but
 * pulled into its own function so the batch helper can call it for any
 * (indicator, country) pair the DDB read missed entirely. We populate the
 * same cache the DDB path uses, so subsequent calls in the same request
 * skip both DDB and Athena.
 */
async function athenaFallback(indicatorId: string, countryName: string): Promise<void> {
  // T13 #306 HIGH + QA P1-5 (2026-04-19): sanitize `indicatorId` before
  // interpolation. Original regex was WB-only (`[A-Z0-9]+(\.[A-Z0-9]+)+`)
  // which silently rejected FAOSTAT (`fao_cereal_yield`) and ILOSTAT
  // (`EAP_TEAP_SEX_AGE_RT_A`) IDs that will land with #150. Broadened to
  // accept letters (upper+lower), digits, underscores, and dots — still
  // rejects quotes, semicolons, spaces, wildcards, comments, etc.
  //
  // TODO(#150, indicator-catalog): once FAOSTAT/ILOSTAT XLSXs land and
  // indexes.json becomes a true catalog SoT, replace this regex with an
  // exact `has()` check against the catalog so new providers are opt-in
  // rather than regex-dodge.
  if (!/^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$/.test(indicatorId)) {
    console.warn(
      `[indicator-values] rejected indicator_id with unexpected shape: ${JSON.stringify(
        indicatorId
      )}`
    );
    return;
  }
  const safe = countryName.replace(/'/g, "''");
  const rows = await runQuery(
    `SELECT year, value FROM qgi_data.indicators
     WHERE indicator_id = '${indicatorId}'
       AND country = '${safe}'
     ORDER BY year`
  );
  const series: CountryYearMap = new Map();
  for (const row of rows) {
    const y = parseInt(row.year, 10);
    const v = parseFloat(row.value);
    if (!isNaN(y) && !isNaN(v)) {
      series.set(y, v);
    }
  }
  // Only seed the cache if we got at least one row — otherwise leave empty
  // so the next caller retries instead of caching a permanent empty.
  if (series.size > 0) {
    cache.set(cacheKey(indicatorId, countryName), series);
  }
}
