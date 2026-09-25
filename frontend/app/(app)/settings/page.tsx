"use client";

import { useSession, signOut } from "next-auth/react";
import { LogOut } from "lucide-react";
import { useUserSettings } from "@/components/settings/useUserSettings";
import { WatchlistPicker } from "@/components/settings/WatchlistPicker";
import { TrendFocusPicker } from "@/components/settings/TrendFocusPicker";

/**
 * Account & personalization settings. Reached from the top-right avatar menu.
 *
 * Personalization is persisted per-device (localStorage) via useUserSettings;
 * the store is abstracted so it can later move to a server store keyed by the
 * Cognito sub (see docs/profile-features-design-2026-07-11.md). Catalog-backed
 * controls (Watchlist, Trend focus) and the Pro alerting features land in
 * follow-up slices.
 */
export default function SettingsPage() {
  const { data: session, status } = useSession();
  const { settings, update } = useUserSettings();

  const email = session?.user?.email ?? null;
  const provider = session?.user?.provider;
  const isPro = (session?.user?.groups ?? []).includes("pro");
  const providerLabel =
    provider === "google"
      ? "Google"
      : provider === "credentials"
        ? "Email & password"
        : "—";

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-10">
      <h1 className="text-xl font-semibold" style={{ color: "var(--qgi-text)" }}>
        Settings
      </h1>
      <p className="mt-1 text-sm" style={{ color: "var(--qgi-text-muted)" }}>
        Your account and personalization for QG Intelligence.
      </p>

      {/* Account */}
      <Section title="Account">
        <Row
          label="Email"
          value={status === "loading" ? "…" : (email ?? "Not signed in")}
        />
        <Divider />
        <Row label="Sign-in method" value={providerLabel} />
        <Divider />
        <Row label="Plan" value={isPro ? "Pro" : "Free"} />
        <Divider />
        <div className="px-5 py-4">
          <button
            type="button"
            onClick={() => signOut({ callbackUrl: "/" })}
            className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-[13px] transition-colors hover:bg-[var(--qgi-surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)]"
            style={{
              color: "var(--qgi-text)",
              borderColor: "var(--qgi-border)",
              background: "transparent",
              cursor: "pointer",
            }}
          >
            <LogOut size={15} strokeWidth={1.75} aria-hidden="true" />
            Sign out
          </button>
        </div>
      </Section>

      {/* Personalization — live controls */}
      <Section title="Personalization">
        <div className="px-5 py-4">
          <span
            className="block text-[13px] font-medium"
            style={{ color: "var(--qgi-text)" }}
          >
            Watchlist
          </span>
          <span
            className="mb-3 block text-[12px]"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Countries you follow.{" "}
            {settings.watchlist.length > 0
              ? `${settings.watchlist.length} selected.`
              : ""}
          </span>
          <WatchlistPicker
            value={settings.watchlist}
            onChange={(next) => update({ watchlist: next })}
          />
        </div>
        <Divider />
        <div className="px-5 py-4">
          <span
            className="block text-[13px] font-medium"
            style={{ color: "var(--qgi-text)" }}
          >
            Trend focus
          </span>
          <span
            className="mb-3 block text-[12px]"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Show only the trends you act on across the Risk Board.{" "}
            {settings.trendFocus
              ? `${settings.trendFocus.length} selected.`
              : "All trends shown."}
          </span>
          <TrendFocusPicker
            value={settings.trendFocus}
            onChange={(next) => update({ trendFocus: next })}
          />
        </div>
      </Section>

      {/* Coming next */}
      <Section title="Coming next" badge="in build">
        <ul
          className="px-5 py-4 space-y-2.5 text-[13px]"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {NEXT.map((r) => (
            <li key={r.title} className="flex items-start gap-2">
              <span aria-hidden="true" style={{ color: "var(--qgi-text-dim)" }}>
                •
              </span>
              <span>
                <span style={{ color: "var(--qgi-text)" }}>{r.title}</span>
                {r.pro && (
                  <span
                    className="ml-1.5 rounded px-1 py-0.5 text-[10px]"
                    style={{
                      background: "var(--qgi-surface-2)",
                      color: "var(--qgi-accent)",
                    }}
                  >
                    Pro
                  </span>
                )}{" "}
                — {r.desc}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

const NEXT: { title: string; desc: string; pro?: boolean }[] = [
  {
    title: "Watchlist on Briefing",
    desc: "extend the watchlist lens to the Briefing surface too.",
  },
  {
    title: "Score-move alerts",
    desc: "notify when a watchlist country crosses a risk threshold.",
    pro: true,
  },
  { title: "Weekly digest", desc: "a summary scoped to your watchlist.", pro: true },
  {
    title: "API access",
    desc: "scoped tokens + bulk export for your own pipeline.",
    pro: true,
  },
];

// ── presentational helpers ──────────────────────────────────────────────────
function Section({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="mt-6 rounded-lg border"
      style={{ background: "var(--qgi-surface)", borderColor: "var(--qgi-border)" }}
    >
      <div className="px-5 py-4">
        <h2
          className="text-[13px] font-semibold uppercase tracking-wider"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {title}
          {badge && (
            <span
              className="ml-2 rounded px-1.5 py-0.5 text-[10px] font-medium tracking-normal normal-case"
              style={{ background: "var(--qgi-surface-2)", color: "var(--qgi-text-dim)" }}
            >
              {badge}
            </span>
          )}
        </h2>
      </div>
      <Divider />
      {children}
    </section>
  );
}

function Divider() {
  return <div style={{ height: 1, background: "var(--qgi-border)" }} />;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between px-5 py-3">
      <span className="text-[13px]" style={{ color: "var(--qgi-text-muted)" }}>
        {label}
      </span>
      <span className="text-[13px] font-medium" style={{ color: "var(--qgi-text)" }}>
        {value}
      </span>
    </div>
  );
}
