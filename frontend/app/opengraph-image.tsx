import { ImageResponse } from "next/og";
import { OgFrame, OG_SIZE, OG_CONTENT_TYPE } from "@/lib/og/OgFrame";

export const runtime = "edge";
export const alt =
  "QG Intelligence · Geopolitics, measured. Country risk read against the historical record, from public data and documented methods.";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
  return new ImageResponse(
    <OgFrame
      eyebrow="Quantitative Geopolitical Intelligence"
      title="Geopolitics, measured."
      tagline="Every country's trajectory read against the historical record, from public data and documented methods. Evidence, not opinion."
    />,
    OG_SIZE
  );
}
