import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

export const metadata: Metadata = {
  title: "Reset password · QG Intelligence",
  description: "Reset your QG Intelligence password.",
  robots: { index: false, follow: false },
};

export default function ForgotPasswordPage() {
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
        </div>

        <h1 className="text-lg font-semibold mb-2" style={{ color: "var(--qgi-text)" }}>
          Reset password
        </h1>
        <p
          className="text-xs mb-6 text-center"
          style={{ color: "var(--qgi-text-muted)", maxWidth: "300px" }}
        >
          Enter your email and we&apos;ll send a code to reset your password.
        </p>

        <Suspense fallback={null}>
          <ForgotPasswordForm />
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
