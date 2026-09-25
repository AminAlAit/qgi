import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/auth";
import { runQuery } from "@/lib/athena";
import { getDashboardJson, type RecipesTop50Payload } from "@/lib/dashboard-cache";

// Dynamic: requires AWS credentials at runtime, cannot prerender at build time.
export const dynamic = "force-dynamic";

export const GET = withAuth(async (_req: NextRequest) => {
  // #146: try the pre-computed dashboard JSON first.
  const cached = await getDashboardJson<RecipesTop50Payload>("recipes-top50.json");
  if (cached) {
    return NextResponse.json(
      // #137: wrap with generated_at so the frontend can render data freshness UX
      { generated_at: cached.generated_at, results: cached.results },
      {
        // #144: edge-cache for 24h on CloudFront once Amplify (#102) lands
        headers: { "Cache-Control": "public, max-age=300, s-maxage=86400" },
      }
    );
  }

  // Fallback: query recipes JOIN convergence view directly.
  // #129: recipes is pre-deduplicated at source.
  // #133: rank by composite sort key (best_pps × ln(1+convergence)),
  // require n_predictors >= 2.
  const currentYear = new Date().getFullYear();
  const rows = await runQuery(
    `WITH joined AS (
       SELECT r.*,
              cv.convergence_score, cv.n_predictors, cv.n_regions,
              cv.convergence_tier, cv.predictor_country_ids, cv.composite_sort_key
       FROM qgi_data.recipes r
       INNER JOIN qgi_data.recipe_convergence cv
         ON cv.following_country_id = r.country_a_id
        AND cv.event_category       = r.event_category
        AND cv.end_year_a           = r.end_year_a
       WHERE r.start_year_b < r.start_year_a
         AND (r.start_year_a + r.length) >= ${currentYear - 2}
         AND (r.start_year_a + r.length) <= ${currentYear + 3}
         AND cv.n_predictors >= 2
     ),
     ranked AS (
       SELECT j.*,
         ROW_NUMBER() OVER (PARTITION BY j.country_a_id   ORDER BY j.composite_sort_key DESC) AS country_rank,
         ROW_NUMBER() OVER (PARTITION BY j.event_category ORDER BY j.composite_sort_key DESC) AS cat_rank
       FROM joined j
     )
     SELECT * FROM ranked
     WHERE country_rank <= 3 AND cat_rank <= 10
     ORDER BY composite_sort_key DESC
     LIMIT 50`
  );

  // Athena returns array<smallint> as a string like "[1, 5, 23]"
  const parseIdArray = (raw: string | undefined): number[] => {
    if (!raw) return [];
    return raw
      .replace(/[\[\]\s]/g, "")
      .split(",")
      .filter(Boolean)
      .map(Number)
      .filter((n) => !Number.isNaN(n));
  };

  return NextResponse.json({
    // #137: live Athena query — generated_at is "now"
    generated_at: new Date().toISOString(),
    results: rows.map((r) => ({
      recipe_id: r.recipe_id,
      event_category: r.event_category,
      country_a_id: Number(r.country_a_id),
      country_b_id: Number(r.country_b_id),
      country_a_name: r.country_a_name || `Country ${r.country_a_id}`,
      country_b_name: r.country_b_name || `Country ${r.country_b_id}`,
      start_year_a: Number(r.start_year_a),
      start_year_b: Number(r.start_year_b),
      length: Number(r.length),
      avg_correlation: Number(r.avg_correlation),
      end_year_a: Number(r.end_year_a),
      end_year_b: Number(r.end_year_b),
      event_window: Number(r.event_window),
      event_year_a: Number(r.event_year_a),
      event_year_b: Number(r.event_year_b),
      event_title_a: r.event_title_a,
      event_title_b: r.event_title_b,
      indicator_count: Number(r.indicator_count),
      instance_count: Number(r.instance_count),
      pattern_power_score: Number(r.pattern_power_score),
      pps: Number(r.pps),
      pattern_tier: r.pattern_tier ?? null,
      // #134: forecast timing
      median_lead_time: r.median_lead_time_b ? Number(r.median_lead_time_b) : null,
      min_lead_time: r.min_lead_time_b ? Number(r.min_lead_time_b) : null,
      max_lead_time: r.max_lead_time_b ? Number(r.max_lead_time_b) : null,
      convergence_score: Number(r.convergence_score),
      convergence_tier: r.convergence_tier,
      n_predictors: Number(r.n_predictors),
      n_regions: Number(r.n_regions),
      predictor_country_ids: parseIdArray(r.predictor_country_ids),
      composite_sort_key: Number(r.composite_sort_key),
    })),
  });
});
