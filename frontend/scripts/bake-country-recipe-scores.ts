/**
 * Bake `data/country-recipe-scores.json` from Athena `qgi_data.country_recipe_scores`
 * (#546, replaces hand-curated `country-recipe-scores-mock.json`).
 *
 * Schema: {[countrySlug]: {[event_category]: similarity_calibrated}}.
 * Country slugs are resolved via `data/countries.json` (id → slug).
 *
 * Re-run:  npx tsx scripts/bake-country-recipe-scores.ts
 */
import { writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";

import {
  AthenaClient,
  StartQueryExecutionCommand,
  GetQueryExecutionCommand,
  GetQueryResultsCommand,
} from "@aws-sdk/client-athena";
import { countrySlug } from "../lib/slug";

const REGION = "eu-central-1";
const DB = "qgi_data";
const WG = "QGI-Lambda-Workgroup";
const OUT = join(process.cwd(), "data", "country-recipe-scores.json");
const COUNTRIES = join(process.cwd(), "data", "countries.json");

interface CountryRow {
  id: string | number;
  name: string;
}

interface CountryRecipeScoresFile {
  generated_at: string;
  pipeline_version: string;
  schema_version: number;
  scores: { [countrySlug: string]: { [event_category: string]: number } };
}

async function runQuery(client: AthenaClient, sql: string): Promise<string[][]> {
  const start = await client.send(
    new StartQueryExecutionCommand({
      QueryString: sql,
      QueryExecutionContext: { Database: DB },
      WorkGroup: WG,
    })
  );
  const qid = start.QueryExecutionId!;
  for (let i = 0; i < 60; i++) {
    const exec = await client.send(
      new GetQueryExecutionCommand({ QueryExecutionId: qid })
    );
    const state = exec.QueryExecution?.Status?.State;
    if (state === "SUCCEEDED") break;
    if (state === "FAILED" || state === "CANCELLED") {
      throw new Error(
        `Query ${state}: ${exec.QueryExecution?.Status?.StateChangeReason}`
      );
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  const rows: string[][] = [];
  let nextToken: string | undefined;
  let isFirst = true;
  do {
    const res = await client.send(
      new GetQueryResultsCommand({
        QueryExecutionId: qid,
        NextToken: nextToken,
      })
    );
    for (const row of res.ResultSet?.Rows ?? []) {
      if (isFirst) {
        isFirst = false;
        continue;
      }
      rows.push((row.Data ?? []).map((c) => c.VarCharValue ?? ""));
    }
    nextToken = res.NextToken;
  } while (nextToken);
  return rows;
}

function buildCountrySlugMap(): Map<number, string> {
  // countries.json is an array of {id, name, alpha_2}. Slug derived via
  // lib/slug.ts::countrySlug, the canonical name→slug helper used elsewhere
  // in the frontend (e.g. country-risks.ts:148).
  const file = JSON.parse(readFileSync(COUNTRIES, "utf-8")) as CountryRow[];
  const m = new Map<number, string>();
  for (const c of file) {
    const id = Number(c.id);
    if (Number.isNaN(id)) continue;
    const slug = countrySlug(c.name);
    if (slug) m.set(id, slug);
  }
  return m;
}

async function main() {
  console.log("[bake-country-recipe-scores] Connecting to Athena...");
  const client = new AthenaClient({ region: REGION });
  const slugMap = buildCountrySlugMap();
  console.log(
    `[bake-country-recipe-scores] Loaded ${slugMap.size} country slug mappings`
  );

  // Skip suppressed rows and rows with null similarity_calibrated
  // country_recipe_scores doesn't have schema_version column (only
  // recipes_aggregated does). Pinning schema_version=1 in the output;
  // bump if the upstream Glue table grows a column.
  const sql = `
    SELECT
      cast(country_id as varchar) as country_id,
      event_category,
      cast(similarity_calibrated as varchar) as similarity_calibrated,
      cast(suppressed as varchar) as suppressed,
      pipeline_version
    FROM ${DB}.country_recipe_scores
    WHERE suppressed = false
      AND similarity_calibrated IS NOT NULL
  `;

  console.log("[bake-country-recipe-scores] Running Athena query...");
  const rows = await runQuery(client, sql);
  console.log(`[bake-country-recipe-scores] Got ${rows.length} score rows`);

  const scores: { [slug: string]: { [cat: string]: number } } = {};
  let pipelineVersion = "v2.0-baked";
  const schemaVersion = 1; // pinned; country_recipe_scores has no schema_version column
  let unmappedCount = 0;
  for (const r of rows) {
    const [country_id, event_category, similarity, , pipeline_version] = r;
    pipelineVersion = pipeline_version;
    const id = Number(country_id);
    const slug = slugMap.get(id);
    if (!slug) {
      unmappedCount++;
      continue;
    }
    if (!scores[slug]) scores[slug] = {};
    scores[slug][event_category] = Number(similarity);
  }

  if (unmappedCount > 0) {
    console.warn(
      `[bake-country-recipe-scores] WARNING: ${unmappedCount} rows had country_ids not in countries.json (skipped)`
    );
  }

  const out: CountryRecipeScoresFile = {
    generated_at: new Date().toISOString(),
    pipeline_version: pipelineVersion,
    schema_version: schemaVersion,
    scores,
  };

  writeFileSync(OUT, JSON.stringify(out, null, 2));
  console.log(
    `[bake-country-recipe-scores] Wrote ${OUT} (${Object.keys(scores).length} countries, ${(JSON.stringify(out).length / 1024).toFixed(1)} KB)`
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
