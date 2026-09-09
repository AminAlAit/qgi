/**
 * WorldActivity — V4.1 confidence-first dashboard.
 *
 * Replaces the R&D-internal walk feed with audience-facing rows describing
 * what is moving in the world this vintage:
 *   - Country movements (top countries by compound score)
 *   - Recipe top-10 shifts (leaders per recipe)
 *   - Analog spotlights (best historical resemblances)
 *
 * Server component. The icon is resolved on the server (LucideIcon function
 * ref does not cross the RSC boundary), pre-rendered into JSX, then handed
 * to <CollapsibleRows> (client) for collapse state. Same pattern as V4.1
 * ActivityTimeline so the harness is familiar.
 */

import Link from "next/link";
import type { Route } from "next";
import { CollapsibleRows } from "@/components/dashboard-v4-1/CollapsibleRows";
import {
  ICON_FOR_ACTIVITY_KEY,
  type WorldActivityRow,
} from "@/lib/te-mock/dashboard-v4-1-data";

const CALM_SLATE_BLUE = "#5B7E99";
const COLLAPSED_COUNT = 5;

export function WorldActivity({ rows }: { rows: WorldActivityRow[] }) {
  return (
    <CollapsibleRows
      panelTitle="What's Moving This Release"
      panelCaption="Country movements, trend leaders, and historical resemblances pulled from the current scoring run."
      accent={CALM_SLATE_BLUE}
      collapsedCount={COLLAPSED_COUNT}
    >
      {rows.map((r, i) => (
        <Row key={`${r.kind}-${i}`} row={r} />
      ))}
    </CollapsibleRows>
  );
}

// isLast is injected by CollapsibleRows on the last visible row.
// IMPORTANT: `isLast` must be destructured here and used ONLY for styling.
// It must NOT be forwarded to <Link> or any DOM element — doing so produces
// a React "unrecognized prop on DOM element" console error on every mount.
function Row({ row, isLast = false }: { row: WorldActivityRow; isLast?: boolean }) {
  const Icon = ICON_FOR_ACTIVITY_KEY[row.iconKey];
  const body = (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "40px minmax(0, 1fr)",
        gap: "14px",
        padding: "12px 14px",
        borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
        alignItems: "flex-start",
      }}
    >
      <div
        style={{
          width: "32px",
          height: "32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${row.color}1A`,
          border: `1px solid ${row.color}55`,
          borderRadius: "6px",
          color: row.color,
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
          {row.title}
        </div>
        <div
          style={{
            fontSize: "11.5px",
            color: "var(--qgi-text-muted)",
            lineHeight: 1.5,
          }}
        >
          {row.detail}
        </div>
      </div>
    </div>
  );

  // `isLast` is consumed above for border suppression; it is NOT passed to
  // <Link> so React never forwards it to the underlying <a> DOM element.
  return (
    <Link
      href={row.href as Route}
      style={{ textDecoration: "none", color: "inherit", display: "block" }}
    >
      {body}
    </Link>
  );
}
