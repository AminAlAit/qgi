import NextAuth, { CredentialsSignin } from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";
import { decodeJwt } from "jose";
import { signIn as cognitoSignIn, emailHasPasswordAccount } from "@/lib/cognito";

/**
 * A CredentialsSignin whose `code` reaches the browser as the `?code=` query
 * param (see @auth/core: `params.set("code", error.code)`), which
 * next-auth/react's signIn() then returns as `{ error, code }`. The login form
 * maps the code to a per-reason message. Kept to a small, stable, non-PII set
 * of codes — never the raw Cognito exception (avoids leaking detail).
 */
class SignInError extends CredentialsSignin {
  constructor(code: string) {
    super();
    this.code = code;
  }
}

/** Map a raw Cognito failure to a stable, client-safe sign-in error code. */
function signInErrorCode(err: unknown): string {
  const code = (err as { code?: string })?.code;
  switch (code) {
    case "UserNotConfirmedException":
      return "unconfirmed";
    case "TooManyRequestsException":
    case "LimitExceededException":
      return "too_many";
    case "ConfigError":
      return "config";
    default:
      // NotAuthorizedException / UserNotFoundException / anything unexpected →
      // one generic, non-enumerating message.
      return "invalid";
  }
}

/**
 * NextAuth.js v5 (Auth.js) config — the app's session front door (see
 * docs/SECURITY.md).
 *
 * Providers:
 *  - Google: native "Continue with Google" (identity lives in the NextAuth JWT).
 *  - Credentials: email/password verified against Cognito via lib/cognito
 *    (server-side); the Cognito id-token's `cognito:groups` claim is surfaced
 *    into the session so the plan-gating in lib/auth.ts keeps working.
 *
 * SKIP_AUTH=true still bypasses gating (dev). This module imports the AWS SDK
 * (via lib/cognito) so it must run on the NODE runtime only — it's consumed by
 * app/api/auth/[...nextauth]/route.ts, NOT by the edge proxy.ts (which keeps a
 * lightweight cookie check).
 */
export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    }),
    Credentials({
      id: "credentials",
      name: "Email and password",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = typeof credentials?.email === "string" ? credentials.email : "";
        const password =
          typeof credentials?.password === "string" ? credentials.password : "";
        if (!email || !password) return null;
        try {
          const tokens = await cognitoSignIn(email, password);
          const claims = decodeJwt(tokens.idToken);
          const groups = Array.isArray(claims["cognito:groups"])
            ? (claims["cognito:groups"] as string[])
            : [];
          return {
            id: (claims.sub as string) ?? email,
            email: (claims.email as string) ?? email,
            groups,
          };
        } catch (err) {
          // Surface a stable per-reason code to the login form (e.g. an
          // unconfirmed account must not read as "wrong password").
          throw new SignInError(signInErrorCode(err));
        }
      },
    }),
  ],
  callbacks: {
    // NOTE: no `authorized` callback here. That callback only fires when
    // NextAuth's `auth()` wrapper is used as middleware — but route gating
    // lives in proxy.ts, which validates the session with getToken() directly.
    // A dead `authorized` callback here would be misleading (it looked like the
    // gate but never ran), so it was removed.

    // Account-linking guard. Google and Cognito are separate identity stores;
    // without this, a user who already has an email/password (Cognito) account
    // could sign in with Google on the same address and get a SECOND, unlinked
    // identity (no groups) — the classic "I paid but Google shows me as free"
    // support incident once plan-gating goes live. So: block a Google sign-in
    // when a confirmed password account already owns that email, and tell the
    // user to sign in the original way. (The reverse — a Google-only user
    // trying email/password — can't be detected without a shared store; they
    // get the generic "incorrect email or password", which is acceptable.)
    // emailHasPasswordAccount is fail-open, so an infra hiccup never locks
    // anyone out; the worst case is the pre-existing no-check behavior.
    async signIn({ user, account }) {
      if (account?.provider === "google" && user?.email) {
        if (await emailHasPasswordAccount(user.email)) {
          return "/login?error=account_exists";
        }
      }
      return true;
    },
    jwt({ token, user, account }) {
      if (user) token.groups = user.groups ?? [];
      if (account) token.provider = account.provider;
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        session.user.groups = token.groups ?? [];
        session.user.provider = token.provider;
      }
      return session;
    },
  },
});
