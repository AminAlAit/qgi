/**
 * Blog-post Article schema (#433).
 *
 * Server-rendered <script type="application/ld+json"> enabling rich SERP
 * cards (title + date + author + image) for each QGI blog post. Inlined
 * per-post via the Next.js layout convention rather than wrapped in a
 * Provider; blog posts are static + short + benefit from deterministic
 * SSR output.
 *
 * #734 (2026-05-16) — author defaults to **Organization (QG Intelligence)**
 * not Person. The previous default was a hard-coded Person attribution
 * for Amin Al-Ait, which leaked into the structured data Google + LLMs
 * scrape — particularly visible on the first pipeline-derived blog post
 * (Burkina Faso, #733). Personal-bylined pieces can still pass an
 * explicit `author={...}` override.
 *
 * 2026-05-24 — brand fix per #867: "QGI Intelligence" (double-I, wrong)
 * was shipping in the LIVE JSON-LD payload on every report. Corrected to
 * "QG Intelligence" (canonical brand, space). Affects Organization name
 * in both `author` default and `publisher`.
 */

export type ArticleAuthor =
  | {
      type: "Organization";
      name: string;
      url?: string;
    }
  | {
      type: "Person";
      name: string;
      url?: string;
    };

const DEFAULT_AUTHOR: ArticleAuthor = {
  type: "Organization",
  name: "QG Intelligence",
  url: "https://qgintelligence.com",
};

interface ArticleJsonLdProps {
  headline: string;
  description: string;
  url: string;
  datePublished: string; // ISO 8601
  imageUrl?: string; // absolute URL; falls back to /og-default.png
  /** Optional override for the structured-data author attribution.
   *  Default: Organization (QGI Intelligence). Pass a Person variant
   *  only for explicitly personally-bylined pieces. */
  author?: ArticleAuthor;
}

export function ArticleJsonLd({
  headline,
  description,
  url,
  datePublished,
  imageUrl,
  author = DEFAULT_AUTHOR,
}: ArticleJsonLdProps) {
  const authorPayload = {
    "@type": author.type,
    name: author.name,
    ...(author.url ? { url: author.url } : {}),
  };
  const payload = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline,
    description,
    url,
    datePublished,
    dateModified: datePublished,
    author: authorPayload,
    publisher: {
      "@type": "Organization",
      name: "QG Intelligence",
      url: "https://qgintelligence.com",
      logo: {
        "@type": "ImageObject",
        url: "https://qgintelligence.com/og-default.png",
      },
    },
    image: imageUrl ?? "https://qgintelligence.com/og-default.png",
    mainEntityOfPage: {
      "@type": "WebPage",
      "@id": url,
    },
  };
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(payload) }}
    />
  );
}
