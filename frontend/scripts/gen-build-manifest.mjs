/**
 * gen-build-manifest.mjs — regenerate data/build-manifest.json by hashing the
 * LOCAL build-fetched vintage (default: te-fleet-run-2).
 *
 * The committed manifest is the build's source of truth: it PINS the exact S3
 * vintage and records every file's sha256 + byte size + count. The prebuild
 * fetch (scripts/fetch-build-data.mjs) downloads that vintage from S3 and
 * verifies it against this manifest, failing the build loudly on any drift,
 * truncation, or count mismatch. Bumping the live vintage is therefore a small,
 * reviewable manifest diff in a PR — never a 96MB JSON commit, never a silent
 * S3 change.
 *
 * Usage (run with the vintage present locally, e.g. right after a bake/sync):
 *   node scripts/gen-build-manifest.mjs            # te-fleet-run-2
 *   node scripts/gen-build-manifest.mjs te-fleet-run-3
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

const VINTAGE = process.argv[2] ?? "te-fleet-run-2";
const DEST_ROOT = `data/${VINTAGE}`;
const S3_PREFIX = `frontend-data/${VINTAGE}/`;

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

const root = join(process.cwd(), DEST_ROOT);
const files = walk(root)
  .map((abs) => {
    const rel = relative(root, abs).split(sep).join("/");
    const buf = readFileSync(abs);
    return {
      rel,
      bytes: buf.length,
      sha256: createHash("sha256").update(buf).digest("hex"),
    };
  })
  .sort((a, b) => a.rel.localeCompare(b.rel));

const manifest = {
  vintage: VINTAGE,
  s3_prefix: S3_PREFIX,
  dest_root: `${DEST_ROOT}/`,
  count: files.length,
  total_bytes: files.reduce((n, f) => n + f.bytes, 0),
  files,
};

writeFileSync(
  join(process.cwd(), "data/build-manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`
);
console.log(
  `build-manifest.json: vintage=${VINTAGE} files=${files.length} bytes=${manifest.total_bytes}`
);
