/**
 * lib/user-settings-store.ts — DynamoDB store for per-user settings.
 * DynamoDBClient.send is stubbed; the real *Command classes are kept so we can
 * assert on command.input exactly as the SDK would receive it.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockSend } = vi.hoisted(() => ({ mockSend: vi.fn() }));
vi.mock("@aws-sdk/client-dynamodb", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@aws-sdk/client-dynamodb")>();
  return {
    ...actual,
    DynamoDBClient: vi.fn().mockImplementation(() => ({ send: mockSend })),
  };
});

const { getServerSettings, putServerSettings } =
  await import("@/lib/user-settings-store");
const { GetItemCommand, PutItemCommand } = await import("@aws-sdk/client-dynamodb");
const { DEFAULT_SETTINGS } = await import("@/lib/user-settings");

beforeEach(() => mockSend.mockReset());

describe("getServerSettings", () => {
  it("returns null when the row has no settings", async () => {
    mockSend.mockResolvedValueOnce({});
    expect(await getServerSettings("a@b.com")).toBeNull();
  });

  it("parses AND sanitizes the stored JSON blob", async () => {
    mockSend.mockResolvedValueOnce({
      Item: {
        settings: {
          // includes a retired field (defaultLanding) + a bad-typed trendFocus
          S: JSON.stringify({
            defaultLanding: "trends",
            watchlist: ["US", 5],
            trendFocus: "not-an-array",
          }),
        },
      },
    });
    const s = await getServerSettings("a@b.com");
    expect(s).not.toHaveProperty("defaultLanding"); // retired field stripped
    expect(s?.watchlist).toEqual(["US"]); // non-string dropped by sanitize
    expect(s?.trendFocus).toBeNull(); // invalid type coerced by sanitize
  });

  it("returns null on a DDB error (caller falls back)", async () => {
    mockSend.mockRejectedValueOnce(new Error("boom"));
    expect(await getServerSettings("a@b.com")).toBeNull();
  });

  it("returns null for empty email without touching DDB", async () => {
    expect(await getServerSettings("")).toBeNull();
    expect(mockSend).not.toHaveBeenCalled();
  });

  it("issues a GetItem keyed on email", async () => {
    mockSend.mockResolvedValueOnce({});
    await getServerSettings("user@x.com");
    const cmd = mockSend.mock.calls[0][0];
    expect(cmd).toBeInstanceOf(GetItemCommand);
    expect(cmd.input.Key.email.S).toBe("user@x.com");
  });
});

describe("putServerSettings", () => {
  it("writes the sanitized blob + timestamp keyed on email", async () => {
    mockSend.mockResolvedValueOnce({});
    const ok = await putServerSettings(
      "user@x.com",
      { watchlist: ["US"], trendFocus: null },
      "2026-07-12T00:00:00Z"
    );
    expect(ok).toBe(true);
    const cmd = mockSend.mock.calls[0][0];
    expect(cmd).toBeInstanceOf(PutItemCommand);
    expect(cmd.input.Item.email.S).toBe("user@x.com");
    expect(cmd.input.Item.updated_at.S).toBe("2026-07-12T00:00:00Z");
    expect(JSON.parse(cmd.input.Item.settings.S).watchlist).toEqual(["US"]);
  });

  it("returns false on a DDB error", async () => {
    mockSend.mockRejectedValueOnce(new Error("boom"));
    expect(await putServerSettings("a@b.com", DEFAULT_SETTINGS, "t")).toBe(false);
  });

  it("returns false for empty email without touching DDB", async () => {
    expect(await putServerSettings("", DEFAULT_SETTINGS, "t")).toBe(false);
    expect(mockSend).not.toHaveBeenCalled();
  });
});
