/**
 * Dump qgi_data.countries to data/countries.json so the API route can serve
 * static data instead of hitting Athena on every request (#143).
 *
 * Usage: requires staging AWS credentials in the environment.
 *   tsx scripts/dump-countries.ts
 *
 * Re-run whenever the legacy countries table changes (rare — once per pipeline migration).
 */
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { runQuery } from "../lib/athena";

async function main() {
  console.log("Querying qgi_data.countries...");
  const rows = await runQuery(
    "SELECT id, name_1 AS name, alpha_2 FROM qgi_data.countries WHERE name_1 != '' ORDER BY name_1"
  );

  // Legacy table has duplicates — dedupe by id
  const seen = new Set<string>();
  const unique = rows.filter((r) => {
    if (!r.name || seen.has(r.id)) return false;
    seen.add(r.id);
    return true;
  });

  // #432 Bug 4: Namibia's alpha_2 is `""` in the legacy table because
  // somewhere upstream a CSV reader is treating the literal string "NA"
  // as a missing-value sentinel and rewriting it to empty. Frontend
  // consequence: the country card falls back to the alpha-2 badge
  // ("??") instead of the Namibian flag.
  //
  // Cheap fix here = patch the dumped JSON. Proper fix lives in
  // qgi-pipeline ingestion (filed under the upstream repo). Do the
  // same for any other historically NA-collision-prone codes if they
  // surface (so far only NA is broken).
  for (const row of unique) {
    if (row.name === "Namibia" && !row.alpha_2) row.alpha_2 = "NA";
  }

  const out = join(__dirname, "..", "data", "countries.json");
  writeFileSync(out, JSON.stringify(unique, null, 2));
  console.log(`Wrote ${unique.length} countries to ${out}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
