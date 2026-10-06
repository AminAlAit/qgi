/**
 * InsightCallouts — three stacked number+label+link callout cards.
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";

interface Callout {
  value: number;
  label: string;
  color: string;
  micro: string;
  href: Route;
  linkLabel: string;
}

interface Props {
  activeCount: number;
  silentAlarmCount: number;
  inPlayCount: number;
}

export function InsightCallouts({ activeCount, silentAlarmCount, inPlayCount }: Props) {
  const callouts: Callout[] = [
    {
      value: activeCount,
      label: "ACTIVE signals right now",
      color: "#E05C5C",
      micro:
        "Both structural resemblance and news pulse are elevated. These are the confirmed signals this vintage.",
      href: "/risk-board" as Route,
      linkLabel: "→ Risk Board",
    },
    {
      value: silentAlarmCount,
      label: "silent alarms",
      color: "#f59e0b",
      micro:
        "Structural pressure is running ahead of headlines. QGI sees it before the news does.",
      href: "/risk-board" as Route,
      linkLabel: "→ Risk Board",
    },
    {
      value: inPlayCount,
      label: "trends in play",
      color: "#7B5EE6",
      micro:
        "Event-shape patterns with structural resemblance scores across 160+ countries this release.",
      href: "/trends" as Route,
      linkLabel: "→ Trends",
    },
  ];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        height: "100%",
        boxSizing: "border-box",
      }}
    >
      {callouts.map((c) => (
        <div
          key={c.label}
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: "6px",
            padding: "16px",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderLeft: `3px solid ${c.color}`,
            borderRadius: "8px",
          }}
        >
          {/* Big number */}
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "36px",
              fontWeight: 700,
              color: c.color,
              lineHeight: 1,
              letterSpacing: "-1px",
            }}
          >
            {c.value}
          </div>
          <div
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              letterSpacing: "0.2px",
            }}
          >
            {c.label}
          </div>
          <p
            style={{
              fontSize: "12px",
              color: "var(--qgi-text-muted)",
              margin: 0,
              lineHeight: 1.5,
              flex: 1,
            }}
          >
            {c.micro}
          </p>
          <Link
            href={c.href}
            style={{
              fontSize: "11px",
              fontFamily: "ui-monospace, monospace",
              color: "var(--qgi-accent)",
              textDecoration: "none",
            }}
          >
            {c.linkLabel}
          </Link>
        </div>
      ))}
    </div>
  );
}
