import type { Metadata } from "next";
import Link from "next/link";
import { PublicNav } from "@/components/PublicNav";
import { PublicFooter } from "@/components/PublicFooter";
import { SkipLink } from "@/components/SkipLink";
import ContactForm from "@/components/ContactForm";
import { Wordmark } from "@/components/brand/Wordmark";

export const metadata: Metadata = {
  title: "Contact · QG Intelligence",
  description:
    "Get in touch with the QG Intelligence team: questions about the methodology, the data, access, or partnerships.",
  alternates: { canonical: "https://qgintelligence.com/contact" },
};

export default function ContactPage() {
  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <SkipLink />

      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="nav" href="/" title="Home" />
          <PublicNav />
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="focus:outline-none">
        <section className="mx-auto max-w-2xl px-6 pt-20 pb-24">
          <h1
            className="text-3xl font-semibold mb-3"
            style={{ color: "var(--qgi-text)" }}
          >
            Contact
          </h1>
          <p
            className="text-base leading-relaxed mb-10"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            Questions about the methodology, the data, access, or a partnership? Send us a
            note and we&rsquo;ll get back to you.
          </p>
          <ContactForm />
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
