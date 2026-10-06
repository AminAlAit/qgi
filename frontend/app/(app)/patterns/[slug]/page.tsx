/**
 * /patterns/[slug] — RETIRED (2026-06-05).
 *
 * Replaced by Analogues. A next.config redirect sends /patterns/* to /analogues
 * before this runs; this stub keeps the dynamic route valid (so existing links
 * and tour anchors resolve) without importing any cascade/SCDI pattern data, so
 * none of it is bundled into the deployed build. The pattern code stays in repo.
 */
import { redirect } from "next/navigation";

export default async function PatternDetailRetired() {
  redirect("/analogues");
}
