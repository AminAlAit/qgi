import { ImageResponse } from "next/og";
import { OgFrame, OG_SIZE, OG_CONTENT_TYPE } from "@/lib/og/OgFrame";

export const runtime = "edge";
export const alt = "Blog · QG Intelligence · Development notes";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
  return new ImageResponse(
    <OgFrame
      eyebrow="Blog · Development Notes"
      title="A lab notebook that happens to be public."
      tagline="Scoring releases, methodology shifts, backtest results, and what the numbers actually mean. Closer to research notes than to product marketing."
    />,
    OG_SIZE
  );
}
