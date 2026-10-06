/**
 * (terminal) route group — the full-bleed "pro terminal" shell.
 *
 * Unlike (app), this group renders NO sidebar/nav: the Live Pulse terminal is
 * a full-screen takeover (founder 2026-06-13, matching the :8761 prototype
 * `qgi-console/pulse.html`). The page owns the whole viewport — its own
 * header, its own back button. Theme still works without a provider: useTheme
 * reads the <html> class via useSyncExternalStore. The root layout already
 * supplies fonts, globals.css and the no-flash theme script.
 */
export default function TerminalLayout({ children }: { children: React.ReactNode }) {
  return <div className="h-full">{children}</div>;
}
