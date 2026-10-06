"use client";

/**
 * ContactForm — the fill-in form behind every "Contact" link.
 *
 * POSTs name / email / message to /api/contact (Resend-backed), with the
 * sender's address set as reply-to. No mailto, no address shown on the page.
 * Graceful success / error states; never a fake success.
 */
import { useState } from "react";

type Status = "idle" | "submitting" | "ok" | "error";

export default function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [company, setCompany] = useState(""); // honeypot
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (status === "submitting") return;
    setStatus("submitting");
    setError("");
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, message: msg, company }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (res.ok) {
        setStatus("ok");
      } else {
        setStatus("error");
        setError(data.error || "Something went wrong. Please try again shortly.");
      }
    } catch {
      setStatus("error");
      setError("Could not reach the server. Please try again shortly.");
    }
  }

  if (status === "ok") {
    return (
      <div
        className="rounded-lg border p-6"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <p className="text-base font-medium mb-1" style={{ color: "var(--qgi-accent)" }}>
          Message sent.
        </p>
        <p className="text-sm" style={{ color: "var(--qgi-text-muted)" }}>
          Thanks for reaching out. We&rsquo;ll reply to {email || "your address"} soon.
        </p>
      </div>
    );
  }

  const fieldStyle = {
    backgroundColor: "var(--qgi-bg)",
    border: "1px solid var(--qgi-border)",
    color: "var(--qgi-text)",
  } as const;

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <div>
        <label
          htmlFor="contact-name"
          className="block text-xs tracking-wider uppercase mb-2"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Name
        </label>
        <input
          id="contact-name"
          type="text"
          required
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full px-4 py-2.5 rounded text-sm outline-none transition-colors focus:border-[var(--qgi-accent)]"
          style={fieldStyle}
        />
      </div>
      <div>
        <label
          htmlFor="contact-email"
          className="block text-xs tracking-wider uppercase mb-2"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Email
        </label>
        <input
          id="contact-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="w-full px-4 py-2.5 rounded text-sm outline-none transition-colors focus:border-[var(--qgi-accent)]"
          style={fieldStyle}
        />
      </div>
      <div>
        <label
          htmlFor="contact-message"
          className="block text-xs tracking-wider uppercase mb-2"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Message
        </label>
        <textarea
          id="contact-message"
          required
          rows={6}
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="How can we help?"
          className="w-full px-4 py-2.5 rounded text-sm outline-none transition-colors focus:border-[var(--qgi-accent)] resize-y"
          style={fieldStyle}
        />
      </div>
      {/* Honeypot */}
      <input
        type="text"
        name="company"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        value={company}
        onChange={(e) => setCompany(e.target.value)}
        style={{ position: "absolute", left: "-9999px", width: 1, height: 1, opacity: 0 }}
      />
      {status === "error" && (
        <p className="text-sm" style={{ color: "#E06C6C" }} role="alert">
          {error}
        </p>
      )}
      <div className="flex items-center gap-4">
        <button
          type="submit"
          disabled={status === "submitting"}
          className="px-6 py-3 rounded text-sm font-medium tracking-wide transition-all hover:brightness-110 disabled:opacity-60"
          style={{ backgroundColor: "var(--qgi-accent)", color: "var(--qgi-bg)" }}
        >
          {status === "submitting" ? "Sending…" : "Send message"}
        </button>
      </div>
    </form>
  );
}
