/**
 * lib/cognito.ts — server wrapper over @aws-sdk/client-cognito-identity-provider.
 *
 * The AWS SDK client is stubbed via vi.mock so no network/AWS calls happen.
 * We keep the real `*Command` classes (only the client's `send` is replaced)
 * so we can assert on `command.input` exactly as the SDK would receive it —
 * this is what lets the SECRET_HASH assertions be a real integration check
 * rather than a mock of our own math.
 *
 * COGNITO_CLIENT_ID / COGNITO_CLIENT_SECRET are read into module-level consts
 * at import time, so they're set on process.env BEFORE the dynamic import of
 * lib/cognito below (vi.mock calls are hoisted above this, so that part is
 * safe regardless of ordering).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createHmac } from "node:crypto";

const TEST_CLIENT_ID = "test-client-id-12345";
const TEST_CLIENT_SECRET = "test-client-secret-abcdef";

const { mockSend } = vi.hoisted(() => ({ mockSend: vi.fn() }));

vi.mock("@aws-sdk/client-cognito-identity-provider", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@aws-sdk/client-cognito-identity-provider")>();
  return {
    ...actual,
    CognitoIdentityProviderClient: vi.fn().mockImplementation(() => ({
      send: mockSend,
    })),
  };
});

process.env.COGNITO_CLIENT_ID = TEST_CLIENT_ID;
process.env.COGNITO_CLIENT_SECRET = TEST_CLIENT_SECRET;
process.env.COGNITO_USER_POOL_ID = "eu-central-1_testpool";
process.env.AWS_REGION = "eu-central-1";

const { signIn, signUp, emailHasPasswordAccount, CognitoError } =
  await import("@/lib/cognito");
const { InitiateAuthCommand, SignUpCommand, ListUsersCommand } =
  await import("@aws-sdk/client-cognito-identity-provider");

function expectedSecretHash(username: string): string {
  return createHmac("sha256", TEST_CLIENT_SECRET)
    .update(username + TEST_CLIENT_ID)
    .digest("base64");
}

/** Build a fake Cognito SDK exception with the given exception `name`. */
function cognitoException(name: string, message = "AWS says no"): Error {
  const err = new Error(message);
  err.name = name;
  return err;
}

beforeEach(() => {
  mockSend.mockReset();
});

describe("secretHash (tested indirectly via the SECRET_HASH sent to Cognito)", () => {
  it("InitiateAuthCommand carries SECRET_HASH = base64(HMAC-SHA256(username + clientId, clientSecret))", async () => {
    mockSend.mockResolvedValueOnce({
      AuthenticationResult: {
        AccessToken: "access-token",
        IdToken: "id-token",
        RefreshToken: "refresh-token",
        ExpiresIn: 3600,
      },
    });

    const email = "user@example.com";
    await signIn(email, "correct horse battery staple");

    expect(mockSend).toHaveBeenCalledTimes(1);
    const command = mockSend.mock.calls[0][0];
    expect(command).toBeInstanceOf(InitiateAuthCommand);
    expect(command.input.ClientId).toBe(TEST_CLIENT_ID);
    expect(command.input.AuthParameters.USERNAME).toBe(email);
    expect(command.input.AuthParameters.SECRET_HASH).toBe(expectedSecretHash(email));
  });

  it("SignUpCommand carries the same SECRET_HASH formula (top-level SecretHash field)", async () => {
    mockSend.mockResolvedValueOnce({ UserConfirmed: false });

    const email = "new-user@example.com";
    await signUp(email, "another-password-1!");

    const command = mockSend.mock.calls[0][0];
    expect(command).toBeInstanceOf(SignUpCommand);
    expect(command.input.SecretHash).toBe(expectedSecretHash(email));
  });

  it("SECRET_HASH changes when the username changes (not a constant)", async () => {
    mockSend.mockResolvedValue({
      AuthenticationResult: {
        AccessToken: "at",
        IdToken: "idt",
        RefreshToken: "rt",
        ExpiresIn: 3600,
      },
    });

    await signIn("alice@example.com", "pw");
    const aliceHash = mockSend.mock.calls[0][0].input.AuthParameters.SECRET_HASH;

    await signIn("bob@example.com", "pw");
    const bobHash = mockSend.mock.calls[1][0].input.AuthParameters.SECRET_HASH;

    expect(aliceHash).not.toBe(bobHash);
    expect(aliceHash).toBe(expectedSecretHash("alice@example.com"));
    expect(bobHash).toBe(expectedSecretHash("bob@example.com"));
  });
});

describe("mapError — raw Cognito exception name -> friendly CognitoError", () => {
  it.each([
    ["NotAuthorizedException", "Incorrect email or password."],
    [
      "UserNotConfirmedException",
      "Please confirm your email address first — check your inbox for the code.",
    ],
    ["UsernameExistsException", "An account with this email already exists."],
    ["CodeMismatchException", "That confirmation code is incorrect."],
    ["ExpiredCodeException", "That confirmation code has expired — request a new one."],
    ["InvalidPasswordException", "That password doesn't meet the requirements."],
    ["LimitExceededException", "Too many attempts. Please wait a moment and try again."],
  ])("%s -> %j", async (rawName, friendlyMessage) => {
    mockSend.mockRejectedValueOnce(cognitoException(rawName));

    await expect(signIn("user@example.com", "pw")).rejects.toMatchObject({
      name: "CognitoError",
      code: rawName,
      message: friendlyMessage,
    });
    await expect(signIn("user@example.com", "pw")).rejects.toBeInstanceOf(CognitoError);
  });

  it("unmapped/unknown exception names fall back to a generic message", async () => {
    mockSend.mockRejectedValueOnce(cognitoException("SomeUnmappedException"));

    await expect(signUp("user@example.com", "pw")).rejects.toMatchObject({
      name: "CognitoError",
      code: "SomeUnmappedException",
      message: "Something went wrong. Please try again.",
    });
  });
});

describe("signIn — happy path", () => {
  it("returns tokens straight from AuthenticationResult", async () => {
    mockSend.mockResolvedValueOnce({
      AuthenticationResult: {
        AccessToken: "access-token-abc",
        IdToken: "id-token-def",
        RefreshToken: "refresh-token-ghi",
        ExpiresIn: 1800,
      },
    });

    const tokens = await signIn("user@example.com", "pw");
    expect(tokens).toEqual({
      accessToken: "access-token-abc",
      idToken: "id-token-def",
      refreshToken: "refresh-token-ghi",
      expiresIn: 1800,
    });
  });

  it("defaults expiresIn to 3600 when Cognito omits ExpiresIn", async () => {
    mockSend.mockResolvedValueOnce({
      AuthenticationResult: {
        AccessToken: "at",
        IdToken: "idt",
        RefreshToken: "rt",
      },
    });

    const tokens = await signIn("user@example.com", "pw");
    expect(tokens.expiresIn).toBe(3600);
  });

  it("throws a CognitoError when Cognito returns a ChallengeName instead of tokens", async () => {
    mockSend.mockResolvedValueOnce({ ChallengeName: "NEW_PASSWORD_REQUIRED" });

    await expect(signIn("user@example.com", "pw")).rejects.toMatchObject({
      name: "CognitoError",
      code: "NEW_PASSWORD_REQUIRED",
      message: "This account needs an extra step to sign in. Please contact support.",
    });
  });

  it("throws a CognitoError when AuthenticationResult is missing required tokens", async () => {
    mockSend.mockResolvedValueOnce({ AuthenticationResult: {} });

    await expect(signIn("user@example.com", "pw")).rejects.toMatchObject({
      name: "CognitoError",
      code: "NoTokens",
    });
  });
});

describe("signUp — happy path", () => {
  it("returns userConfirmed: true when Cognito confirms the user immediately", async () => {
    mockSend.mockResolvedValueOnce({ UserConfirmed: true });
    const result = await signUp("user@example.com", "pw");
    expect(result).toEqual({ userConfirmed: true });
  });

  it("returns userConfirmed: false when Cognito requires email confirmation", async () => {
    mockSend.mockResolvedValueOnce({ UserConfirmed: false });
    const result = await signUp("user@example.com", "pw");
    expect(result).toEqual({ userConfirmed: false });
  });

  it("defaults userConfirmed to false when Cognito omits the field", async () => {
    mockSend.mockResolvedValueOnce({});
    const result = await signUp("user@example.com", "pw");
    expect(result).toEqual({ userConfirmed: false });
  });
});

describe("emailHasPasswordAccount — account-linking existence check", () => {
  it("issues a ListUsersCommand filtered by email, scoped to the pool", async () => {
    mockSend.mockResolvedValueOnce({ Users: [] });
    await emailHasPasswordAccount("user@example.com");

    const command = mockSend.mock.calls[0][0];
    expect(command).toBeInstanceOf(ListUsersCommand);
    expect(command.input.UserPoolId).toBe("eu-central-1_testpool");
    expect(command.input.Filter).toBe('email = "user@example.com"');
  });

  it("returns true when a CONFIRMED user owns the email", async () => {
    mockSend.mockResolvedValueOnce({ Users: [{ UserStatus: "CONFIRMED" }] });
    await expect(emailHasPasswordAccount("user@example.com")).resolves.toBe(true);
  });

  it("returns false when no user owns the email", async () => {
    mockSend.mockResolvedValueOnce({ Users: [] });
    await expect(emailHasPasswordAccount("nobody@example.com")).resolves.toBe(false);
  });

  it("returns false for an UNCONFIRMED account (abandoned sign-up must not block Google)", async () => {
    mockSend.mockResolvedValueOnce({ Users: [{ UserStatus: "UNCONFIRMED" }] });
    await expect(emailHasPasswordAccount("pending@example.com")).resolves.toBe(false);
  });

  it("FAILS OPEN (returns false) when the ListUsers call throws — never blocks sign-in on an infra hiccup", async () => {
    mockSend.mockRejectedValueOnce(cognitoException("AccessDeniedException"));
    await expect(emailHasPasswordAccount("user@example.com")).resolves.toBe(false);
  });

  it("returns false without calling AWS when the email is empty", async () => {
    await expect(emailHasPasswordAccount("")).resolves.toBe(false);
    expect(mockSend).not.toHaveBeenCalled();
  });
});
