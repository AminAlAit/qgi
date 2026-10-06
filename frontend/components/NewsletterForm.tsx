"use client";

/**
 * NewsletterForm — real email capture for the monthly digest.
 *
 * HISTORY
 * - Original: client-side fake form that threw submissions away.
 * - 2026-04-19 (#353): replaced with a mailto CTA (exposed the founder's
 *   address) while no backend existed.
 * - 2026-05-31: real form again. POSTs to /api/newsletter (Resend-backed),
 *   no address shown on the page. Graceful success / error states; never a
 *   fake success — a delivery failure shows a retry, not a thank-you.
 */
import { useState } from "react";

type Status = "idle" | "submitting" | "ok" | "error";

export default function NewsletterForm() {
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState(""); // honeypot
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (status === "submitting") return;
    setStatus("submitting");
    setMessage("");
    try {
      const res = await fetch("/api/newsletter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, company }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (res.ok) {
        setStatus("ok");
        setEmail("");
      } else {
        setStatus("error");
        setMessage(data.error || "Something went wrong. Please try again shortly.");
      }
    } catch {
      setStatus("error");
      setMessage("Could not reach the server. Please try again shortly.");
    }
  }

  if (status === "ok") {
    return (
      <div className="w-full max-w-md">
        <p className="text-sm" style={{ color: "var(--qgi-accent)" }}>
          You&rsquo;re on the list. We&rsquo;ll be in touch with the next digest.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-md" noValidate>
      <div className="flex flex-col sm:flex-row gap-2">
        <label htmlFor="newsletter-email" className="sr-only">
          Email address
        </label>
        <input
          id="newsletter-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="flex-1 px-4 py-2.5 rounded text-sm outline-none transition-colors focus:border-[var(--qgi-accent)]"
          style={{
            backgroundColor: "var(--qgi-bg)",
            border: "1px solid var(--qgi-border)",
            color: "var(--qgi-text)",
          }}
        />
        {/* Honeypot: visually hidden, off the tab order. Bots fill it. */}
        <input
          type="text"
          name="company"
          tabIndex={-1}
          autoComplete="off"
          aria-hidden="true"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          style={{
            position: "absolute",
            left: "-9999px",
            width: 1,
            height: 1,
            opacity: 0,
          }}
        />
        <button
          type="submit"
          disabled={status === "submitting"}
          className="px-5 py-2.5 rounded text-sm font-medium tracking-wide transition-all hover:brightness-110 disabled:opacity-60"
          style={{ backgroundColor: "var(--qgi-accent)", color: "var(--qgi-bg)" }}
        >
          {status === "submitting" ? "Joining…" : "Join the list"}
        </button>
      </div>
      {status === "error" && (
        <p className="text-xs mt-2" style={{ color: "#E06C6C" }} role="alert">
          {message}
        </p>
      )}
    </form>
  );
}
