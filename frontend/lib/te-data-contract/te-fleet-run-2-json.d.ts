/**
 * Ambient module declarations for S3-fetched TE fleet-run-2 artifacts.
 * Ensures `tsc --noEmit` succeeds in clean CI checkouts prior to `fetch-build-data.mjs`.
 */
declare module "@/data/te-fleet-run-2/cards-v3/*.json" {
  const value: Record<string, unknown>;
  export default value;
}

declare module "@/data/te-fleet-run-2/scores/*.json" {
  const value: Record<string, unknown>;
  export default value;
}

declare module "@/data/te-fleet-run-2/countries/*.json" {
  const value: Record<string, unknown>;
  export default value;
}

declare module "@/data/te-fleet-run-2/analogs/*.json" {
  const value: Record<string, unknown>;
  export default value;
}

declare module "@/data/te-fleet-run-2/activity/*.json" {
  const value: Record<string, unknown>;
  export default value;
}

declare module "@/data/te-fleet-run-2/MANIFEST.json" {
  const value: Record<string, unknown>;
  export default value;
}
