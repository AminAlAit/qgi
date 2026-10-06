"use client";

/**
 * CollapsibleRows — thin client wrapper that owns the expand/collapse state
 * for a list of pre-rendered server rows. Lives outside ActivityTimeline so
 * the parent can stay a server component (and pass LucideIcon function refs
 * server-side without crossing the RSC boundary — that boundary cannot
 * serialize function references).
 *
 * Pattern: pass already-rendered React elements as children. The client
 * wrapper only slices them; no event-data props with function refs cross the
 * server→client edge.
 */

import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { PanelBase } from "@/components/dashboard-v4-1/PanelBase";

const CALM_SLATE_BLUE = "#5B7E99";

export interface CollapsibleRowsProps {
  panelTitle: string;
  panelCaption?: string;
  accent?: string;
  collapsedCount: number;
  children: ReactNode;
}

export function CollapsibleRows({
  panelTitle,
  panelCaption,
  accent = CALM_SLATE_BLUE,
  collapsedCount,
  children,
}: CollapsibleRowsProps) {
  const [expanded, setExpanded] = useState(false);
  const regionId = useId();
  const rows = Children.toArray(children);
  const total = rows.length;
  const sliced = expanded ? rows : rows.slice(0, collapsedCount);
  // Inject isLast=true into the last visible child so the bottom-border
  // suppression keys off what is actually shown, not the underlying array
  // index. The row component accepts `isLast?: boolean` and ignores any
  // extra props if it does not declare them.
  const visible = sliced.map((child, i) => {
    if (i === sliced.length - 1 && isValidElement(child)) {
      const el = child as ReactElement<{ isLast?: boolean }>;
      return cloneElement(el, { isLast: true });
    }
    return child;
  });
  const canExpand = total > collapsedCount;

  const expandButton = canExpand ? (
    <button
      type="button"
      aria-label={
        expanded ? `Collapse to ${collapsedCount} entries` : `Show all ${total} entries`
      }
      aria-expanded={expanded}
      aria-controls={regionId}
      title={expanded ? "Collapse" : "Show all"}
      onClick={() => setExpanded((v) => !v)}
      style={{
        width: "22px",
        height: "22px",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--qgi-bg)",
        border: `1px solid ${accent}55`,
        borderRadius: "4px",
        color: accent,
        cursor: "pointer",
        padding: 0,
        boxShadow: `0 0 0 3px ${accent}22`,
        transition: "box-shadow 120ms ease",
      }}
    >
      {expanded ? (
        <ChevronUp size={13} strokeWidth={1.8} aria-hidden="true" />
      ) : (
        <ChevronDown size={13} strokeWidth={1.8} aria-hidden="true" />
      )}
    </button>
  ) : undefined;

  return (
    <PanelBase
      title={panelTitle}
      caption={panelCaption}
      accent={accent}
      rightSlot={expandButton}
    >
      <div
        id={regionId}
        style={{
          border: "1px solid var(--qgi-border)",
          borderRadius: "6px",
          background: "var(--qgi-surface)",
          overflow: "hidden",
        }}
      >
        {visible}
      </div>
      {canExpand && (
        <button
          type="button"
          aria-label={
            expanded
              ? `Collapse to ${collapsedCount} entries`
              : `Show all ${total} entries`
          }
          aria-expanded={expanded}
          aria-controls={regionId}
          onClick={() => setExpanded((v) => !v)}
          style={{
            marginTop: "8px",
            display: "block",
            width: "100%",
            padding: "7px 0",
            background: "none",
            border: "none",
            cursor: "pointer",
            fontSize: "11.5px",
            color: accent,
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.4px",
            textAlign: "center",
            opacity: 0.85,
            transition: "opacity 120ms ease",
          }}
        >
          {expanded ? `collapse, showing all ${total}` : `show all ${total} entries`}
        </button>
      )}
    </PanelBase>
  );
}
