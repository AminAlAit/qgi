"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import {
  type UserSettings,
  getSettingsSnapshot,
  getServerSettingsSnapshot,
  subscribeSettings,
  updateSettings,
  applyServerSettings,
} from "@/lib/user-settings";
import { loadSettingsAction, saveSettingsAction } from "@/lib/settings-actions";

/**
 * React hook over the per-user settings store.
 *
 * - Instant reads/writes come from the localStorage-backed store (SSR-safe via
 *   useSyncExternalStore; returns defaults on the server, hydrates on client).
 * - On mount (client), it reconciles with the server (DynamoDB): a signed-in
 *   user's server row wins; if they have no row yet, the current local settings
 *   seed the server. That's what makes settings follow the user across devices.
 * - Writes update locally immediately, then persist to the server debounced
 *   (so dragging a slider doesn't spam writes). Server persistence is
 *   best-effort — if it fails/offline, localStorage still holds the value.
 */
export function useUserSettings(): {
  settings: UserSettings;
  update: (patch: Partial<UserSettings>) => void;
} {
  const settings = useSyncExternalStore(
    subscribeSettings,
    getSettingsSnapshot,
    getServerSettingsSnapshot
  );
  const loadedRef = useRef(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    loadSettingsAction()
      .then((server) => {
        if (server) {
          applyServerSettings(server); // server is the source of truth
        } else {
          // No server row yet (or signed out — then this no-ops): seed from local.
          void saveSettingsAction(getSettingsSnapshot()).catch(() => {});
        }
      })
      .catch(() => {
        /* offline — the localStorage store already has the values */
      });
    // NOTE: deliberately no unmount cleanup that clears saveTimer. A pending
    // debounced save must survive unmount — navigating away within 500ms of an
    // edit (add a country, click a nav link) is an ordinary flow, and canceling
    // the timer there would silently drop the DynamoDB write (localStorage would
    // still show it as "saved", breaking cross-device sync). The timeout
    // callback is a fire-and-forget server action with no setState, so it's safe
    // after unmount. The only cancellation we want is update() replacing a prior
    // pending timer with a newer one, which it does itself.
  }, []);

  const update = useCallback((patch: Partial<UserSettings>) => {
    const next = updateSettings(patch); // instant local + localStorage
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      void saveSettingsAction(next).catch(() => {});
    }, 500);
  }, []);

  return { settings, update };
}
