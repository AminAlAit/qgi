import { ImageResponse } from "next/og";
import { OgFrame, OG_SIZE, OG_CONTENT_TYPE } from "@/lib/og/OgFrame";

export const runtime = "edge";
export const alt = "About QG Intelligence · Built by Amin Al-Ait · Cloud Data Engineer";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
  return new ImageResponse(
    <OgFrame
      eyebrow="About · Amin Al-Ait"
      title="Built solo, in the open, on Open Source Intelligence."
      tagline="Cloud Data Engineer. Five years building the structural-precedent platform that asks honest questions of geopolitical data."
    />,
    OG_SIZE
  );
}
