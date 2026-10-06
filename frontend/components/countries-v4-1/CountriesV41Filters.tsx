"use client";

/**
 * CountriesV41Filters — region pill row + sort selector for /countries.
 *
 * Client component: controls write through to the URL via router.replace,
 * preserving the server-rendered card grouping. (Distinct from the v4
 * filters only in the base path it routes to.)
 */
import { useRouter, useSearchParams } from "next/navigation";
import { ListFilter, ArrowUpDown } from "lucide-react";

export function CountriesV41Filters({
  regions,
  activeRegion,
  activeSort,
  totalShown,
}: {
  regions: readonly string[];
  activeRegion: string;
  activeSort: "compound" | "lit" | "name";
  totalShown: number;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(searchParams.toString());
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
    const qs = next.toString();
    router.replace((qs ? `/countries?${qs}` : "/countries") as never);
  }

  return (
    <div
      style={{
        marginTop: "20px",
        padding: "14px 16px",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        display: "flex",
        gap: "16px",
        flexWrap: "wrap",
        alignItems: "center",
      }}
    >
      <div
        style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "10px",
            letterSpacing: "1.5px",
            textTransform: "uppercase",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          <ListFilter size={12} strokeWidth={1.8} />
          Region
        </span>
        <Pill
          label="All"
          active={!activeRegion}
          onClick={() => setParam("region", null)}
        />
        {regions.map((r) => (
          <Pill
            key={r}
            label={r}
            active={activeRegion === r}
            onClick={() => setParam("region", activeRegion === r ? null : r)}
          />
        ))}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          flexWrap: "wrap",
          marginLeft: "auto",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "10px",
            letterSpacing: "1.5px",
            textTransform: "uppercase",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          <ArrowUpDown size={12} strokeWidth={1.8} />
          Sort
        </span>
        <Pill
          label="Compound Risk"
          active={activeSort === "compound"}
          onClick={() => setParam("sort", "compound")}
        />
        <Pill
          label="Trends matched"
          active={activeSort === "lit"}
          onClick={() => setParam("sort", "lit")}
        />
        <Pill
          label="Name"
          active={activeSort === "name"}
          onClick={() => setParam("sort", "name")}
        />
      </div>

      <span
        style={{
          fontSize: "10.5px",
          color: "var(--qgi-text-muted)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
          width: "100%",
          textAlign: "right",
        }}
      >
        Showing {totalShown} countries
      </span>
    </div>
  );
}

function Pill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontSize: "11px",
        padding: "5px 10px",
        background: active ? "var(--qgi-accent)" : "var(--qgi-bg)",
        color: active ? "var(--qgi-bg)" : "var(--qgi-text-muted)",
        border: `1px solid ${active ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
        borderRadius: "4px",
        userSelect: "none",
        cursor: "pointer",
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.3px",
      }}
    >
      {label}
    </button>
  );
}
