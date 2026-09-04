import {
  AthenaClient,
  StartQueryExecutionCommand,
  GetQueryExecutionCommand,
  GetQueryResultsCommand,
  type Row,
} from "@aws-sdk/client-athena";
import { unstable_cache } from "next/cache";

const REGION = process.env.AWS_REGION ?? "eu-central-1";
const WORKGROUP = process.env.ATHENA_WORKGROUP ?? "QGI-Lambda-Workgroup";
const OUTPUT_LOCATION =
  process.env.ATHENA_OUTPUT_LOCATION ?? "s3://qgi-data-lake-771606957899/query_results/";
const CACHE_TTL_SECONDS = 600; // 10 minutes

function getClient(): AthenaClient {
  return new AthenaClient({ region: REGION });
}

function rowsToObjects(rows: Row[]): Record<string, string>[] {
  if (rows.length < 2) return [];
  const headers = rows[0].Data?.map((c) => c.VarCharValue ?? "") ?? [];
  return rows.slice(1).map((row) => {
    const obj: Record<string, string> = {};
    row.Data?.forEach((cell, i) => {
      obj[headers[i]] = cell.VarCharValue ?? "";
    });
    return obj;
  });
}

async function poll(client: AthenaClient, queryExecutionId: string): Promise<void> {
  for (let attempt = 0; attempt < 120; attempt++) {
    await new Promise((r) => setTimeout(r, 500));
    const { QueryExecution } = await client.send(
      new GetQueryExecutionCommand({ QueryExecutionId: queryExecutionId })
    );
    const state = QueryExecution?.Status?.State;
    if (state === "SUCCEEDED") return;
    if (state === "FAILED" || state === "CANCELLED") {
      throw new Error(
        `Athena query ${state}: ${QueryExecution?.Status?.StateChangeReason ?? "unknown"}`
      );
    }
  }
  throw new Error("Athena query timed out after 60s");
}

/**
 * Internal: actually run an Athena query (no caching). Wrapped by `runQuery`.
 */
async function _runQueryUncached(
  sql: string,
  database: string
): Promise<Record<string, string>[]> {
  const client = getClient();
  const { QueryExecutionId } = await client.send(
    new StartQueryExecutionCommand({
      QueryString: sql,
      QueryExecutionContext: { Database: database },
      WorkGroup: WORKGROUP,
      ResultConfiguration: { OutputLocation: OUTPUT_LOCATION },
      // #625 (rescoped post #632): per-query result reuse with a 60-min
      // TTL. The workgroup-level `ResultReuseConfiguration` approach in the
      // original ticket was wrong — Athena only accepts this on each
      // `StartQueryExecution` call, not on `UpdateWorkGroup`. Adding it here
      // means: identical SQL fired within 60min returns Athena's cached
      // result, costing $0 and skipping the data scan. This layers under
      // the 10-min `unstable_cache` above — when Next's cache misses (cold
      // serverless instance, HMR, restart), Athena's per-query reuse still
      // catches it.
      ResultReuseConfiguration: {
        ResultReuseByAgeConfiguration: {
          Enabled: true,
          MaxAgeInMinutes: 60,
        },
      },
    })
  );
  if (!QueryExecutionId) throw new Error("No QueryExecutionId returned");

  await poll(client, QueryExecutionId);

  const allRows: Record<string, string>[] = [];
  let nextToken: string | undefined;
  do {
    const res = await client.send(
      new GetQueryResultsCommand({ QueryExecutionId, NextToken: nextToken })
    );
    const rows = res.ResultSet?.Rows ?? [];
    // First page includes header row; subsequent pages don't
    if (allRows.length === 0) {
      allRows.push(...rowsToObjects(rows));
    } else {
      // Prepend a fake header row so rowsToObjects works
      const firstPageHeaders =
        res.ResultSet?.ResultSetMetadata?.ColumnInfo?.map((c) => ({
          VarCharValue: c.Name,
        })) ?? [];
      allRows.push(...rowsToObjects([{ Data: firstPageHeaders }, ...rows]));
    }
    nextToken = res.NextToken;
  } while (nextToken);

  return allRows;
}

/**
 * Internal cached wrapper. unstable_cache uses the literal args as part of the
 * cache key, so we always pass `database` explicitly (never let a default kick
 * in) to keep the key stable across call sites.
 */
const _runQueryCached = unstable_cache(
  (sql: string, database: string) => _runQueryUncached(sql, database),
  ["qgi-athena-query"],
  { revalidate: CACHE_TTL_SECONDS, tags: ["athena"] }
);

/**
 * Run an Athena query with caching (#144).
 *
 * Uses Next.js `unstable_cache` (filesystem-backed in dev, Next data cache in
 * production). Survives `next dev` HMR hot-reloads and is shared across server
 * instances in production. Cache TTL: 10 minutes.
 *
 * Note: `unstable_cache` is being phased out in Next 16 in favor of the
 * `'use cache'` directive (which requires opting into Cache Components).
 * Migrate when QGI enables Cache Components project-wide.
 */
export function runQuery(
  sql: string,
  database: string = "qgi_data"
): Promise<Record<string, string>[]> {
  return _runQueryCached(sql, database);
}
