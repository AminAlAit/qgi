/**
 * /patterns — RETIRED (2026-06-05).
 *
 * The pattern catalogue is replaced by Analogues. A next.config redirect sends
 * every /patterns* URL to /analogues before this runs; this stub keeps the route
 * valid (so existing /patterns links and the tour still resolve) and, crucially,
 * imports none of the cascade/SCDI pattern data (ranking, partners index, etc.),
 * so that data is no longer bundled into the deployed build. The pattern/SCDI
 * code remains in the repo.
 */
import { redirect } from "next/navigation";

export default function PatternsRetired() {
  redirect("/analogues");
}
