import { NextRequest, NextResponse } from "next/server";
import { withAuth, requireGroup } from "@/lib/auth";
import { runQuery } from "@/lib/athena";
import indexData from "@/data/indexes.json";

const indexByNumericId = new Map<number, { name: string; sector: string; org: string }>();
for (const idx of indexData as {
  numeric_id: number | null;
  name: string;
  sector: string;
  org: string;
}[]) {
  if (idx.numeric_id != null) {
    indexByNumericId.set(idx.numeric_id, {
      name: idx.name,
      sector: idx.sector,
      org: idx.org,
    });
  }
}

export const GET = withAuth(async (req: NextRequest, payload) => {
  // #445: raw SCDI list (indicator + correlation per pair) is core IP.
  // Gated to pro plan. In dev, set SKIP_AUTH_GROUPS=pro to exercise the route.
  requireGroup(payload, "pro");

  const { searchParams } = req.nextUrl;
  const country_a = searchParams.get("country_a");
  const country_b = searchParams.get("country_b");
  const length = searchParams.get("length");
  const start_year_a = searchParams.get("start_year_a");
  const start_year_b = searchParams.get("start_year_b");

  // #425: the original contract accepted only (country_a, country_b)
  // which returned ALL SCDI rows across every (length, start_year) combo
  // for that pair (~780K rows for Syria/Turkiye). That exceeded Vercel's
  // 10s function timeout every time it ran. Scoping to a single pattern
  // window is the correct contract — SCDIs only make sense in the
  // context of a specific window — and brings the query to ~5s / ~20
  // rows. Callers that want cross-window SCDI aggregation should use
  // /api/patterns/detail (which already returns scoped SCDIs inline).
  if (!country_a || !country_b || !length || !start_year_a || !start_year_b) {
    return NextResponse.json(
      {
        error:
          "country_a, country_b, length, start_year_a, and start_year_b are required",
      },
      { status: 400 }
    );
  }

  const aId = Number(country_a);
  const bId = Number(country_b);
  const lenNum = Number(length);
  const startA = Number(start_year_a);
  const startB = Number(start_year_b);

  if (
    !Number.isFinite(aId) ||
    !Number.isFinite(bId) ||
    !Number.isFinite(lenNum) ||
    !Number.isFinite(startA) ||
    !Number.isFinite(startB)
  ) {
    return NextResponse.json({ error: "Invalid numeric parameter" }, { status: 400 });
  }

  const rows = await runQuery(
    `SELECT indicator_numeric_id, correlation, start_year_a, start_year_b, length
     FROM qgi_data.scdis
     WHERE country_a_id = ${aId}
       AND country_b_id = ${bId}
       AND length = ${lenNum}
       AND start_year_a = ${startA}
       AND start_year_b = ${startB}
     ORDER BY CAST(correlation AS DOUBLE) DESC`
  );

  return NextResponse.json(
    rows.map((r) => {
      const numId = Number(r.indicator_numeric_id);
      const meta = indexByNumericId.get(numId);
      return {
        indicator_numeric_id: numId,
        index_name: meta?.name ?? `Indicator #${numId}`,
        sector: meta?.sector ?? "Unknown",
        org: meta?.org ?? "Unknown",
        correlation: Number(r.correlation),
        start_year_a: Number(r.start_year_a),
        start_year_b: Number(r.start_year_b),
        length: Number(r.length),
        predicted: false,
      };
    })
  );
});
