"use server";

import { auth } from "@/lib/auth-config";
import { getServerSettings, putServerSettings } from "@/lib/user-settings-store";
import { sanitizeSettings, type UserSettings } from "@/lib/user-settings";

/**
 * Server actions for per-user profile settings.
 *
 * IDOR guard (required — the frontend uses ONE shared IAM credential, so IAM
 * can't bind a caller to their own row): the user's email is derived ONLY from
 * the authenticated session here, never from the client payload. The client
 * sends settings *values*; it can never name whose row to touch.
 */

/** The signed-in user's settings, or null (not signed in, or no row yet). */
export async function loadSettingsAction(): Promise<UserSettings | null> {
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return null;
  return await getServerSettings(email);
}

/** Persist the signed-in user's settings. Email comes from the session only. */
export async function saveSettingsAction(input: unknown): Promise<{ ok: boolean }> {
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return { ok: false };
  const ok = await putServerSettings(
    email,
    sanitizeSettings(input),
    new Date().toISOString()
  );
  return { ok };
}
