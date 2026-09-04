"use server";

/**
 * Server actions for the email/password auth flows (sign-up, confirm, resend,
 * forgot/reset). They call the server-only lib/cognito wrapper and translate
 * failures into friendly, non-enumerating messages. Sign-IN itself goes through
 * the NextAuth Credentials provider (signIn("credentials")), not here.
 */
import {
  signUp,
  confirmSignUp,
  resendConfirmationCode,
  forgotPassword,
  confirmForgotPassword,
  CognitoError,
} from "@/lib/cognito";

export type ActionResult = { ok: true } | { ok: false; error: string };
export type SignUpResult =
  | { ok: true; needsConfirm: boolean }
  | { ok: false; error: string };

function fail(e: unknown): { ok: false; error: string } {
  if (e instanceof CognitoError) return { ok: false, error: e.message };
  return { ok: false, error: "Something went wrong. Please try again." };
}

export async function signUpAction(
  email: string,
  password: string
): Promise<SignUpResult> {
  try {
    const { userConfirmed } = await signUp(email, password);
    return { ok: true, needsConfirm: !userConfirmed };
  } catch (e) {
    return fail(e);
  }
}

export async function confirmSignUpAction(
  email: string,
  code: string
): Promise<ActionResult> {
  try {
    await confirmSignUp(email, code);
    return { ok: true };
  } catch (e) {
    return fail(e);
  }
}

export async function resendCodeAction(email: string): Promise<ActionResult> {
  try {
    await resendConfirmationCode(email);
    return { ok: true };
  } catch (e) {
    return fail(e);
  }
}

export async function forgotPasswordAction(email: string): Promise<ActionResult> {
  try {
    await forgotPassword(email);
    return { ok: true };
  } catch (e) {
    return fail(e);
  }
}

export async function confirmForgotPasswordAction(
  email: string,
  code: string,
  newPassword: string
): Promise<ActionResult> {
  try {
    await confirmForgotPassword(email, code, newPassword);
    return { ok: true };
  } catch (e) {
    return fail(e);
  }
}
