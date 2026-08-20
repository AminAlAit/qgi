import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";

/**
 * Next.js 16 Proxy (replaces middleware.ts).
 *
 * Gates the 9 canonical V4.1 product routes behind a *validated* session.
 * Landing page (/), /login, /signup, /forgot-password, and the public Live
 * Pulse terminal stay open.
 *
 * Why getToken() and not a name-only cookie check: the old check only tested
 * for the *presence* of a cookie named `authjs.session-token`, which any client
 * can forge to walk past the gate. getToken() decrypts the NextAuth JWE with
 * AUTH_SECRET and returns null unless it's a genuine, unexpired session token.
 * Next 16 runs Proxy on the Node.js runtime, so the jose/hkdf decrypt works
 * here (it did not on the old Edge middleware runtime).
 *
 * Scope note: today this proxy is the *only* live enforcement point for the
 * rendered product pages (they read baked/mock data modules, not per-user
 * data). lib/auth.ts's Bearer-token gate on 4 API routes exists but nothing
 * currently calls those routes — so the "API layer is the real boundary /
 * defense-in-depth" story is aspirational, not yet wired. Before any route
 * serves per-user or pro-gated data, add a real server-side session check at
 * the data layer (see docs/auth-implementation-plan Phase 1/3); do not rely on
 * this optimistic proxy gate alone for anything sensitive.
 *
 * SKIP_AUTH=true bypasses gating entirely (local pre-paywall dev posture).
 */
export async function proxy(request: NextRequest) {
  // Dev bypass — no gating at all when SKIP_AUTH=true.
  if (process.env.SKIP_AUTH === "true") {
    return NextResponse.next();
  }

  // NextAuth names the cookie `__Secure-authjs.session-token` over https and
  // `authjs.session-token` over http, and derives the JWE salt from that name.
  // Pick secureCookie from whichever cookie is actually present so decryption
  // uses the matching salt on both localhost (http) and prod (https) — avoids a
  // redirect loop when the request protocol and the issuing protocol differ.
  const secureCookie = request.cookies.has("__Secure-authjs.session-token");

  const token = await getToken({
    req: request,
    secret: process.env.AUTH_SECRET,
    secureCookie,
  });

  if (!token) {
    const loginUrl = new URL("/login", request.url);
    // Round-trip the caller back to where they were headed after sign-in.
    loginUrl.searchParams.set(
      "callbackUrl",
      request.nextUrl.pathname + request.nextUrl.search
    );
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/trends/:path*",
    // Gate the country profile while leaving the public Live Pulse terminal at
    // /countries/:iso/live-pulse open. Per the Next.js 16 proxy matcher rules,
    // a named param matches exactly ONE segment (rule 2: "/countries/:iso" hits
    // /countries/IRN but NOT /countries/IRN/live-pulse). We deliberately do NOT
    // add a bare "/countries": rule 5 makes bare paths start-anchored, so it
    // would also catch /countries/IRN/live-pulse and re-gate the terminal. The
    // country *list* page is non-sensitive and left ungated as the safe tradeoff.
    "/countries/:iso",
    "/risk-board/:path*",
    "/compound-risk/:path*",
    "/compare/:path*",
    "/analogues/:path*",
    "/patterns/:path*",
    "/settings/:path*",
  ],
};
