import { NextResponse } from "next/server";
import indexData from "@/data/indexes.json";

export const revalidate = false; // build-time only

export function GET() {
  return NextResponse.json(indexData);
}
