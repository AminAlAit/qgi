import { ImageResponse } from "next/og";
import { OgFrame, OG_SIZE, OG_CONTENT_TYPE } from "@/lib/og/OgFrame";

export const runtime = "edge";
export const alt = "Trend Tracker · QG Intelligence · Live status of all 69 trends";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
  return new ImageResponse(
    <OgFrame
      eyebrow="Blog · Trend Tracker"
      title="69 trends. 42 in play. Every one walks the gates."
      tagline="Live status board for every QGI trend. Each one is scored against validation gates in held-out historical data and graded on a confidence ladder, and most will not top it on a given walk."
      rightStat={{ value: "42", label: "Trends in play" }}
    />,
    OG_SIZE
  );
}
