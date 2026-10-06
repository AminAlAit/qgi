"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ListFilter, Layers } from "lucide-react";
import { L1_FAMILIES as L1_FAMILY_MAP, familyColor } from "@/lib/te-mock/l1-families";

const L1_FAMILIES = Object.values(L1_FAMILY_MAP).map((f) => ({
  id: f.id,
  label: f.label,
  color: familyColor(f.id),
}));

interface Props {
  minThreshold: number;
  familyFilter: string[];
}

export function CompoundFilters({ minThreshold, familyFilter }: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [localMin, setLocalMin] = useState<number>(minThreshold);
  const [localFams, setLocalFams] = useState<Set<string>>(new Set(familyFilter));

  useEffect(() => {
    setLocalMin(minThreshold);
  }, [minThreshold]);
  useEffect(() => {
    setLocalFams(new Set(familyFilter));
  }, [familyFilter]);

  const push = useCallback(
    (min: number, fams: Set<string>) => {
      const next = new URLSearchParams(searchParams.toString());
      next.set("min", String(min));
      if (fams.size > 0) next.set("families", Array.from(fams).sort().join(","));
      else next.delete("families");
      router.replace(`/compound-risk?${next.toString()}` as never, { scroll: false });
    },
    [router, searchParams]
  );

  const setMin = (v: number) => {
    setLocalMin(v);
    push(v, localFams);
  };
  const toggleFam = (id: string) => {
    const next = new Set(localFams);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setLocalFams(next);
    push(localMin, next);
  };
  const clearFams = () => {
    setLocalFams(new Set());
    push(localMin, new Set());
  };

  return (
    <div
      style={{
        marginTop: "24px",
        padding: "16px",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
      }}
    >
      {/* Threshold row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
          flexWrap: "wrap",
          marginBottom: "14px",
          paddingBottom: "14px",
          borderBottom: "1px solid var(--qgi-border)",
        }}
      >
        <Layers size={14} color="var(--qgi-text-dim)" strokeWidth={1.7} />
        <span
          style={{
            fontSize: "10px",
            letterSpacing: "1.5px",
            textTransform: "uppercase",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          Minimum recipes matched
        </span>
        {[2, 3, 4].map((n) => {
          const active = n === localMin;
          return (
            <button
              key={n}
              type="button"
              aria-pressed={active}
              onClick={() => setMin(n)}
              style={{
                fontSize: "12px",
                padding: "5px 14px",
                background: active ? "var(--qgi-accent)" : "var(--qgi-bg)",
                color: active ? "var(--qgi-bg)" : "var(--qgi-text-muted)",
                border: `1px solid ${active ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
                borderRadius: "4px",
                cursor: "pointer",
                fontFamily: "ui-monospace, monospace",
                fontWeight: 600,
                letterSpacing: "0.3px",
              }}
            >
              ≥{n}
            </button>
          );
        })}
        <span style={{ flex: 1 }} />
        <span
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
            fontStyle: "italic",
          }}
        >
          Tighter threshold ⇒ fewer, harder-stacked cases
        </span>
      </div>

      {/* Family row */}
      <div
        style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}
      >
        <ListFilter size={14} color="var(--qgi-text-dim)" strokeWidth={1.7} />
        <span
          style={{
            fontSize: "10px",
            letterSpacing: "1.5px",
            textTransform: "uppercase",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          Threat-family overlap (all selected)
        </span>
        {L1_FAMILIES.map((f) => {
          const active = localFams.has(f.id);
          return (
            <button
              key={f.id}
              type="button"
              aria-pressed={active}
              onClick={() => toggleFam(f.id)}
              title={f.label}
              style={{
                fontSize: "11px",
                padding: "4px 10px",
                background: active ? f.color : "var(--qgi-bg)",
                color: active ? "var(--qgi-bg)" : f.color,
                border: `1px solid ${f.color}`,
                borderRadius: "4px",
                cursor: "pointer",
                fontFamily: "ui-monospace, monospace",
                fontWeight: 600,
                letterSpacing: "0.4px",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <span
                style={{
                  width: "6px",
                  height: "6px",
                  borderRadius: "50%",
                  background: active ? "var(--qgi-bg)" : f.color,
                }}
              />
              {f.label}
            </button>
          );
        })}
        {localFams.size > 0 && (
          <button
            type="button"
            onClick={clearFams}
            style={{
              fontSize: "10.5px",
              padding: "4px 10px",
              background: "transparent",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "4px",
              cursor: "pointer",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
            }}
          >
            clear ×
          </button>
        )}
      </div>
    </div>
  );
}
