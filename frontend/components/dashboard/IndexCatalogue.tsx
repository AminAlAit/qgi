"use client";

import { useState } from "react";
import type { IndexEntry } from "@/lib/types";
import { sectorColor, sectorChipBg } from "@/lib/design";

interface Props {
  indexes: IndexEntry[];
  activeSector?: string | null;
}

export function IndexCatalogue({ indexes, activeSector }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const visible = activeSector
    ? indexes.filter((idx) => idx.sector === activeSector)
    : indexes;

  return (
    <div className="flex flex-col h-full">
      <div
        className="text-[9px] tracking-[0.2em] uppercase px-4 py-2 border-b flex gap-4"
        style={{ color: "var(--qgi-text-dim)", borderColor: "var(--qgi-border)" }}
      >
        <span className="w-6">#</span>
        <span className="flex-1">INDICATOR</span>
        <span className="w-24">SECTOR</span>
        <span className="w-20">SOURCE</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {visible.map((idx, i) => (
          <div key={`${idx.id}-${i}`}>
            <button
              onClick={() => setExpandedId(expandedId === idx.id ? null : idx.id)}
              className="w-full text-left flex items-center gap-4 px-4 py-2 border-b text-xs transition-colors hover:bg-[var(--qgi-surface-2)]"
              style={{ borderColor: "var(--qgi-border)" }}
            >
              <span
                className="w-6 font-data text-[10px] shrink-0"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                {idx.numeric_id}
              </span>
              <span className="flex-1 truncate" style={{ color: "var(--qgi-text)" }}>
                {idx.name}
              </span>
              <span
                className="w-24 shrink-0 text-[9px] rounded px-1.5 py-0.5 text-center"
                style={{
                  color: sectorColor(idx.sector),
                  backgroundColor: sectorChipBg(idx.sector),
                }}
              >
                {idx.sector.toUpperCase()}
              </span>
              <span
                className="w-20 shrink-0 text-[9px] truncate"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                {idx.org}
              </span>
            </button>
            {expandedId === idx.id && idx.description && (
              <div
                className="px-4 py-3 text-xs border-b"
                style={{
                  backgroundColor: "var(--qgi-surface-2)",
                  borderColor: "var(--qgi-border)",
                  color: "var(--qgi-text-muted)",
                }}
              >
                <p className="mb-1">{idx.description}</p>
                {idx.citation && (
                  <p className="text-[10px]" style={{ color: "var(--qgi-text-dim)" }}>
                    {idx.citation}
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
