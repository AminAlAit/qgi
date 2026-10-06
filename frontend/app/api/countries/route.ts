import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/auth";
import { runQuery } from "@/lib/athena";

// Dynamic: Athena fallback requires AWS credentials, cannot prerender at build time.
// Prefer the static dump at data/countries.json — if missing, fall back to Athena.
// To populate the static file, run: `tsx scripts/dump-countries.ts` with staging creds.
export const dynamic = "force-dynamic";

type Country = { id: string; name: string; alpha_2: string };

let staticCache: Country[] | null | undefined;

async function loadStatic(): Promise<Country[] | null> {
  if (staticCache !== undefined) return staticCache;
  try {
    const path = join(process.cwd(), "data", "countries.json");
    const text = await readFile(path, "utf-8");
    staticCache = JSON.parse(text) as Country[];
  } catch {
    staticCache = null;
  }
  return staticCache;
}

export const GET = withAuth(async (_req: NextRequest) => {
  const staticCountries = await loadStatic();
  if (staticCountries) {
    return NextResponse.json(staticCountries);
  }

  // Fallback: query Athena (legacy path; remove once data/countries.json is committed)
  const rows = await runQuery(
    "SELECT id, name_1 AS name, alpha_2 FROM qgi_data.countries WHERE name_1 != '' ORDER BY name_1"
  );
  const seen = new Set<string>();
  const unique = rows.filter((r) => {
    if (!r.name || seen.has(r.id)) return false;
    seen.add(r.id);
    return true;
  });
  return NextResponse.json(unique);
});
