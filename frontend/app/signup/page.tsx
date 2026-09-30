import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { SignupForm } from "@/components/auth/SignupForm";

export const metadata: Metadata = {
  title: "Create account · QG Intelligence",
  description: "Create a QG Intelligence account.",
  robots: { index: false, follow: false },
};

export default function SignupPage() {
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
          Create your account
        </h1>

        <Suspense fallback={null}>
          <SignupForm />
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
