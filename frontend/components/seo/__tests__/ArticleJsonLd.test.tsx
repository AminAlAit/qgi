/**
 * #734 (2026-05-16) — verify ArticleJsonLd defaults to institutional
 * author (Organization: QG Intelligence), with personal-byline override
 * available.
 *
 * Prior default was a hard-coded Person attribution for Amin Al-Ait. This
 * test pins the new contract so the Burkina Faso piece + future pipeline-
 * derived content land with institutional structured-data attribution
 * (important for LLMs + Google rich cards).
 */
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ArticleJsonLd } from "@/components/seo/ArticleJsonLd";

function extractPayload(markup: string): Record<string, unknown> {
  const match = markup.match(/<script[^>]*>([\s\S]*?)<\/script>/);
  if (!match) throw new Error("ArticleJsonLd did not render a <script> tag");
  return JSON.parse(match[1]) as Record<string, unknown>;
}

describe("ArticleJsonLd author attribution (#734)", () => {
  const baseProps = {
    headline: "Test headline",
    description: "Test description",
    url: "https://qgintelligence.com/blog/test",
    datePublished: "2026-05-16T00:00:00Z",
  };

  it("defaults to Organization author (QG Intelligence)", () => {
    const markup = renderToStaticMarkup(<ArticleJsonLd {...baseProps} />);
    const payload = extractPayload(markup);
    const author = payload.author as Record<string, string>;
    expect(author["@type"]).toBe("Organization");
    expect(author.name).toBe("QG Intelligence");
    expect(author.url).toBe("https://qgintelligence.com");
  });

  it("never renders Person author by default (regression guard)", () => {
    const markup = renderToStaticMarkup(<ArticleJsonLd {...baseProps} />);
    expect(markup).not.toContain('"@type":"Person"');
    expect(markup).not.toContain("Amin Al-Ait");
  });

  it("accepts an explicit Person override for personally-bylined pieces", () => {
    const markup = renderToStaticMarkup(
      <ArticleJsonLd
        {...baseProps}
        author={{
          type: "Person",
          name: "Test Author",
          url: "https://qgintelligence.com/about",
        }}
      />
    );
    const payload = extractPayload(markup);
    const author = payload.author as Record<string, string>;
    expect(author["@type"]).toBe("Person");
    expect(author.name).toBe("Test Author");
    expect(author.url).toBe("https://qgintelligence.com/about");
  });

  it("publisher remains Organization regardless of author override", () => {
    const markup = renderToStaticMarkup(
      <ArticleJsonLd {...baseProps} author={{ type: "Person", name: "Test Author" }} />
    );
    const payload = extractPayload(markup);
    const publisher = payload.publisher as Record<string, string>;
    expect(publisher["@type"]).toBe("Organization");
    expect(publisher.name).toBe("QG Intelligence");
  });

  it("emits valid JSON-LD shape", () => {
    const markup = renderToStaticMarkup(<ArticleJsonLd {...baseProps} />);
    const payload = extractPayload(markup);
    expect(payload["@context"]).toBe("https://schema.org");
    expect(payload["@type"]).toBe("Article");
    expect(payload.headline).toBe(baseProps.headline);
    expect(payload.url).toBe(baseProps.url);
  });
});
