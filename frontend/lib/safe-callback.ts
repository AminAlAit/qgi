/**
 * Post-auth redirect guard (CWE-601 open-redirect prevention).
 *
 * The auth forms sign in with `redirect: false`, which opts out of NextAuth's
 * own same-origin `redirect()` callback, then navigate manually to the
 * `callbackUrl` query param. That param is attacker-controllable
 * (`/login?callbackUrl=https://evil.example/reverify`), so it MUST be
 * constrained to a same-origin relative path before we navigate to it.
 *
 * A naive prefix check (`startsWith("/") && !startsWith("//")`) is NOT enough:
 * a leading backslash slips through (2nd char is `\`, not `/`) yet the WHATWG
 * URL parser browsers use normalizes `/\` to `//` for http(s), so
 * `window.location.href = "/\\evil.com"` navigates to https://evil.com. We
 * therefore parse the candidate against a fixed base and accept it only when
 * its resolved origin still equals that base — then return just the relative
 * path (never the origin), so even a same-origin match can't carry us off-site.
 */
export function safeCallbackUrl(
  raw: string | null | undefined,
  fallback = "/dashboard"
): string {
  // Cheap early reject: must be an explicitly-rooted path, and not the
  // protocol-relative `//host` form. `/\host` still passes here — the parser
  // below is what actually catches it.
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return fallback;
  try {
    const base = "http://localhost";
    const u = new URL(raw, base);
    if (u.origin !== base) return fallback;
    const out = u.pathname + u.search + u.hash;
    // Path normalization can collapse a leading segment and leave a `//host`
    // (or `/\host`) *pathname* even when the resolved origin is same-origin —
    // e.g. `/..//evil.com` → pathname `//evil.com`. That value is
    // protocol-relative at the `window.location.href = out` sink and would
    // navigate off-origin, so we must re-check the OUTPUT, not just the raw
    // input. (The `/\` arm is belt-and-suspenders; the parser normalizes `\`
    // to `/` in paths, so it shouldn't fire, but we don't rely on that.)
    if (out.startsWith("//") || out.startsWith("/\\")) return fallback;
    return out;
  } catch {
    return fallback;
  }
}
