import { NextResponse } from "next/server";
import { loadCountryRisks } from "@/lib/country-risks";

/**
 * GET /api/country-risks
 *
 * Returns the pre-computed country-risks.json from S3 or local fallback.
 * No auth required — data is aggregate risk tiers, not sensitive.
 * Cache for 1 hour at the edge.
 */
export async function GET() {
  try {
    const data = await loadCountryRisks();
    return NextResponse.json(data, {
      headers: {
        "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=7200",
      },
    });
  } catch (err) {
    // T9 #302 HIGH fix (2026-04-19): don't echo the raw exception message
    // — it may include S3 bucket names/ARNs. Log server-side, return
    // generic.
    console.error("country-risks route failed:", err);
    return NextResponse.json(
      { error: "Country risk data temporarily unavailable" },
      { status: 503 }
    );
  }
}
