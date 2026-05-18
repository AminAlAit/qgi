# live-pulse — hourly news-pulse nowcast

One bounded Lambda, fired hourly by EventBridge Scheduler, that turns the
**free** raw GDELT GKG feed into `dashboard/hf-pulse-live.json`. The
qgi-frontend reads that file at runtime (same S3 pattern as
`country-risks.json`) behind a staleness gate, so a stale or missing file
always degrades to the monthly board verdict.

The same run also writes `dashboard/hf-pulse-articles.json` — a rolling 24h,
per-country feed of the matched headlines (url, domain, tone, first topic) for
the Live Pulse terminal's news rail. It is best-effort: a failure there is
logged and never fails the pulse run. (The terminal's intraday charts are
rebuilt frontend-side straight from `hf-pulse-buckets.json`, so they need no
change here.)

Authorized by founder "I like it. Go." (2026-06-11). Chosen over GitHub
Actions because the free CI-minute pool is depleted by other repos and the
repos stay private; chosen over an always-on box because it must cost $0.

## Why it is free

- GDELT raw 15-min files are public HTTP — no API key, no BigQuery scan.
- Lambda compute is a few seconds/run: perpetual free tier (1M req +
  400k GB-s/mo). 24 runs/day at 512 MB for ~5 s is ~5% of the free GB-s.
- EventBridge Scheduler: 24 fires/day ≈ 0.005% of the free 14M/mo.
- Two small S3 objects. The `aws_budgets_budget` here is a $1/mo belt; the
  real expectation is $0.

## Data flow

```
GDELT lastupdate.txt ──► newest 15-min slot
            │
            ▼
  fetch ONLY uncached slots in the trailing 48h  ◄── hf-pulse-buckets.json
  (+ re-fetch the most recent 2h, which GDELT revises)      (rolling cache)
            │
            ▼
  roll trailing 24h ─► share = topic_docs / country_docs
            │
            ▼
  z-score vs cached 90-day daily-share μ/σ  ◄── hf-pulse-baseline.json
            │                                       (seeded once, read-only)
            ▼
  pulse = z_to_100(z)  (sparsity ⇒ null, never 0)
            │
            ▼
  hf-pulse-live.json ─► frontend runtime read (staleness gate)
```

## S3 keys (all under `dashboard/` in the data-lake bucket)

| Key | Owner | Purpose |
|-----|-------|---------|
| `hf-pulse-baseline.json` | seed script (founder, once) | 90-day daily-share μ/σ per `ISO3\|Txx`. Read-only to the Lambda. |
| `hf-pulse-buckets.json`  | the Lambda | rolling per-15-min count cache (trailing 48h). Makes fetches incremental — no file is bought twice. |
| `hf-pulse-live.json`     | the Lambda | the nowcast the frontend reads. |

## Convention divergence (intentional)

Other QGI Lambdas ship a placeholder zip and let qgi-pipeline CI deploy the
real code. This one packages its **real** handler via `archive_file`, so
`terraform apply` deploys working code with **zero GitHub minutes** — the
whole reason this track exists. The handler is stdlib + runtime boto3 only;
there is nothing to build. A code edit + `apply` is the deploy path (no
`lifecycle ignore_changes` on the source).

## Setup order

1. `terraform apply` (executed with authorized operator credentials).
2. Founder runs `qgi-gdelt-poc/seed_live_baseline.py --upload` **once** to
   write `hf-pulse-baseline.json`. Until then the Lambda writes a clean
   `status:"seeding"` marker and the frontend shows the monthly verdict.
3. The first few hourly runs warm `hf-pulse-buckets.json`; cells go live as
   the 24h window fills (~3-4 h on a cold cache, faster if the seed primed it).

## EventBridge Scheduler exception

The org keeps Scheduler `DISABLED` to guard expensive pipeline fan-outs
(the $37 / $139 incidents). This target is a single bounded free Lambda — a
different risk class — so it ships `ENABLED`. Founder ratified the exception
2026-06-11. Set `schedule_state = "DISABLED"` to stage without the clock.

## Tests

`python -m pytest modules/live-pulse/tests/ -v` — exercises the z mapping,
sparsity suppression, the incremental-fetch set math, and the
window-rollup, all without touching AWS or the network.
