import type { Metadata } from "next";
import { Geist, Geist_Mono, Jost } from "next/font/google";
import "./globals.css";
import { DevAdminButton } from "@/components/admin/DevAdminButton";
import { SessionProviderWrapper } from "@/components/auth/SessionProviderWrapper";

// T16 #309 LOW fix: declare `display: "swap"` so text is visible during
// webfont download instead of the default "block" FOIT period.
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

// Brand/logo font. Century Gothic is proprietary and cannot be web-embedded, so
// Jost — the standard free geometric look-alike — is the guaranteed delivery
// behind var(--font-qg-brand). The logo font stacks still prefer real Century
// Gothic wherever the OS has it installed, falling back to Jost otherwise.
const jostBrand = Jost({
  variable: "--font-qg-brand",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
});

/**
 * Root metadata (T19 #312).
 *
 * - `openGraph.images` + `twitter` added so social previews don't render
 *   blank. PNG lives at `public/og-default.png` (1200×630). Per-page
 *   routes override with more specific art when available.
 * - `robots` default-allowed. Per-route opt-outs happen in their own
 *   metadata.
 * - **NO `alternates.canonical` at root** — #699 regression fix (2026-05-15):
 *   the root canonical inherited to every child page that didn't explicitly
 *   override, so V3 routes (`/precedents`, `/countries`, etc.) all told
 *   Google "I am a duplicate of https://qgintelligence.com" — the exact
 *   bug PR-iii's V3 cutover was supposed to fix. Each route now declares
 *   its own canonical in its own metadata; the home page (`app/page.tsx`)
 *   declares `canonical: "/"` explicitly.
 */
// 2026-06-04: brand OG repositioned to the "evidence, not opinion" line
// (founder pick, "Option A"); trivia scope counts dropped from social/meta copy.
const OG_TITLE = "QG Intelligence · Geopolitics, measured";
const OG_DESCRIPTION =
  "Country risk read against the historical record, from public data and openly documented methods. Evidence, not opinion.";

export const metadata: Metadata = {
  metadataBase: new URL("https://qgintelligence.com"),
  title: "QGI · Quantitative Geopolitical Intelligence",
  description: OG_DESCRIPTION,
  openGraph: {
    title: OG_TITLE,
    description: OG_DESCRIPTION,
    url: "https://qgintelligence.com",
    siteName: "QG Intelligence",
    type: "website",
    // OG image resolved via file convention: app/opengraph-image.tsx
    // (edge-rendered via lib/og/OgFrame). Per-route overrides live under
    // app/<route>/opengraph-image.tsx where each high-share-value page
    // declares its own. Previously hardcoded to /og-default.png which
    // drifted out of date with the platform vocabulary (e.g. 58 indicators
    // / "economic data" framing). 2026-05-23.
  },
  twitter: {
    card: "summary_large_image",
    title: OG_TITLE,
    description: OG_DESCRIPTION,
    // Twitter falls back to the same file-based opengraph-image per
    // Next.js conventions when twitter.images is omitted.
  },
  robots: {
    index: true,
    follow: true,
  },
  // #433: apple-touch-icon + PWA manifest so iOS home-screen save uses
  // a real QGI-branded icon instead of a low-res auto-crop of the page.
  icons: {
    apple: "/apple-touch-icon.png",
    icon: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  },
  manifest: "/manifest.webmanifest",
};

// T19 #312: Organization schema helps Google understand QGI as an entity
// and enables knowledge-panel treatment. Injected as a <script> tag in
// the body so it's available site-wide.
const ORGANIZATION_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "QG Intelligence",
  alternateName: "Quantitative Geopolitical Intelligence",
  url: "https://qgintelligence.com",
  description:
    "QG Intelligence reads every country's trajectory against the historical record, from public data and openly documented methods. Evidence-based country risk, not opinion.",
  founder: { "@type": "Person", name: "Amin Al-Ait" },
  sameAs: ["https://www.linkedin.com/in/aminalait/"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${jostBrand.variable} h-full`}
      // The no-flash script below may add `class="light"` to <html> before React
      // hydrates (only for users who opted into light); suppress the resulting
      // attribute-mismatch warning. Dark-default users have no mismatch at all.
      suppressHydrationWarning
    >
      <head>
        {/* No-flash theme: runs synchronously before first paint. Dark is the
            default (:root); add `light` only when the user has opted in. Inline
            string (not a Script component) so it executes during HTML parse. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{if(localStorage.getItem('qgi-theme')==='light'){document.documentElement.classList.add('light');}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="h-full antialiased">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(ORGANIZATION_JSON_LD) }}
        />
        <SessionProviderWrapper>{children}</SessionProviderWrapper>
        <DevAdminButton />
      </body>
    </html>
  );
}
