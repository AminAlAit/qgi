/**
 * robots.txt route (T19 #312).
 *
 * Allows search engines to crawl public content. Disallows:
 *   - /login (auth page, not useful to index)
 *   - /api/  (protected + cost-sensitive)
 *
 * 2026-05-28 (V4.1 canonical promotion): All legacy V1/V2/V3 routes are
 * deleted. No superseded routes to Disallow. The 9 canonical V4.1 surfaces
 * are the only app routes now.
 */
import type { MetadataRoute } from "next";

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://qgintelligence.com";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/login", "/api/"],
      },
    ],
    sitemap: `${BASE_URL}/sitemap.xml`,
    host: BASE_URL,
  };
}
