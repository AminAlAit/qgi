/**
 * lib/settings-actions.ts — the IDOR guard is the point of these tests:
 * the user's email must come ONLY from the authenticated session, never from
 * the client payload.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockAuth, mockGet, mockPut } = vi.hoisted(() => ({
  mockAuth: vi.fn(),
  mockGet: vi.fn(),
  mockPut: vi.fn(),
}));
vi.mock("@/lib/auth-config", () => ({ auth: mockAuth }));
vi.mock("@/lib/user-settings-store", () => ({
  getServerSettings: mockGet,
  putServerSettings: mockPut,
}));

const { loadSettingsAction, saveSettingsAction } = await import("@/lib/settings-actions");

beforeEach(() => {
  mockAuth.mockReset();
  mockGet.mockReset();
  mockPut.mockReset();
});

describe("saveSettingsAction — IDOR guard", () => {
  it("writes to the SESSION email, ignoring any client-supplied email in the payload", async () => {
    mockAuth.mockResolvedValueOnce({ user: { email: "real@user.com" } });
    mockPut.mockResolvedValueOnce(true);
    // Attacker crams a victim email into the payload — it must be ignored.
    const res = await saveSettingsAction({
      email: "victim@other.com",
      watchlist: ["US"],
    });
    expect(res.ok).toBe(true);
    expect(mockPut).toHaveBeenCalledTimes(1);
    expect(mockPut.mock.calls[0][0]).toBe("real@user.com"); // email arg = session
    // and the injected email field is stripped from the persisted settings
    expect(mockPut.mock.calls[0][1]).not.toHaveProperty("email");
    expect(mockPut.mock.calls[0][1].watchlist).toEqual(["US"]);
  });

  it("is a no-op when signed out", async () => {
    mockAuth.mockResolvedValueOnce(null);
    const res = await saveSettingsAction({ watchlist: ["US"] });
    expect(res.ok).toBe(false);
    expect(mockPut).not.toHaveBeenCalled();
  });
});

describe("loadSettingsAction", () => {
  it("reads the session email; null (no DDB call) when signed out", async () => {
    mockAuth.mockResolvedValueOnce(null);
    expect(await loadSettingsAction()).toBeNull();
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("reads the session user's row when signed in", async () => {
    mockAuth.mockResolvedValueOnce({ user: { email: "real@user.com" } });
    mockGet.mockResolvedValueOnce(null);
    await loadSettingsAction();
    expect(mockGet.mock.calls[0][0]).toBe("real@user.com");
  });
});
