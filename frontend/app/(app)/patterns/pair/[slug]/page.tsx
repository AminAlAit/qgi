/**
 * /patterns/pair/[slug] — DEPRECATED. Redirected to /patterns/[slug].
 *
 * 2026-05-30: The pair-overview view has been merged into the unified
 * /patterns/[slug] route. 2-segment ISO-2 slugs (e.g. "pl-cz") now dispatch
 * to the pair-overview view inside that route.
 *
 * The next.config.ts 301 redirect from /patterns/pair/:slug → /patterns/:slug
 * handles incoming requests before this page runs; this file is kept as a
 * safety fallback only.
 */
import { redirect } from "next/navigation";
import { notFound } from "next/navigation";

interface Params {
  params: Promise<{ slug: string }>;
}

export default async function PairPageRedirect({ params }: Params) {
  const { slug } = await params;
  if (!slug) notFound();
  redirect(`/patterns/${slug}`);
}
