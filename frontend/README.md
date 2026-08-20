# qgi-frontend

Next.js 16 / React 19 / TypeScript app for **QG Intelligence** (Quantitative Geopolitical Intelligence). Live at **[qgintelligence.com](https://qgintelligence.com)**, deployed on Vercel (auto-deploy on push to `main`).

## Run locally

```bash
npm install
npm run dev
# → http://localhost:3000
```

## Required environment

| Variable               | Default                      | Purpose                                        |
| ---------------------- | ---------------------------- | ---------------------------------------------- |
| `SKIP_AUTH`            | `true`                       | Bypass NextAuth in dev (pre-paywall posture)   |
| `AWS_REGION`           | `eu-central-1`               | Athena + DynamoDB region for live data loaders |
| `QGI_DATA_LAKE_BUCKET` | `qgi-data-lake-771606957899` | Staging data lake S3 bucket                    |

Optional (set in `.env.local` if you need them):

- `ATHENA_WORKGROUP` (default `QGI-Lambda-Workgroup`)
- `ATHENA_OUTPUT_LOCATION` (default `s3://${BUCKET}/query_results/`)

## Where things live

- `app/` — Next.js App Router routes
  - `app/(app)/...` — auth-gated app shell (dashboard, countries, signals, patterns, precedents)
  - `app/about/`, `app/methodology/`, `app/reports/`, `app/blog/`, `app/legal/` — public marketing pages
- `components/` — shared UI (PublicNav, PublicFooter, SkipLink, charts, SEO)
- `lib/` — data loaders, types, business logic
- `data/` — baked JSON consumed at build/SSR (country-risks, ranking, taxonomy)
- `public/` — static assets

## Conventions

- **Single source of truth for counts**: `lib/site-stats.ts` (`TOTAL_COUNTRIES`, `TOTAL_INDICATORS`, `TOTAL_LOCKED`, etc.). Never hardcode counts elsewhere.
- **Brand**: "QG Intelligence" (with space). "QGI" alone is fine as acronym.
- **No em-dashes** in user-facing prose. Hyphens / commas / colons only.
- **Reversibility pattern**: page redesigns back up the old page to `_classic-backup/page.tsx` (Next.js ignores `_`-prefixed dirs).
- **Tests**: vitest. Run `npx vitest run` before commit (also enforced via pre-push hook).

## Full architecture

See [`docs/specs/architecture/frontend.md`](https://github.com/AminAlAit/docs/specs/blob/main/architecture/frontend.md).
