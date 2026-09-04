import "server-only";

import { DynamoDBClient, GetItemCommand, PutItemCommand } from "@aws-sdk/client-dynamodb";
import { type UserSettings, sanitizeSettings } from "@/lib/user-settings";
import { awsRuntimeCredentials } from "@/lib/aws-credentials";

/**
 * DynamoDB store for per-user profile settings (qgi-user-settings).
 *
 *   PK:   email : S
 *   attr: settings : S   (a JSON blob — one row per user)
 *   attr: updated_at : S
 *
 * server-only: uses the frontend reader IAM credentials (default chain, same as
 * lib/indicator-values.ts). The IAM grant is scoped to this one table; the
 * email is always supplied by the caller from the authenticated session
 * (never the client) — see lib/settings-actions.ts.
 *
 * All reads/writes pass through sanitizeSettings so a stale or tampered row can
 * never surface bad state.
 */
const REGION = process.env.AWS_REGION ?? "eu-central-1";
const TABLE = process.env.QGI_USER_SETTINGS_TABLE ?? "qgi-user-settings";

let _client: DynamoDBClient | undefined;
async function client(): Promise<DynamoDBClient> {
  if (!_client) {
    // On Vercel, federate via OIDC (AWS_ROLE_ARN); locally, undefined → the
    // default chain uses the .env.local STS creds. See lib/aws-credentials.ts.
    const credentials = await awsRuntimeCredentials();
    _client = new DynamoDBClient({
      region: REGION,
      ...(credentials ? { credentials } : {}),
    });
  }
  return _client;
}

/** Read a user's settings; null if no row yet or on any error (caller falls back). */
export async function getServerSettings(email: string): Promise<UserSettings | null> {
  if (!email) return null;
  try {
    const res = await (
      await client()
    ).send(new GetItemCommand({ TableName: TABLE, Key: { email: { S: email } } }));
    const raw = res.Item?.settings?.S;
    if (!raw) return null;
    return sanitizeSettings(JSON.parse(raw));
  } catch (err) {
    console.warn(
      "[settings] read failed:",
      (err as { name?: string })?.name ?? "UnknownError"
    );
    return null;
  }
}

/** Write a user's settings. Returns whether it persisted. */
export async function putServerSettings(
  email: string,
  settings: UserSettings,
  nowIso: string
): Promise<boolean> {
  if (!email) return false;
  try {
    await (
      await client()
    ).send(
      new PutItemCommand({
        TableName: TABLE,
        Item: {
          email: { S: email },
          settings: { S: JSON.stringify(sanitizeSettings(settings)) },
          updated_at: { S: nowIso },
        },
      })
    );
    return true;
  } catch (err) {
    console.warn(
      "[settings] write failed:",
      (err as { name?: string })?.name ?? "UnknownError"
    );
    return false;
  }
}
