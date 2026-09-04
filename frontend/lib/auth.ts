import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";
import { NextRequest, NextResponse } from "next/server";

const USER_POOL_ID = process.env.COGNITO_USER_POOL_ID;
const REGION = process.env.AWS_REGION ?? "eu-central-1";

function getJwksUri(): string {
  if (!USER_POOL_ID) throw new Error("COGNITO_USER_POOL_ID env var not set");
  return `https://cognito-idp.${REGION}.amazonaws.com/${USER_POOL_ID}/.well-known/jwks.json`;
}

// Lazily initialised — module-level singleton
let _jwks: ReturnType<typeof createRemoteJWKSet> | null = null;
function getJwks() {
  if (!_jwks) _jwks = createRemoteJWKSet(new URL(getJwksUri()));
  return _jwks;
}

export interface AuthPayload extends JWTPayload {
  "cognito:groups"?: string[];
  email?: string;
}

/**
 * Verify a Cognito JWT from the Authorization header.
 * Returns the decoded payload or throws on invalid/missing token.
 */
export async function verifyToken(req: NextRequest): Promise<AuthPayload> {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    throw new AuthError(401, "Missing or malformed Authorization header");
  }
  const token = auth.slice(7);
  const { payload } = await jwtVerify(token, getJwks(), {
    issuer: `https://cognito-idp.${REGION}.amazonaws.com/${USER_POOL_ID}`,
    audience: process.env.COGNITO_CLIENT_ID,
  });
  return payload as AuthPayload;
}

export class AuthError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
  }
}

/**
 * Middleware wrapper for data API routes.
 * Handles auth errors and returns JSON 401/403.
 */
export function withAuth(
  handler: (req: NextRequest, payload: AuthPayload) => Promise<NextResponse>
) {
  return async (req: NextRequest): Promise<NextResponse> => {
    // Skip auth in local dev when SKIP_AUTH=true. Dev payload's group list
    // is driven by SKIP_AUTH_GROUPS (comma-separated) so local devs can
    // opt into pro-gated routes explicitly without the shim silently
    // granting pro access in production (#445). If SKIP_AUTH_GROUPS is
    // unset, dev payload has zero groups — requireGroup("pro") will 403,
    // which is the correct behavior for prod where SKIP_AUTH is set but
    // no real Cognito group membership exists.
    //
    // Bug fix (#425 follow-up): both branches must share the same
    // try/catch so AuthError thrown INSIDE the handler (e.g. from
    // `requireGroup()`) surfaces as a clean 403/401 JSON response
    // instead of an unhandled 500 with empty body. The original code
    // had SKIP_AUTH returning `handler(req, ...)` directly, which meant
    // thrown AuthErrors escaped the wrapper and Next returned HTTP 500.
    try {
      let payload: AuthPayload;
      if (process.env.SKIP_AUTH === "true") {
        const devGroups = (process.env.SKIP_AUTH_GROUPS ?? "")
          .split(",")
          .map((g) => g.trim())
          .filter(Boolean);
        payload = {
          sub: "dev",
          "cognito:groups": devGroups,
        } as AuthPayload;
      } else {
        payload = await verifyToken(req);
      }
      return await handler(req, payload);
    } catch (err) {
      if (err instanceof AuthError) {
        return NextResponse.json({ error: err.message }, { status: err.status });
      }
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  };
}

export function requireGroup(payload: AuthPayload, group: string): void {
  const groups = payload["cognito:groups"] ?? [];
  if (!groups.includes(group)) {
    throw new AuthError(403, `Requires ${group} plan`);
  }
}
