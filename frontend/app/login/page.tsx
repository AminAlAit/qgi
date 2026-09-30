import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { LoginForm } from "@/components/auth/LoginForm";

/**
 * Login page. "Continue with Google" (live) + native email/password
 * (via the NextAuth Credentials provider → Cognito, live once the pool is
 * applied). Replaces the #429 "coming soon" stub as part of the #448 auth work.
 * noindex.
 */
export const metadata: Metadata = {
  title: "Sign in · QG Intelligence",
  description: "Sign in to QG Intelligence.",
  robots: { index: false, follow: false },
};

export default function LoginPage() {
  return (
    <div
      className="min-h-full flex items-center justify-center p-6"
      style={{ backgroundColor: "var(--qgi-bg)" }}
    >
      <div
        className="w-full max-w-md rounded-lg border p-8 flex flex-col items-center"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        {/* Logo */}
        <div className="text-center mb-6">
          <span
            className="font-data text-lg tracking-[0.25em] font-semibold"
            style={{ color: "var(--qgi-accent)" }}
          >
            QGI
          </span>
          <p
            className="mt-2 text-xs tracking-wider uppercase"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            Quantitative Geopolitical Intelligence
          </p>
        </div>

        <h1 className="text-lg font-semibold mb-6" style={{ color: "var(--qgi-text)" }}>
          Sign in
        </h1>

        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>

        <div className="mt-6 text-center">
          <Link
            href="/"
            className="text-xs transition-colors hover:text-[var(--qgi-accent)]"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            &larr; Back to home
          </Link>
        </div>
      </div>
    </div>
  );
}
