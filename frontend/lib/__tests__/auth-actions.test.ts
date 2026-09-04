/**
 * lib/auth-actions.ts — server actions for sign-up/confirm/resend/forgot
 * password. `lib/cognito` is mocked wholesale (its functions become vi.fn())
 * so these tests only exercise the { ok, error } translation layer, not the
 * Cognito SDK itself (that's covered by cognito.test.ts).
 *
 * The mocked module keeps the REAL `CognitoError` class (via importOriginal)
 * so `e instanceof CognitoError` inside lib/auth-actions.ts's `fail()` still
 * matches — both this test file and auth-actions.ts resolve "@/lib/cognito"
 * to the same mocked module instance, so the class reference is shared.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const {
  signUp,
  confirmSignUp,
  resendConfirmationCode,
  forgotPassword,
  confirmForgotPassword,
} = vi.hoisted(() => ({
  signUp: vi.fn(),
  confirmSignUp: vi.fn(),
  resendConfirmationCode: vi.fn(),
  forgotPassword: vi.fn(),
  confirmForgotPassword: vi.fn(),
}));

vi.mock("@/lib/cognito", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/cognito")>();
  return {
    ...actual,
    signUp,
    confirmSignUp,
    resendConfirmationCode,
    forgotPassword,
    confirmForgotPassword,
  };
});

const {
  signUpAction,
  confirmSignUpAction,
  resendCodeAction,
  forgotPasswordAction,
  confirmForgotPasswordAction,
} = await import("@/lib/auth-actions");
const { CognitoError } = await import("@/lib/cognito");

const GENERIC_FALLBACK = "Something went wrong. Please try again.";

beforeEach(() => {
  signUp.mockReset();
  confirmSignUp.mockReset();
  resendConfirmationCode.mockReset();
  forgotPassword.mockReset();
  confirmForgotPassword.mockReset();
});

describe("signUpAction", () => {
  it("returns ok:true, needsConfirm:true when Cognito has NOT auto-confirmed the user", async () => {
    signUp.mockResolvedValueOnce({ userConfirmed: false });
    const result = await signUpAction("user@example.com", "pw");
    expect(result).toEqual({ ok: true, needsConfirm: true });
    expect(signUp).toHaveBeenCalledWith("user@example.com", "pw");
  });

  it("returns ok:true, needsConfirm:false when Cognito auto-confirmed the user", async () => {
    signUp.mockResolvedValueOnce({ userConfirmed: true });
    const result = await signUpAction("user@example.com", "pw");
    expect(result).toEqual({ ok: true, needsConfirm: false });
  });

  it("returns ok:false with the friendly message when signUp throws a CognitoError", async () => {
    signUp.mockRejectedValueOnce(
      new CognitoError(
        "UsernameExistsException",
        "An account with this email already exists."
      )
    );
    const result = await signUpAction("user@example.com", "pw");
    expect(result).toEqual({
      ok: false,
      error: "An account with this email already exists.",
    });
  });

  it("returns the generic fallback when signUp throws a non-CognitoError", async () => {
    signUp.mockRejectedValueOnce(new Error("ECONNRESET"));
    const result = await signUpAction("user@example.com", "pw");
    expect(result).toEqual({ ok: false, error: GENERIC_FALLBACK });
  });
});

describe("confirmSignUpAction", () => {
  it("returns ok:true on success and forwards email/code", async () => {
    confirmSignUp.mockResolvedValueOnce(undefined);
    const result = await confirmSignUpAction("user@example.com", "123456");
    expect(result).toEqual({ ok: true });
    expect(confirmSignUp).toHaveBeenCalledWith("user@example.com", "123456");
  });

  it("returns ok:false with the friendly message on CognitoError", async () => {
    confirmSignUp.mockRejectedValueOnce(
      new CognitoError("CodeMismatchException", "That confirmation code is incorrect.")
    );
    const result = await confirmSignUpAction("user@example.com", "000000");
    expect(result).toEqual({ ok: false, error: "That confirmation code is incorrect." });
  });

  it("returns the generic fallback on a non-CognitoError", async () => {
    confirmSignUp.mockRejectedValueOnce(new TypeError("boom"));
    const result = await confirmSignUpAction("user@example.com", "000000");
    expect(result).toEqual({ ok: false, error: GENERIC_FALLBACK });
  });
});

describe("resendCodeAction", () => {
  it("returns ok:true on success and forwards email", async () => {
    resendConfirmationCode.mockResolvedValueOnce(undefined);
    const result = await resendCodeAction("user@example.com");
    expect(result).toEqual({ ok: true });
    expect(resendConfirmationCode).toHaveBeenCalledWith("user@example.com");
  });

  it("returns ok:false with the friendly message on CognitoError", async () => {
    resendConfirmationCode.mockRejectedValueOnce(
      new CognitoError(
        "LimitExceededException",
        "Too many attempts. Please wait a moment and try again."
      )
    );
    const result = await resendCodeAction("user@example.com");
    expect(result).toEqual({
      ok: false,
      error: "Too many attempts. Please wait a moment and try again.",
    });
  });

  it("returns the generic fallback on a non-CognitoError", async () => {
    resendConfirmationCode.mockRejectedValueOnce(new Error("network down"));
    const result = await resendCodeAction("user@example.com");
    expect(result).toEqual({ ok: false, error: GENERIC_FALLBACK });
  });
});

describe("forgotPasswordAction", () => {
  it("returns ok:true on success and forwards email", async () => {
    forgotPassword.mockResolvedValueOnce(undefined);
    const result = await forgotPasswordAction("user@example.com");
    expect(result).toEqual({ ok: true });
    expect(forgotPassword).toHaveBeenCalledWith("user@example.com");
  });

  it("returns ok:false with the friendly message on CognitoError", async () => {
    forgotPassword.mockRejectedValueOnce(
      new CognitoError("NotAuthorizedException", "Incorrect email or password.")
    );
    const result = await forgotPasswordAction("user@example.com");
    expect(result).toEqual({ ok: false, error: "Incorrect email or password." });
  });

  it("returns the generic fallback on a non-CognitoError", async () => {
    forgotPassword.mockRejectedValueOnce(new Error("nope"));
    const result = await forgotPasswordAction("user@example.com");
    expect(result).toEqual({ ok: false, error: GENERIC_FALLBACK });
  });
});

describe("confirmForgotPasswordAction", () => {
  it("returns ok:true on success and forwards email/code/newPassword", async () => {
    confirmForgotPassword.mockResolvedValueOnce(undefined);
    const result = await confirmForgotPasswordAction(
      "user@example.com",
      "123456",
      "NewPassw0rd!"
    );
    expect(result).toEqual({ ok: true });
    expect(confirmForgotPassword).toHaveBeenCalledWith(
      "user@example.com",
      "123456",
      "NewPassw0rd!"
    );
  });

  it("returns ok:false with the friendly message on CognitoError", async () => {
    confirmForgotPassword.mockRejectedValueOnce(
      new CognitoError(
        "ExpiredCodeException",
        "That confirmation code has expired — request a new one."
      )
    );
    const result = await confirmForgotPasswordAction(
      "user@example.com",
      "123456",
      "NewPassw0rd!"
    );
    expect(result).toEqual({
      ok: false,
      error: "That confirmation code has expired — request a new one.",
    });
  });

  it("returns the generic fallback on a non-CognitoError", async () => {
    confirmForgotPassword.mockRejectedValueOnce("a thrown string, not an Error");
    const result = await confirmForgotPasswordAction(
      "user@example.com",
      "123456",
      "NewPassw0rd!"
    );
    expect(result).toEqual({ ok: false, error: GENERIC_FALLBACK });
  });
});
