/**
 * hf/live-pulse — runtime loader + staleness gate for the hourly news pulse.
 *
 * The live-pulse Lambda (qgi-infra/modules/live-pulse) writes
 * dashboard/hf-pulse-live.json every hour from the raw GDELT feed. This
 * module reads it at request time (same S3 pattern as country-risks.ts) and
 * grades it on freshness (gradeLive, in live-pulse-core) so the UI NEVER
 * shows a dead clock as "live":
 *
 *   live    generated_at <= staleAfterHours (default 2h)  -> "Live"
 *   recent  generated_at <= 26h                            -> "Last updated Xh ago"
 *   paused  generated_at  > 26h                            -> "Pulse paused", monthly fallback
 *   absent  no file / unreadable / status != live          -> monthly only (today's default)
 *
 * Until the founder applies the Terraform and runs seed_live_baseline.py,
 * the file is absent and every surface renders exactly as it does today.
 * This loader can only ADD a fresher reading; it can never break the
 * monthly fallback.
 *
 * The pure grading / verdict / overlay logic lives in live-pulse-core.ts so
 * it stays unit-testable without this module's server-only + AWS imports.
 */
import "server-only";

import {
  ABSENT,
  gradeLive,
  type LivePulse,
  type LiveStamp,
  type RawLive,
} from "@/lib/hf/live-pulse-core";

export type { LiveStatus, LivePulse, LiveStamp } from "@/lib/hf/live-pulse-core";
// NOTE: the pure functions (gradeLive / verdictFor / overlayCells) are NOT
// re-exported here on purpose — import them from "@/lib/hf/live-pulse-core" so
// callers never drag this module's `server-only` guard into a client bundle.

const BUCKET = process.env.QGI_DATA_LAKE_BUCKET ?? "qgi-data-lake-771606957899";
const REGION = process.env.AWS_REGION ?? "eu-central-1";
const S3_KEY = "dashboard/hf-pulse-live.json";

let _cache: LivePulse | null = null;
let _cacheTs = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 min: the file changes hourly
// Absent gets a much shorter TTL so a TRANSIENT S3 error (throttle, blip)
// can't pin the stamp to "missing" for 5 minutes after S3 recovers. A genuine
// absence (poller not deployed yet) just re-checks cheaply every 30s.
const ABSENT_TTL = 30 * 1000;

/** Read + grade the live file. Never throws; any failure -> absent. */
export async function getLivePulse(nowMs: number = Date.now()): Promise<LivePulse> {
  if (_cache) {
    const ttl = _cache.status === "absent" ? ABSENT_TTL : CACHE_TTL;
    if (nowMs - _cacheTs < ttl) return _cache;
  }

  // S3 is the source of truth for live data (a committed local file would be
  // stale by construction). A local override is honored only for dev.
  try {
    const { S3Client, GetObjectCommand } = await import("@aws-sdk/client-s3");
    // On Vercel (AWS_ROLE_ARN set) read via OIDC federation — a short-lived
    // assumed-role token, no stored AWS key. Locally / at build time there is
    // no OIDC token, so fall back to the default credential chain; a failure
    // there just yields `absent` (the monthly fallback), never a crash.
    const roleArn = process.env.AWS_ROLE_ARN;
    const credentials = roleArn
      ? (await import("@vercel/oidc-aws-credentials-provider")).awsCredentialsProvider({
          roleArn,
        })
      : undefined;
    const s3 = new S3Client({ region: REGION, ...(credentials ? { credentials } : {}) });
    const resp = await s3.send(new GetObjectCommand({ Bucket: BUCKET, Key: S3_KEY }));
    const body = await resp.Body?.transformToString();
    if (body) {
      _cache = gradeLive(JSON.parse(body) as RawLive, "s3", nowMs);
      _cacheTs = nowMs;
      return _cache;
    }
  } catch {
    // S3 miss / no creds / not yet applied — fall through.
  }

  try {
    const fs = await import("fs/promises");
    const path = await import("path");
    const raw = await fs.readFile(
      path.join(process.cwd(), "data", "hf-pulse-live.json"),
      "utf-8"
    );
    _cache = gradeLive(JSON.parse(raw) as RawLive, "local", nowMs);
    _cacheTs = nowMs;
    return _cache;
  } catch {
    // No live data anywhere -> absent (monthly fallback). This is the
    // expected state until the poller is live.
  }

  _cache = { ...ABSENT };
  _cacheTs = nowMs;
  return _cache;
}

/** Load live + grade, returning a serializable stamp descriptor for clients. */
export async function getLiveStamp(): Promise<LiveStamp> {
  const live = await getLivePulse();
  return { status: live.status, ageMinutes: live.ageMinutes, vintage: live.vintage };
}
