import { ImageResponse } from "next/og";
import { OgFrame, OG_SIZE, OG_CONTENT_TYPE } from "@/lib/og/OgFrame";

export const runtime = "edge";
export const alt = "Methodology · QG Intelligence · How QGI works";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
  return new ImageResponse(
    <OgFrame
      eyebrow="Methodology"
      title="How QGI works."
      tagline="Two methods that read open data against history, and show you the evidence behind every reading."
    />,
    OG_SIZE
  );
}
