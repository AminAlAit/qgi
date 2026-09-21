"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import { AuthField, AuthSubmit, AuthError } from "@/components/auth/AuthField";
import { safeCallbackUrl } from "@/lib/safe-callback";
import { signUpAction, confirmSignUpAction, resendCodeAction } from "@/lib/auth-actions";

type Step = "details" | "confirm";

export function SignupForm() {
  const params = useSearchParams();
  const callbackUrl = safeCallbackUrl(params.get("callbackUrl"));
  const [step, setStep] = useState<Step>("details");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onDetails(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return; // guard against double-submit
    setError(null);
    if (password !== confirmPw) {
      setError("Passwords don't match.");
      return;
    }
    // Mirror the Cognito pool policy client-side so users get an instant,
    // specific message instead of a vague round-trip InvalidPasswordException.
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
    const res = await signUpAction(email, password);
    if (!res.ok) {
      setLoading(false);
      setError(res.error);
      return;
    }
    if (res.needsConfirm) {
      setLoading(false);
      setStep("confirm");
      setNotice(`We emailed a 6-digit code to ${email}.`);
    } else {
      await finish();
    }
  }

  async function onConfirm(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return; // guard against double-submit
    setError(null);
    setLoading(true);
    const res = await confirmSignUpAction(email, code);
    if (!res.ok) {
      setLoading(false);
      setError(res.error);
      return;
    }
    await finish();
  }

  async function finish() {
    const r = await signIn("credentials", { email, password, redirect: false });
    setLoading(false);
    if (r?.error) {
      setError("Account confirmed, but automatic sign-in failed. Please sign in.");
    } else {
      window.location.href = callbackUrl;
    }
  }

  async function onResend() {
    setError(null);
    setNotice(null);
    const res = await resendCodeAction(email);
    if (res.ok) setNotice("A new code is on its way.");
    else setError(res.error);
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

      {step === "details" ? (
        <form
          onSubmit={onDetails}
          style={{ display: "flex", flexDirection: "column", gap: "12px" }}
        >
          <AuthField
            label="Email"
            type="email"
            value={email}
            onChange={setEmail}
            autoComplete="email"
          />
          <AuthField
            label="Password"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
          />
          <AuthField
            label="Confirm password"
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
            {loading ? "Creating account…" : "Create account"}
          </AuthSubmit>
        </form>
      ) : (
        <form
          onSubmit={onConfirm}
          style={{ display: "flex", flexDirection: "column", gap: "12px" }}
        >
          <AuthField
            label="Confirmation code"
            type="text"
            value={code}
            onChange={setCode}
            autoComplete="one-time-code"
            inputMode="numeric"
            placeholder="6-digit code"
          />
          <AuthError message={error} />
          <AuthSubmit loading={loading}>
            {loading ? "Confirming…" : "Confirm & sign in"}
          </AuthSubmit>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <button
              type="button"
              onClick={onResend}
              style={{
                background: "none",
                border: "none",
                color: "var(--qgi-text-muted)",
                fontSize: "13px",
                cursor: "pointer",
                padding: 0,
              }}
            >
              Resend code
            </button>
            <button
              type="button"
              onClick={() => {
                setStep("details");
                setCode("");
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
          </div>
        </form>
      )}

      <div style={{ marginTop: "16px", fontSize: "13px", textAlign: "center" }}>
        <span style={{ color: "var(--qgi-text-dim)" }}>Already have an account? </span>
        <Link
          href={`/login?callbackUrl=${encodeURIComponent(callbackUrl)}` as Route}
          style={{ color: "var(--qgi-accent)" }}
        >
          Sign in
        </Link>
      </div>
    </div>
  );
}
