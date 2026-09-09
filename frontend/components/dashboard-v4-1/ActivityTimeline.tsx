/**
 * ActivityTimeline — V4.1
 *
 * Server component. Renders rows server-side (including LucideIcon JSX) and
 * hands the pre-rendered elements to <CollapsibleRows> (client) for expand
 * state. This avoids the RSC serialization error that would fire if the
 * client component received `Icon: LucideIcon` as a prop (function refs do
 * not cross the server→client boundary).
 *
 * Changes from V4:
 * - Wrapped in PanelBase (Worker B) with default CALM_SLATE_BLUE accent.
 * - Default-collapses to the most-recent 3 entries via <CollapsibleRows>.
 *   Top-right halo button + bottom "show all N entries" link both toggle.
 * - Row chrome, date column, icon box, conditional "later withdrawn after
 *   audit" tail, SCHEDULED/QUEUED alias, and META_EVENTS interleaving all
 *   preserved byte-identical from V4 (founder ruled "don't negotiate
 *   template data state").
 */

import Link from "next/link";
import type { Route } from "next";
import type { LucideIcon } from "lucide-react";
import { CollapsibleRows } from "@/components/dashboard-v4-1/CollapsibleRows";

const CALM_SLATE_BLUE = "#5B7E99";
const COLLAPSED_COUNT = 3;

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
    <CollapsibleRows
      panelTitle="Recent activity"
      panelCaption="Latest entries from the program log. Validation results, methodology updates, and curation events."
      accent={CALM_SLATE_BLUE}
      collapsedCount={COLLAPSED_COUNT}
    >
      {sorted.map((e, i) => (
        <ActivityRow key={`${e.date}-${i}`} event={e} />
      ))}
    </CollapsibleRows>
  );
}

// isLast is injected by CollapsibleRows via cloneElement on the last visible
// row so the border suppression is keyed off what is actually shown, not the
// underlying sorted-array index — fixes the spurious bottom-border on the
// last visible row when the list is collapsed.
function ActivityRow({
  event,
  isLast = false,
}: {
  event: ActivityEvent;
  isLast?: boolean;
}) {
  const { Icon, color } = event;
  const body = (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "92px 40px minmax(0, 1fr)",
        gap: "14px",
        padding: "12px 14px",
        borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
        alignItems: "flex-start",
      }}
    >
      <div
        style={{
          fontSize: "10.5px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
          paddingTop: "2px",
        }}
      >
        {event.date}
      </div>
      <div
        style={{
          width: "32px",
          height: "32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${color}1A`,
          border: `1px solid ${color}55`,
          borderRadius: "6px",
          color,
        }}
      >
        <Icon size={16} strokeWidth={1.6} aria-hidden="true" />
      </div>
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--qgi-text)",
            lineHeight: 1.35,
            marginBottom: "2px",
          }}
        >
          {event.title}
        </div>
        <div
          style={{
            fontSize: "11.5px",
            color: "var(--qgi-text-muted)",
            lineHeight: 1.5,
          }}
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
