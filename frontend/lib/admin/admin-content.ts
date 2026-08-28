/**
 * Admin dashboard — async / sibling-repo REAL-data accessors (server-only).
 *
 *  - Curation progress: counts entries in data/curation/what-happened-next.json
 *  - X content queue:   parses the X engine outbox in the sibling docs-specs repo
 *    (manifest.json per batch + post-log.jsonl). LOCALHOST-ONLY — the outbox is
 *    gitignored and not present in a Vercel build, so these gracefully degrade
 *    to a `present: false` flag rather than throwing.
 *
 * No mocks: if a source isn't on disk we say so (present=false), never invent.
 */
import "server-only";
import { promises as fs } from "fs";
import path from "path";

const CURATION_TOTAL = 3440; // size of the analog pool to curate (charter target)

export interface CurationProgress {
  present: boolean;
  done: number;
  total: number;
  pct: number;
}

export async function getCurationProgress(): Promise<CurationProgress> {
  try {
    const p = path.join(process.cwd(), "data", "curation", "what-happened-next.json");
    const raw = await fs.readFile(p, "utf-8");
    const obj = JSON.parse(raw) as Record<string, unknown>;
    const done = Object.keys(obj).length;
    return {
      present: true,
      done,
      total: CURATION_TOTAL,
      pct: (done / CURATION_TOTAL) * 100,
    };
  } catch {
    return { present: false, done: 0, total: CURATION_TOTAL, pct: 0 };
  }
}

export interface XPost {
  idx: number;
  type: string;
  slug: string;
  status: string;
}
export interface XBatch {
  batch: string;
  approved: boolean;
  built: number;
  pending: number;
  posted: number;
  items: XPost[];
}
export interface XQueue {
  present: boolean;
  built: number; // total posts authored across all batches
  approved: number; // in approved batches, not yet sent
  pending: number; // not-yet-sent posts (any batch)
  postedTotal: number;
  postedThisWeek: number;
  lastPostAt: string | null;
  batches: XBatch[];
}

const OUTBOX = path.join(
  process.cwd(),
  "..",
  "docs-specs",
  "internal",
  "outreach",
  "twitter-x",
  "engine",
  "outbox"
);

export async function getXQueue(): Promise<XQueue> {
  const empty: XQueue = {
    present: false,
    built: 0,
    approved: 0,
    pending: 0,
    postedTotal: 0,
    postedThisWeek: 0,
    lastPostAt: null,
    batches: [],
  };
  let dirs: string[];
  try {
    const ents = await fs.readdir(OUTBOX, { withFileTypes: true });
    dirs = ents.filter((e) => e.isDirectory()).map((e) => e.name);
  } catch {
    return empty;
  }

  const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const q: XQueue = { ...empty, present: true, batches: [] };
  let lastPost = 0;

  for (const dir of dirs.sort()) {
    const base = path.join(OUTBOX, dir);
    // manifest
    let approved = false;
    let posts: Array<{
      idx?: number;
      type?: string;
      text_file?: string;
      image_file?: string;
      status?: string;
    }> = [];
    try {
      const m = JSON.parse(await fs.readFile(path.join(base, "manifest.json"), "utf-8"));
      approved = m.approved === true;
      posts = Array.isArray(m.posts) ? m.posts : [];
    } catch {
      // no manifest — staging batch (png/txt only); skip counting
      continue;
    }
    // post-log
    let postedInBatch = 0;
    try {
      const log = await fs.readFile(path.join(base, "post-log.jsonl"), "utf-8");
      for (const line of log.split("\n")) {
        const t = line.trim();
        if (!t) continue;
        try {
          const rec = JSON.parse(t);
          if (rec.result === "sent" || rec.tweet_id) {
            postedInBatch++;
            const ts = rec.at ? Date.parse(rec.at) : NaN;
            if (!Number.isNaN(ts)) {
              if (ts > lastPost) lastPost = ts;
              if (ts >= weekAgo) q.postedThisWeek++;
            }
          }
        } catch {
          /* skip bad line */
        }
      }
    } catch {
      /* no log = nothing posted yet */
    }

    const built = posts.length;
    const pending = Math.max(0, built - postedInBatch);
    q.built += built;
    q.postedTotal += postedInBatch;
    q.pending += pending;
    if (approved) q.approved += pending;
    const items: XPost[] = posts.map((p, i) => ({
      idx: p.idx ?? i,
      type: p.type ?? "post",
      slug:
        (p.text_file ?? p.image_file ?? "")
          .replace(/^.*[\\/]/, "")
          .replace(/\.[^.]+$/, "") || `item ${i + 1}`,
      status: p.status ?? "pending",
    }));
    q.batches.push({
      batch: dir,
      approved,
      built,
      pending,
      posted: postedInBatch,
      items,
    });
  }

  q.lastPostAt = lastPost ? new Date(lastPost).toISOString() : null;
  return q;
}
