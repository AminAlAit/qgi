/**
 * lib/cognito.ts — SERVER-ONLY thin wrapper over the Cognito SDK.
 *
 * This is the email/password half of the hybrid auth layer (see
 * docs/SECURITY.md). It is called by:
 *   - the NextAuth Credentials provider (sign-in), and
 *   - server actions for sign-up / confirm / forgot-password.
 *
 * NEVER import this from a client component — the app client is confidential
 * (has a secret) and every call computes SECRET_HASH from it. The confidential
 * client + USER_PASSWORD_AUTH flow are provisioned in
 * infra/modules/cognito. The returned tokens are consumed by lib/auth.ts
 * (JWKS verification + `cognito:groups`).
 *
 * Env: COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET, AWS_REGION (default eu-central-1).
 */
import "server-only";

import { createHmac } from "node:crypto";
import {
  CognitoIdentityProviderClient,
  InitiateAuthCommand,
  SignUpCommand,
  ConfirmSignUpCommand,
  ResendConfirmationCodeCommand,
  ForgotPasswordCommand,
  ConfirmForgotPasswordCommand,
  ListUsersCommand,
} from "@aws-sdk/client-cognito-identity-provider";
import { awsRuntimeCredentials } from "@/lib/aws-credentials";

const REGION = process.env.AWS_REGION ?? "eu-central-1";
const CLIENT_ID = process.env.COGNITO_CLIENT_ID ?? "";
const CLIENT_SECRET = process.env.COGNITO_CLIENT_SECRET ?? "";
const USER_POOL_ID = process.env.COGNITO_USER_POOL_ID ?? "";

// Lazy singleton so importing this module never constructs a client (and never
// throws on missing env) until a call is actually made.
let _client: CognitoIdentityProviderClient | null = null;
async function client(): Promise<CognitoIdentityProviderClient> {
  if (!CLIENT_ID || !CLIENT_SECRET) {
    throw new CognitoError(
      "ConfigError",
      "Auth is not configured (COGNITO_CLIENT_ID / COGNITO_CLIENT_SECRET missing)."
    );
  }
  if (!_client) {
    // On Vercel, ListUsers (account-linking) needs IAM creds, which the default
    // chain can't get from OIDC — federate via AWS_ROLE_ARN. Locally, undefined
    // → default chain uses .env.local creds. The unauthenticated flows
    // (InitiateAuth/SignUp/…) don't require creds, but passing the provider is
    // harmless for them. See lib/aws-credentials.ts.
    const credentials = await awsRuntimeCredentials();
    _client = new CognitoIdentityProviderClient({
      region: REGION,
      ...(credentials ? { credentials } : {}),
    });
  }
  return _client;
}

/** SECRET_HASH = base64( HMAC-SHA256( username + clientId, clientSecret ) ). */
function secretHash(username: string): string {
  return createHmac("sha256", CLIENT_SECRET)
    .update(username + CLIENT_ID)
    .digest("base64");
}

/** A Cognito failure with the raw exception name + a user-safe message. */
export class CognitoError extends Error {
  constructor(
    public code: string,
    message: string
  ) {
    super(message);
    this.name = "CognitoError";
  }
}

/** Map raw Cognito SDK exceptions to friendly, non-enumerating messages. */
function mapError(err: unknown): CognitoError {
  const code =
    (err as { name?: string })?.name ??
    (err as { code?: string })?.code ??
    "UnknownError";
  const friendly: Record<string, string> = {
    NotAuthorizedException: "Incorrect email or password.",
    UserNotFoundException: "Incorrect email or password.",
    UserNotConfirmedException:
      "Please confirm your email address first — check your inbox for the code.",
    UsernameExistsException: "An account with this email already exists.",
    InvalidPasswordException: "That password doesn't meet the requirements.",
    CodeMismatchException: "That confirmation code is incorrect.",
    ExpiredCodeException: "That confirmation code has expired — request a new one.",
    LimitExceededException: "Too many attempts. Please wait a moment and try again.",
    TooManyRequestsException: "Too many attempts. Please wait a moment and try again.",
    InvalidParameterException:
      "Something in the request wasn't valid. Please check and retry.",
    ConfigError: (err as Error)?.message ?? "Auth is not configured.",
  };
  return new CognitoError(
    code,
    friendly[code] ?? "Something went wrong. Please try again."
  );
}

export interface Tokens {
  accessToken: string;
  idToken: string;
  refreshToken: string;
  expiresIn: number;
}

/** Email/password sign-in. Returns Cognito tokens (idToken feeds NextAuth). */
export async function signIn(email: string, password: string): Promise<Tokens> {
  try {
    const res = await (
      await client()
    ).send(
      new InitiateAuthCommand({
        AuthFlow: "USER_PASSWORD_AUTH",
        ClientId: CLIENT_ID,
        AuthParameters: {
          USERNAME: email,
          PASSWORD: password,
          SECRET_HASH: secretHash(email),
        },
      })
    );
    if (res.ChallengeName) {
      // e.g. NEW_PASSWORD_REQUIRED / MFA — not handled in Phase 1.
      throw new CognitoError(
        res.ChallengeName,
        "This account needs an extra step to sign in. Please contact support."
      );
    }
    const a = res.AuthenticationResult;
    if (!a?.IdToken || !a.AccessToken || !a.RefreshToken) {
      throw new CognitoError(
        "NoTokens",
        "Sign-in did not return a session. Please try again."
      );
    }
    return {
      accessToken: a.AccessToken,
      idToken: a.IdToken,
      refreshToken: a.RefreshToken,
      expiresIn: a.ExpiresIn ?? 3600,
    };
  } catch (err) {
    if (err instanceof CognitoError) throw err;
    throw mapError(err);
  }
}

/**
 * Account-linking helper: true iff a CONFIRMED email/password account already
 * exists in the pool for this email. Used to block a duplicate Google identity
 * for someone who signed up with a password (see the signIn callback in
 * lib/auth-config.ts).
 *
 * Uses the admin ListUsers API (needs `cognito-idp:ListUsers` on the pool —
 * granted to the frontend's IAM principal; see qgi-infra
 * modules/iam/vercel_frontend_reader.tf). FAIL-OPEN: any error (missing
 * permission, throttle, network, unset pool id) returns false, so a Google
 * sign-in is never blocked by an infra hiccup. Worst case is the pre-existing
 * behavior (no linking check) — never a lockout.
 *
 * Only CONFIRMED accounts block: an abandoned, never-confirmed password
 * sign-up should not permanently prevent Google sign-in on that address.
 */
export async function emailHasPasswordAccount(email: string): Promise<boolean> {
  if (!USER_POOL_ID || !email) return false;
  try {
    const res = await (
      await client()
    ).send(
      new ListUsersCommand({
        UserPoolId: USER_POOL_ID,
        // Cognito ListUsers filter syntax: attribute = "value" (quote-escaped).
        Filter: `email = "${email.replace(/"/g, '\\"')}"`,
        Limit: 1,
      })
    );
    return (res.Users ?? []).some((u) => u.UserStatus === "CONFIRMED");
  } catch (err) {
    console.warn(
      "[auth] emailHasPasswordAccount lookup failed (fail-open):",
      (err as { name?: string })?.name ?? "UnknownError"
    );
    return false;
  }
}

/** Register a new email/password user. Returns whether email confirmation is needed. */
export async function signUp(
  email: string,
  password: string
): Promise<{ userConfirmed: boolean }> {
  try {
    const res = await (
      await client()
    ).send(
      new SignUpCommand({
        ClientId: CLIENT_ID,
        Username: email,
        Password: password,
        SecretHash: secretHash(email),
        UserAttributes: [{ Name: "email", Value: email }],
      })
    );
    return { userConfirmed: res.UserConfirmed ?? false };
  } catch (err) {
    throw mapError(err);
  }
}

/** Confirm a sign-up with the emailed code. */
export async function confirmSignUp(email: string, code: string): Promise<void> {
  try {
    await (
      await client()
    ).send(
      new ConfirmSignUpCommand({
        ClientId: CLIENT_ID,
        Username: email,
        ConfirmationCode: code,
        SecretHash: secretHash(email),
      })
    );
  } catch (err) {
    throw mapError(err);
  }
}

/** Resend the sign-up confirmation code. */
export async function resendConfirmationCode(email: string): Promise<void> {
  try {
    await (
      await client()
    ).send(
      new ResendConfirmationCodeCommand({
        ClientId: CLIENT_ID,
        Username: email,
        SecretHash: secretHash(email),
      })
    );
  } catch (err) {
    throw mapError(err);
  }
}

/** Start a password reset — Cognito emails a code. */
export async function forgotPassword(email: string): Promise<void> {
  try {
    await (
      await client()
    ).send(
      new ForgotPasswordCommand({
        ClientId: CLIENT_ID,
        Username: email,
        SecretHash: secretHash(email),
      })
    );
  } catch (err) {
    throw mapError(err);
  }
}

/** Complete a password reset with the emailed code + new password. */
export async function confirmForgotPassword(
  email: string,
  code: string,
  newPassword: string
): Promise<void> {
  try {
    await (
      await client()
    ).send(
      new ConfirmForgotPasswordCommand({
        ClientId: CLIENT_ID,
        Username: email,
        ConfirmationCode: code,
        Password: newPassword,
        SecretHash: secretHash(email),
      })
    );
  } catch (err) {
    throw mapError(err);
  }
}
