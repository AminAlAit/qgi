# TODO: Playwright specs for #464 route restructure

The mock-data scaffold landed in week 2 (#464); deferred from this PR.
When real data wires up in week 3 (#463 country-vs-recipe scoring), add
Tier-1 Playwright specs for these new URLs:

## New routes that need spec coverage

| URL                         | Spec                             | Asserts                                                                                                                                    |
| --------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `/precedents`               | `precedents-index.spec.ts`       | 200, lists ≥5 recipe rows, sorted by `total_instances` desc                                                                                |
| `/precedents/[slug]`        | `precedents-slug.spec.ts`        | 200 for a known slug (e.g. `civil_war_and_insurgency`); 404 for an invalid slug; renders canonical_length + indicator_fingerprint sections |
| `/signals/[country]`        | `signals-country.spec.ts`        | 200 for a known slug (e.g. `yemen`); 404 for `not-a-country`; lists ≥1 signal row sorted by score desc                                     |
| `/signals/[country]/[slug]` | `signals-country-recipe.spec.ts` | 200 for a known (country, slug) pair; 404 for invalid slug; renders the similarity score + Recipe context card                             |

## Existing route to update

`country-slug-routing.spec.ts` — assert that `/countries/[id]/[category]`
returns a 308/301 redirect to `/signals/{slug}/{category}` (Next.js
`redirect()` defaults to 308 Permanent Redirect, which is the V2.0 spec).

## Reference

Ticket: <https://github.com/AminAlAit/qgi-aws-tf/issues/464>
Companion ticket (real data): <https://github.com/AminAlAit/qgi-aws-tf/issues/463>
