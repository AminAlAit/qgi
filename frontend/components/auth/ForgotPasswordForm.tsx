"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import { AuthField, AuthSubmit, AuthError } from "@/components/auth/AuthField";
import { safeCallbackUrl } from "@/lib/safe-callback";
import { forgotPasswordAction, confirmForgotPasswordAction } from "@/lib/auth-actions";

type Step = "request" | "reset";

export function ForgotPasswordForm() {
  const params = useSearchParams();
  const callbackUrl = safeCallbackUrl(params.get("callbackUrl"));
  const [step, setStep] = useState<Step>("request");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onRequest(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return; // guard against double-submit
    setError(null);
    setLoading(true);
    const res = await forgotPasswordAction(email);
    setLoading(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    setStep("reset");
    setNotice(`If an account exists for ${email}, a reset code is on its way.`);
  }

  async function onReset(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return; // guard against double-submit
    setError(null);
    if (password !== confirmPw) {
      setError("Passwords don't match.");
      return;
    }
    // Mirror the Cognito pool policy client-side (same as sign-up).
    if (
      password.length < 10 ||
      !/[a-z]/.test(password) ||
      !/[A-Z]/.test(password) ||
      !/\d/.test(password)
    ) {
      setError(
        "Password must be at least 10 characters and include an uppercase letter, a lowercase letter, and a number."
      );
      return;
    }
    setLoading(true);
    const res = await confirmForgotPasswordAction(email, code, password);
    setLoading(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    setDone(true);
  }

  if (done) {
    return (
      <div style={{ width: "100%", maxWidth: "380px", textAlign: "center" }}>
        <p style={{ color: "var(--qgi-text)", fontSize: "14px", marginBottom: "16px" }}>
          Your password has been reset.
        </p>
        <Link
          href={`/login?callbackUrl=${encodeURIComponent(callbackUrl)}` as Route}
          style={{
            display: "inline-block",
            padding: "10px 18px",
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--qgi-bg)",
            background: "var(--qgi-accent)",
            borderRadius: "8px",
            textDecoration: "none",
          }}
        >
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", maxWidth: "380px" }}>
      {notice && (
        <p
          aria-live="polite"
          style={{ color: "var(--qgi-accent)", fontSize: "13px", margin: "0 0 12px" }}
        >
          {notice}
        </p>
      )}

      {step === "request" ? (
        <form
          onSubmit={onRequest}
          style={{ display: "flex", flexDirection: "column", gap: "12px" }}
        >
          <AuthField
            label="Email"
            type="email"
            value={email}
            onChange={setEmail}
            autoComplete="email"
          />
          <AuthError message={error} />
          <AuthSubmit loading={loading}>
            {loading ? "Sending…" : "Send reset code"}
          </AuthSubmit>
        </form>
      ) : (
        <form
          onSubmit={onReset}
          style={{ display: "flex", flexDirection: "column", gap: "12px" }}
        >
          <AuthField
            label="Reset code"
            type="text"
            value={code}
            onChange={setCode}
            autoComplete="one-time-code"
            inputMode="numeric"
            placeholder="6-digit code"
          />
          <AuthField
            label="New password"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
          />
          <AuthField
            label="Confirm new password"
            type="password"
            value={confirmPw}
            onChange={setConfirmPw}
            autoComplete="new-password"
          />
          <p
            style={{ fontSize: "11px", color: "var(--qgi-text-dim)", margin: "-4px 0 0" }}
          >
            At least 10 characters, with upper &amp; lower case and a number.
          </p>
          <AuthError message={error} />
          <AuthSubmit loading={loading}>
            {loading ? "Resetting…" : "Reset password"}
          </AuthSubmit>
          <button
            type="button"
            onClick={() => {
              setStep("request");
              setCode("");
              setPassword("");
              setConfirmPw("");
              setError(null);
              setNotice(null);
            }}
            style={{
              background: "none",
              border: "none",
              color: "var(--qgi-text-muted)",
              fontSize: "13px",
              cursor: "pointer",
              padding: 0,
            }}
          >
            Change email
          </button>
        </form>
      )}

      <div style={{ marginTop: "16px", fontSize: "13px", textAlign: "center" }}>
        <Link
          href={`/login?callbackUrl=${encodeURIComponent(callbackUrl)}` as Route}
          style={{ color: "var(--qgi-text-muted)" }}
        >
          Back to sign in
        </Link>
      </div>
    </div>
  );
}
