"use client";

import { useState } from "react";
import taxonomyData from "@/data/taxonomy_hierarchy.json";

type Layer2 = {
  id: string;
  label: string;
  definition: string;
  layer3: string[];
};

type Layer1 = {
  id: string;
  label: string;
  display_label: string;
  definition: string;
  color_hint: string;
  layer2: Layer2[];
};

type TaxonomyData = {
  version: string;
  generated: string;
  source: string;
  summary: { layer1_count: number; layer2_count: number; layer3_count: number };
  layer1: Layer1[];
};

const data = taxonomyData as TaxonomyData;

/**
 * Interactive expandable taxonomy viz for the methodology page.
 * Layer 1 (8 cards) → Layer 2 (~52 sub-categories) → Layer 3 (71 canonical event types).
 * Layer 4 (~12K individual event titles) is not surfaced here — it's per-country and lives on the country profile page.
 */
export default function LayeredTaxonomyTree() {
  const [openL1, setOpenL1] = useState<string | null>(null);
  const [openL2, setOpenL2] = useState<string | null>(null);

  return (
    <div className="my-6">
      {/* Summary header */}
      <div
        className="rounded-lg border p-4 mb-4 text-xs"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
          color: "var(--qgi-text-muted)",
        }}
      >
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat value="8" label="Master groups" sub="Layer 1" />
          <Stat value="52" label="Sub-categories" sub="Layer 2" />
          <Stat value="71" label="Cardinal types" sub="Layer 3" />
          <Stat value="~12K" label="Event records" sub="Layer 4 (not shown)" />
        </div>
        <div className="mt-3 text-[11px] leading-relaxed">
          Click a master group to expand its sub-categories. Click a sub-category to see
          the canonical Layer 3 event types that map into it.
        </div>
      </div>

      {/* Layer 1 grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {data.layer1.map((l1) => {
          const isOpen = openL1 === l1.id;
          return (
            <button
              key={l1.id}
              onClick={() => {
                setOpenL1(isOpen ? null : l1.id);
                setOpenL2(null);
              }}
              className="text-left rounded-lg border p-3 transition-all hover:border-[var(--qgi-accent)]"
              style={{
                backgroundColor: isOpen ? "var(--qgi-accent-glow)" : "var(--qgi-surface)",
                borderTopColor: isOpen ? "var(--qgi-accent)" : "var(--qgi-border)",
                borderRightColor: isOpen ? "var(--qgi-accent)" : "var(--qgi-border)",
                borderBottomColor: isOpen ? "var(--qgi-accent)" : "var(--qgi-border)",
                borderLeftWidth: 3,
                borderLeftColor: l1.color_hint,
              }}
              aria-expanded={isOpen}
            >
              <div
                className="text-[10px] font-semibold tracking-wider uppercase"
                style={{ color: l1.color_hint }}
              >
                {l1.id}
              </div>
              <div
                className="text-sm font-medium mt-1"
                style={{ color: "var(--qgi-text)" }}
              >
                {l1.display_label}
              </div>
              <div className="text-[10px] mt-1" style={{ color: "var(--qgi-text-dim)" }}>
                {l1.layer2.length} sub-categories
              </div>
            </button>
          );
        })}
      </div>

      {/* Layer 2 expansion (renders when an L1 card is open) */}
      {openL1 && (
        <div
          className="mt-4 rounded-lg border p-4"
          style={{
            backgroundColor: "var(--qgi-surface)",
            borderColor: "var(--qgi-border)",
          }}
        >
          {(() => {
            const l1 = data.layer1.find((x) => x.id === openL1)!;
            return (
              <>
                <div className="mb-3">
                  <div
                    className="text-[10px] tracking-widest uppercase"
                    style={{ color: l1.color_hint }}
                  >
                    {l1.label}
                  </div>
                  <p
                    className="text-xs mt-1 leading-relaxed"
                    style={{ color: "var(--qgi-text-muted)" }}
                  >
                    {l1.definition}
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {l1.layer2.map((l2) => {
                    const l2Open = openL2 === l2.id;
                    return (
                      <div key={l2.id}>
                        <button
                          onClick={() => setOpenL2(l2Open ? null : l2.id)}
                          className="w-full text-left rounded border px-3 py-2 transition-colors hover:border-[var(--qgi-accent)]"
                          style={{
                            backgroundColor: l2Open
                              ? "var(--qgi-accent-glow)"
                              : "transparent",
                            borderColor: l2Open
                              ? "var(--qgi-accent)"
                              : "var(--qgi-border)",
                          }}
                          aria-expanded={l2Open}
                        >
                          <div className="flex items-baseline justify-between gap-2">
                            <span
                              className="text-xs font-medium"
                              style={{ color: "var(--qgi-text)" }}
                            >
                              {l2.label}
                            </span>
                            <span
                              className="text-[10px] font-mono"
                              style={{ color: "var(--qgi-text-dim)" }}
                            >
                              {l2.layer3.length} type{l2.layer3.length === 1 ? "" : "s"}
                            </span>
                          </div>
                          <div
                            className="text-[10px] mt-1 leading-relaxed"
                            style={{ color: "var(--qgi-text-muted)" }}
                          >
                            {l2.definition}
                          </div>
                        </button>

                        {/* Layer 3 codes inline */}
                        {l2Open && (
                          <div
                            className="mt-1 ml-2 pl-3 border-l text-[11px] py-2"
                            style={{
                              borderColor: l1.color_hint,
                              color: "var(--qgi-text-muted)",
                            }}
                          >
                            <div
                              className="text-[9px] tracking-widest uppercase mb-1"
                              style={{ color: "var(--qgi-text-dim)" }}
                            >
                              Layer 3 canonical types
                            </div>
                            {l2.layer3.map((code) => (
                              <code
                                key={code}
                                className="inline-block mr-1 mb-1 px-2 py-0.5 rounded font-mono text-[10px]"
                                style={{
                                  backgroundColor: "var(--qgi-bg)",
                                  border: "1px solid var(--qgi-border)",
                                  color: "var(--qgi-accent)",
                                }}
                              >
                                {code}
                              </code>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* Footer attribution */}
      <div
        className="mt-3 text-[10px] tracking-wide"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Source: <code className="font-mono">qgi-data/events/taxonomy_hierarchy.json</code>{" "}
        · Generated {data.generated} · Approved per{" "}
        <code className="font-mono">event-taxonomy-layered-design.md</code>
      </div>
    </div>
  );
}

function Stat({ value, label, sub }: { value: string; label: string; sub: string }) {
  return (
    <div className="text-center">
      <div className="font-data text-xl font-bold" style={{ color: "var(--qgi-accent)" }}>
        {value}
      </div>
      <div className="text-[11px] font-medium" style={{ color: "var(--qgi-text)" }}>
        {label}
      </div>
      <div className="text-[9px]" style={{ color: "var(--qgi-text-dim)" }}>
        {sub}
      </div>
    </div>
  );
}
