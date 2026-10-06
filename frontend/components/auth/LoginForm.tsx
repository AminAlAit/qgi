"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import { safeCallbackUrl } from "@/lib/safe-callback";
import { confirmSignUpAction, resendCodeAction } from "@/lib/auth-actions";

/** Per-reason sign-in messages, keyed by the code lib/auth-config surfaces. */
const SIGNIN_MESSAGES: Record<string, string> = {
  too_many: "Too many attempts. Please wait a moment and try again.",
  config: "Sign-in is temporarily unavailable. Please try again shortly.",
  invalid: "Incorrect email or password.",
};

/**
 * Login form — "Continue with Google" + native email/password.
 * Google works today; email/password works once the Cognito pool is applied
 * (the Credentials provider calls lib/cognito server-side).
 */
export function LoginForm() {
  const params = useSearchParams();
  // An explicit callbackUrl (e.g. from a gated "Open Dashboard" click) is
  // sanitized — it's attacker-controllable and we navigate to it manually,
  // bypassing NextAuth's same-origin guard. With no callbackUrl, safeCallbackUrl
  // falls back to /dashboard (the Briefing surface), the default landing.
  const callbackUrl = safeCallbackUrl(params.get("callbackUrl"));
  // Account-linking bounce: a Google sign-in was blocked because a password
  // account already owns this email (see signIn callback in lib/auth-config).
  const initialError =
    params.get("error") === "account_exists"
      ? "This email is already registered with a password. Please sign in with your email and password below."
      : null;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(initialError);
  const [loading, setLoading] = useState(false);
  // Inline "confirm your email" sub-flow for an unconfirmed account. We still
  // hold email+password, so after confirming we sign the user straight in
  // (instead of the old dead-end where "unconfirmed" read as "wrong password").
  const [needsConfirm, setNeedsConfirm] = useState(false);
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  async function completeSignIn() {
    const res = await signIn("credentials", { email, password, redirect: false });
    if (res?.error) {
      setError("Sign-in failed after confirmation. Please try signing in again.");
    } else {
      window.location.href = callbackUrl;
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return; // guard against double-submit
    setError(null);
    setNotice(null);
    setLoading(true);
    const res = await signIn("credentials", { email, password, redirect: false });
    if (res?.error) {
      const errCode = res.code ?? "";
      if (errCode === "unconfirmed") {
        // Not a wrong password — the account exists but isn't verified. Send a
        // fresh code and drop into the inline confirm step.
        setNeedsConfirm(true);
        await resendCodeAction(email);
        setNotice(
          "Your email isn't confirmed yet — we sent a new code. Enter it below to finish signing in."
        );
      } else {
        setError(SIGNIN_MESSAGES[errCode] ?? "Incorrect email or password.");
      }
      setLoading(false);
    } else {
      window.location.href = callbackUrl; // keep the spinner up through nav
    }
  }

  async function onConfirm(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);
    const res = await confirmSignUpAction(email, code);
    if (!res.ok) {
      setLoading(false);
      setError(res.error);
      return;
    }
    await completeSignIn();
    setLoading(false);
  }

  async function onResend() {
    setError(null);
    const res = await resendCodeAction(email);
    if (res.ok) setNotice("A new code is on its way.");
    else setError(res.error);
  }

  if (needsConfirm) {
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
        <form
          onSubmit={onConfirm}
          style={{ display: "flex", flexDirection: "column", gap: "12px" }}
        >
          <Field
            label="Confirmation code"
            type="text"
            value={code}
            onChange={setCode}
            autoComplete="one-time-code"
          />
          {error && (
            <p
              role="alert"
              style={{ color: "var(--qgi-danger)", fontSize: "13px", margin: 0 }}
            >
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--qgi-surface)]"
            style={{
              padding: "11px 14px",
              minHeight: "44px",
              fontSize: "14px",
              fontWeight: 600,
              color: "var(--qgi-bg)",
              background: "var(--qgi-accent)",
              border: "none",
              borderRadius: "8px",
              cursor: loading ? "default" : "pointer",
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? "Confirming…" : "Confirm & sign in"}
          </button>
        </form>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: "16px",
            fontSize: "13px",
          }}
        >
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
              setNeedsConfirm(false);
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
            Back to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", maxWidth: "380px" }}>
      <button
        type="button"
        onClick={() => signIn("google", { callbackUrl })}
        className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--qgi-surface)]"
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "10px",
          padding: "11px 14px",
          minHeight: "44px",
          fontSize: "14px",
          fontWeight: 500,
          color: "var(--qgi-text)",
          background: "var(--qgi-surface, rgba(255,255,255,0.04))",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          cursor: "pointer",
        }}
      >
        <GoogleGlyph />
        Continue with Google
      </button>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
          margin: "18px 0",
          color: "var(--qgi-text-dim)",
          fontSize: "11px",
          letterSpacing: "1px",
          textTransform: "uppercase",
        }}
      >
        <span style={{ flex: 1, height: 1, background: "var(--qgi-border)" }} />
        or
        <span style={{ flex: 1, height: 1, background: "var(--qgi-border)" }} />
      </div>

      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "12px" }}
      >
        <Field
          label="Email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
        />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />
        {error && (
          <p
            role="alert"
            style={{ color: "var(--qgi-danger)", fontSize: "13px", margin: 0 }}
          >
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--qgi-surface)]"
          style={{
            padding: "11px 14px",
            minHeight: "44px",
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--qgi-bg)",
            background: "var(--qgi-accent)",
            border: "none",
            borderRadius: "8px",
            cursor: loading ? "default" : "pointer",
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: "16px",
          fontSize: "13px",
        }}
      >
        <Link
          href={`/signup?callbackUrl=${encodeURIComponent(callbackUrl)}` as Route}
          style={{ color: "var(--qgi-accent)" }}
        >
          Create account
        </Link>
        <Link
          href={
            `/forgot-password?callbackUrl=${encodeURIComponent(callbackUrl)}` as Route
          }
          style={{ color: "var(--qgi-text-muted)" }}
        >
          Forgot password?
        </Link>
      </div>
    </div>
  );
}

function Field({
  label,
  type,
  value,
  onChange,
  autoComplete,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
      <span style={{ fontSize: "12px", color: "var(--qgi-text-muted)" }}>{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        required
        className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--qgi-surface)]"
        style={{
          padding: "10px 12px",
          fontSize: "14px",
          minHeight: "44px",
          color: "var(--qgi-text)",
          background: "var(--qgi-bg)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
        }}
      />
    </label>
  );
}

function GoogleGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z"
      />
      <path
        fill="#34A853"
        d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z"
      />
      <path
        fill="#FBBC05"
        d="M11.69 28.18C11.25 26.86 11 25.45 11 24s.25-2.86.69-4.18v-5.7H4.34A21.99 21.99 0 0 0 2 24c0 3.55.85 6.91 2.34 9.88l7.35-5.7z"
      />
      <path
        fill="#EA4335"
        d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7c1.73-5.2 6.58-9.07 12.31-9.07z"
      />
    </svg>
  );
}
