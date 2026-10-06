// Serves the live news-pulse freshness stamp from a DYNAMIC request context.
//
// Why a route (not the page server component): the Vercel OIDC token used to
// read the private S3 file is only available inside a request/function context.
// ISR static regeneration runs outside one, so a page that read S3 during
// revalidation silently got `absent`. The pages stay fast (static/ISR); the
// small <LivePulseStamp> client widget fetches this route, which DOES run in a
// request context and can assume the read-only AWS role.
import { NextResponse } from "next/server";
import { getLiveStamp } from "@/lib/hf/live-pulse";

export const dynamic = "force-dynamic";

export async function GET() {
  const stamp = await getLiveStamp();
  return NextResponse.json(stamp, {
    // Cache at the edge for a minute so visitors don't each trigger an S3
    // read; the data only changes hourly, so this stays plenty fresh.
    headers: { "cache-control": "public, max-age=60, s-maxage=60" },
  });
}
