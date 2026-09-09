import Link from "next/link";
import type { Route } from "next";
import type { LucideIcon } from "lucide-react";

export interface ActivityEvent {
  date: string;
  kind:
    | "walk_fired"
    | "vacate"
    | "indicator_added"
    | "methodology_amendment"
    | "graduation"
    | "hard_fail"
    | "data_sync";
  title: string;
  detail: string;
  href?: string;
  Icon: LucideIcon;
  color: string;
}

export function ActivityTimeline({ events }: { events: ActivityEvent[] }) {
  const sorted = [...events].sort((a, b) => b.date.localeCompare(a.date));
  return (
    <section style={{ marginBottom: "32px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "12px",
          marginBottom: "12px",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            letterSpacing: "1.5px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text-dim)",
          }}
        >
          §03
        </span>
        <h2
          style={{
            fontSize: "16px",
            fontWeight: 600,
            margin: 0,
            color: "var(--qgi-text)",
            flex: 1,
          }}
        >
          Recent activity
        </h2>
        <span
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-muted)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          newest first · past-tense only
        </span>
      </div>
      <div
        style={{
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          background: "var(--qgi-surface)",
          overflow: "hidden",
        }}
      >
        {sorted.map((e, i) => (
          <ActivityRow
            key={`${e.date}-${i}`}
            event={e}
            isLast={i === sorted.length - 1}
          />
        ))}
      </div>
    </section>
  );
}

function ActivityRow({ event, isLast }: { event: ActivityEvent; isLast: boolean }) {
  const { Icon, color } = event;
  const body = (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "92px 40px minmax(0, 1fr)",
        gap: "14px",
        alignItems: "center",
        padding: "12px 14px",
        borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
        background: "var(--qgi-surface)",
        transition: "background 0.15s",
      }}
    >
      <div
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "10.5px",
          color: "var(--qgi-text-dim)",
          letterSpacing: "0.4px",
          whiteSpace: "nowrap",
        }}
      >
        {event.date}
      </div>

      <div
        aria-hidden="true"
        style={{
          width: "32px",
          height: "32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: `1px solid ${color}`,
          borderRadius: "5px",
          background: "var(--qgi-bg)",
          color,
          flexShrink: 0,
        }}
      >
        <Icon size={16} strokeWidth={1.7} />
      </div>

      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--qgi-text)",
            lineHeight: 1.3,
            marginBottom: "2px",
          }}
        >
          {event.title}
        </div>
        <div
          style={{ fontSize: "11.5px", color: "var(--qgi-text-muted)", lineHeight: 1.4 }}
        >
          {event.detail}
        </div>
      </div>
    </div>
  );

  if (event.href) {
    return (
      <Link
        href={event.href as Route}
        style={{ textDecoration: "none", color: "inherit", display: "block" }}
      >
        {body}
      </Link>
    );
  }
  return body;
}
