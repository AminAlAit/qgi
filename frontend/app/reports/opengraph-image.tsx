import { ImageResponse } from "next/og";
import { OgFrame, OG_SIZE, OG_CONTENT_TYPE } from "@/lib/og/OgFrame";
import { SECTION_LABEL } from "./_data/reports-manifest";

export const runtime = "edge";
export const alt = `${SECTION_LABEL} · QG Intelligence`;
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
  return new ImageResponse(
    <OgFrame
      eyebrow={SECTION_LABEL}
      title="Structural findings only QGI's pattern engine can produce."
      tagline="Country analogues, sovereign-credit theses, and divergence reports — each anchored on a scored pattern, with method and date on every piece."
    />,
    OG_SIZE
  );
}
