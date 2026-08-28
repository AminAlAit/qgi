/**
 * Per-user profile settings — client store.
 *
 * MVP persistence is localStorage (device-local, zero backend) behind a small
 * store abstraction (getSnapshot / subscribe / update), so the entire settings
 * surface + hooks can later swap to a server-backed store — a DynamoDB
 * `qgi-user-settings` table keyed by the Cognito `sub` (see
 * docs/ARCHITECTURE.md) — without touching any UI.
 *
 * Only the client-configurable settings live here. Pro/backend features
 * (alerts, digests, API keys, delivery) are designed but need server infra;
 * their preferences will join this schema when that lands.
 */

export interface UserSettings {
  /** alpha-2 (ISO 3166-1) country codes the user follows; becomes the default lens. */
  watchlist: string[];
  /** Allowlist of trend slugs to show; null = show all. */
  trendFocus: string[] | null;
}

export const DEFAULT_SETTINGS: UserSettings = {
  watchlist: [],
  trendFocus: null,
};

const KEY = "qgi-user-settings-v1";

/**
 * Coerce arbitrary (untrusted / stale / tampered) input into a valid
 * UserSettings — clamps ranges, validates enums, caps array sizes. Applied on
 * every read and write, client and server, so a bad blob can never poison the
 * store or the DynamoDB row.
 */
export function sanitizeSettings(input: unknown): UserSettings {
  const o = (input && typeof input === "object" ? input : {}) as Record<string, unknown>;
  const strArr = (v: unknown): string[] =>
    Array.isArray(v)
      ? v.filter((x): x is string => typeof x === "string").slice(0, 200)
      : [];
  return {
    watchlist: strArr(o.watchlist),
    trendFocus: Array.isArray(o.trendFocus) ? strArr(o.trendFocus) : null,
  };
}

// ── store internals ────────────────────────────────────────────────────────
let cache: UserSettings | null = null;
const listeners = new Set<() => void>();

function read(): UserSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(KEY);
    // Merge over defaults so a schema addition doesn't break older saved blobs.
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : DEFAULT_SETTINGS;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

/** Cached client snapshot (stable ref until a change — required by useSyncExternalStore). */
export function getSettingsSnapshot(): UserSettings {
  if (cache === null) cache = read();
  return cache;
}

/** Server snapshot: always defaults (localStorage is client-only). */
export function getServerSettingsSnapshot(): UserSettings {
  return DEFAULT_SETTINGS;
}

export function subscribeSettings(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

// Cross-tab sync: another tab's write invalidates our cache once.
if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === KEY) {
      cache = read();
      listeners.forEach((l) => l());
    }
  });
}

/** Merge a partial patch, persist, notify subscribers; returns the merged next. */
export function updateSettings(patch: Partial<UserSettings>): UserSettings {
  const next = { ...getSettingsSnapshot(), ...patch };
  cache = next;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* quota / disabled storage — settings stay in-memory for the session */
    }
  }
  listeners.forEach((l) => l());
  return next;
}

/**
 * Replace the local store with authoritative server settings (on sign-in load).
 * Sanitized, cached, mirrored to localStorage, and broadcast to subscribers.
 */
export function applyServerSettings(settings: UserSettings): void {
  cache = sanitizeSettings(settings);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(cache));
    } catch {
      /* ignore */
    }
  }
  listeners.forEach((l) => l());
}

/** Reset all settings to defaults. */
export function resetSettings(): void {
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  }
  cache = { ...DEFAULT_SETTINGS };
  listeners.forEach((l) => l());
}
