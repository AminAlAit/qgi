"use client";

/**
 * Light/dark theme hook (2026-06-10). Dark is the default; light is opt-in via
 * a `light` class on <html>. The no-flash script in app/layout.tsx applies the
 * class before paint.
 *
 * The <html> class + localStorage pair IS an external store, so this uses
 * useSyncExternalStore (no effect, no cascading-render lint, SSR snapshot is
 * "dark" to match the server-rendered :root default). All mounted instances
 * stay in sync via a custom window event — no ThemeProvider/context needed,
 * so the root layout stays a server component.
 */
import { useCallback, useSyncExternalStore } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "qgi-theme";
const CHANGE_EVENT = "qgi-themechange";

function domTheme(): Theme {
  return document.documentElement.classList.contains("light") ? "light" : "dark";
}

function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onStoreChange);
  window.addEventListener("storage", onStoreChange); // cross-tab
  return () => {
    window.removeEventListener(CHANGE_EVENT, onStoreChange);
    window.removeEventListener("storage", onStoreChange);
  };
}

export function useTheme() {
  const theme = useSyncExternalStore<Theme>(subscribe, domTheme, () => "dark");

  const setTheme = useCallback((t: Theme) => {
    document.documentElement.classList.toggle("light", t === "light");
    try {
      localStorage.setItem(STORAGE_KEY, t);
    } catch {
      // localStorage blocked (private mode) — in-memory only this session.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  const toggle = useCallback(() => {
    setTheme(domTheme() === "light" ? "dark" : "light");
  }, [setTheme]);

  return { theme, isDark: theme === "dark", setTheme, toggle };
}
