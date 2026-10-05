/**
 * Generate `data/country-recipe-scores-mock.json` — Week-2 mock data
 * scaffold for #464 (Frontend route restructure). Mirrors the future
 * `qgi_data.country_recipe_scores` table per #463.
 *
 * One pseudo-similarity score per (country, recipe) for a sample of
 * high-tier countries. Real scores ship in Week 3.
 *
 * Re-run:  npx tsx scripts/generate-country-recipe-scores-mock.ts
 */
import { writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";

interface Recipe {
  event_category: string;
}

interface RecipesFile {
  recipes: Recipe[];
}

const ROOT = join(__dirname, "..");

const recipesPath = join(ROOT, "data", "recipes-aggregated-mock.json");
const recipes: RecipesFile = JSON.parse(readFileSync(recipesPath, "utf-8"));

// Sample countries (high-tier picks Amin and the user persona feedback
// flagged most often + a few mid-risk for variety). Slugs match the
// output of `countrySlug()` in lib/slug.ts.
const COUNTRY_SLUGS = [
  "yemen",
  "syria",
  "venezuela",
  "lebanon",
  "haiti",
  "myanmar",
  "sudan",
  "pakistan",
  "afghanistan",
  "iran",
];

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function round(n: number, decimals: number): number {
  const f = 10 ** decimals;
  return Math.round(n * f) / f;
}

const TIMESTAMP = "2026-04-26T12:00:00.000Z";

const scores: Record<string, Record<string, number>> = {};

for (const country of COUNTRY_SLUGS) {
  const countryScores: Record<string, number> = {};
  // Each country gets a score for ~30-50 recipes (not all 71 — closer
  // to real data where tail recipes don't fire on every country).
  const k = 30 + (hashString(country) % 20);
  const seed = hashString(country);
  // Pick which recipes fire — top-k by stable shuffle.
  const allCats = recipes.recipes.map((r) => r.event_category);
  const picked = new Set<string>();
  let idx = seed % allCats.length;
  while (picked.size < k && picked.size < allCats.length) {
    picked.add(allCats[idx]);
    idx = (idx + 1103515245 + picked.size * 12345) % allCats.length;
  }
  let i = 0;
  for (const cat of picked) {
    // Score in [0.18, 0.92]; first ~5 picks are higher-salience for
    // each country so the country page has a few hero items.
    const base = i < 5 ? 0.7 : 0.35;
    const wobble = ((hashString(country + cat) % 220) / 1000) * (i < 5 ? 1 : 0.8);
    const score = round(Math.min(0.92, Math.max(0.18, base + wobble)), 2);
    countryScores[cat] = score;
    i++;
  }
  scores[country] = countryScores;
}

const output = {
  generated_at: TIMESTAMP,
  schema_version: 1,
  pipeline_version: "mock-v0",
  scores,
};

const outPath = join(ROOT, "data", "country-recipe-scores-mock.json");
writeFileSync(outPath, JSON.stringify(output, null, 2));
console.log(`Wrote scores for ${COUNTRY_SLUGS.length} countries to ${outPath}`);
