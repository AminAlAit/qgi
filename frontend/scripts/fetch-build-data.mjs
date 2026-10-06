/**
 * fetch-build-data.mjs — PREBUILD step. Download the pinned fleet vintage from
 * S3 into data/ before `next build`, so the heavy machine-generated data lives
 * in S3 (the source of truth) instead of git.
 *
 * Contract (data/build-manifest.json): the manifest PINS one vintage prefix and
 * lists every file's sha256 + byte size + an exact count. This script fetches
 * exactly those keys and verifies each against the manifest. ANY drift —
 * missing file, wrong size, checksum mismatch, count off by one — FAILS the
 * build loudly (exit 1). `next build` never runs on partial/corrupt data, so a
 * truncated fetch can never ship empty pages to the public site.
 *
 * Credentials:
 *   - On Vercel (build): VERCEL_OIDC_TOKEN is present → assume the dedicated
 *     build role (AWS_BUILD_ROLE_ARN, falling back to AWS_ROLE_ARN) via
 *     @vercel/oidc-aws-credentials-provider. No static keys.
 *   - Locally: no VERCEL_OIDC_TOKEN → the default AWS SDK credential chain
 *     (~/.aws, env vars, SSO). If the files are already present and valid
 *     (e.g. a fresh checkout that still has them, or a prior fetch), every file
 *     is skipped by checksum and the script makes zero S3 calls — local/offline
 *     builds keep working.
 *
 * Function-size note: this changes ONLY where the files come from (S3 vs git).
 * The import statements are unchanged, so `next build` output is byte-identical
 * and serverless function bundles are unaffected (those stay governed by
 * next.config.ts `outputFileTracingExcludes`).
 */
import { createHash } from "node:crypto";
import { readFile, writeFile, rename, mkdir, stat } from "node:fs/promises";
import { dirname, join } from "node:path";

const ROOT = process.cwd();
const MANIFEST_PATH = join(ROOT, "data", "build-manifest.json");
const BUCKET = process.env.QGI_DATA_LAKE_BUCKET ?? "qgi-data-lake-771606957899";
const REGION = process.env.AWS_REGION ?? "eu-central-1";
const CONCURRENCY = 12;
const MAX_ATTEMPTS = 3;

function sha256(buf) {
  return createHash("sha256").update(buf).digest("hex");
}

async function fileMatches(dest, expected) {
  try {
    const st = await stat(dest);
    if (st.size !== expected.bytes) return false;
    const buf = await readFile(dest);
    return sha256(buf) === expected.sha256;
  } catch {
    return false;
  }
}

/** Resolve credentials: OIDC build role on Vercel, default chain locally. */
async function resolveCredentials() {
  if (!process.env.VERCEL_OIDC_TOKEN) {
    console.log(
      "[fetch-build-data] no VERCEL_OIDC_TOKEN — using default AWS credential chain (local)."
    );
    return undefined; // let the SDK use its default chain
  }
  const roleArn = process.env.AWS_BUILD_ROLE_ARN || process.env.AWS_ROLE_ARN;
  if (!roleArn) {
    throw new Error(
      "VERCEL_OIDC_TOKEN is set but neither AWS_BUILD_ROLE_ARN nor AWS_ROLE_ARN is — cannot assume a role to fetch build data."
    );
  }
  const { awsCredentialsProvider } =
    await import("@vercel/oidc-aws-credentials-provider");
  console.log(`[fetch-build-data] assuming build role via Vercel OIDC: ${roleArn}`);
  return awsCredentialsProvider({ roleArn });
}

// Lazy, memoized S3 client. Credentials are resolved (and the client built)
// ONLY when a file actually needs downloading — so a build where every file is
// already present (the no-op path, e.g. while the data is still committed)
// makes zero S3 calls and requires no role/env at all. Memoizing the PROMISE
// keeps concurrent workers from double-initializing.
let _s3Promise;
function getS3() {
  if (!_s3Promise) {
    _s3Promise = (async () => {
      const credentials = await resolveCredentials();
      const { S3Client, GetObjectCommand } = await import("@aws-sdk/client-s3");
      const client = new S3Client({
        region: REGION,
        ...(credentials ? { credentials } : {}),
      });
      return { client, GetObjectCommand };
    })();
  }
  return _s3Promise;
}

async function getObjectBuffer(key) {
  const { client, GetObjectCommand } = await getS3();
  const resp = await client.send(new GetObjectCommand({ Bucket: BUCKET, Key: key }));
  const chunks = [];
  for await (const chunk of resp.Body) chunks.push(chunk);
  return Buffer.concat(chunks);
}

/** Download one manifest entry with verification + retries + atomic write. */
async function fetchOne(m, entry) {
  const dest = join(ROOT, m.dest_root, entry.rel);
  // Guard: a malformed/hostile manifest 'rel' must not escape the vintage dir.
  if (!dest.startsWith(join(ROOT, m.dest_root))) {
    throw new Error(`manifest rel escapes dest_root: ${entry.rel}`);
  }
  if (await fileMatches(dest, entry)) return "skip";

  const key = m.s3_prefix + entry.rel;
  let lastErr;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const buf = await getObjectBuffer(key);
      if (buf.length !== entry.bytes) {
        throw new Error(
          `size mismatch for ${key}: got ${buf.length}, expected ${entry.bytes}`
        );
      }
      const got = sha256(buf);
      if (got !== entry.sha256) {
        throw new Error(
          `checksum mismatch for ${key}: got ${got}, expected ${entry.sha256}`
        );
      }
      await mkdir(dirname(dest), { recursive: true });
      // Deterministic temp suffix (key+attempt): each key is owned by one worker
      // so in-flight names never collide; a leftover from a crashed run is just
      // overwritten, and rename-over-existing is atomic on the build's fs.
      const tmp = `${dest}.tmp-${createHash("sha1").update(`${key}:${attempt}`).digest("hex").slice(0, 12)}`;
      await writeFile(tmp, buf);
      await rename(tmp, dest); // atomic on the same filesystem
      return "fetch";
    } catch (err) {
      lastErr = err;
      if (attempt < MAX_ATTEMPTS) {
        await new Promise((r) => setTimeout(r, 500 * 2 ** (attempt - 1)));
      }
    }
  }
  throw new Error(
    `failed after ${MAX_ATTEMPTS} attempts: ${lastErr?.message ?? lastErr}`
  );
}

async function main() {
  const manifest = JSON.parse(await readFile(MANIFEST_PATH, "utf-8"));
  const { vintage, s3_prefix, dest_root, count, files } = manifest;
  if (!vintage || !s3_prefix || !dest_root || !Array.isArray(files)) {
    throw new Error(
      "build-manifest.json is malformed (missing vintage/s3_prefix/dest_root/files)."
    );
  }
  if (files.length !== count) {
    throw new Error(
      `manifest self-inconsistent: count=${count} but files.length=${files.length}.`
    );
  }
  console.log(`[fetch-build-data] vintage=${vintage} files=${count} bucket=${BUCKET}`);

  let fetched = 0;
  let skipped = 0;
  const queue = [...files];
  async function worker() {
    for (;;) {
      const entry = queue.shift();
      if (!entry) return;
      const r = await fetchOne(manifest, entry);
      if (r === "skip") skipped++;
      else fetched++;
      const done = fetched + skipped;
      if (done % 20 === 0 || done === count) {
        console.log(
          `[fetch-build-data] ${done}/${count} (fetched ${fetched}, skipped ${skipped})`
        );
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, files.length) }, worker));

  // Final gate: exact count, no silent shortfall.
  const total = fetched + skipped;
  if (total !== count) {
    throw new Error(`vintage incomplete: resolved ${total}/${count} files.`);
  }
  console.log(
    `[fetch-build-data] OK — ${vintage}: ${fetched} fetched, ${skipped} verified-present, ${count} total.`
  );
}

main().catch((err) => {
  console.error(`[fetch-build-data] FAILED: ${err?.message ?? err}`);
  console.error(
    "[fetch-build-data] Build aborted — refusing to build on partial/corrupt vintage data."
  );
  process.exit(1);
});
