"use client";

/**
 * IndicatorsTable — the indicators counterpart to EventsTable. A searchable,
 * filterable list of every active in-play indicator (data/indicator-catalog.json):
 * provider + theme dropdowns, fulltext search on name/code, and a row count.
 */
import { useMemo, useState } from "react";
import catalog from "@/data/indicator-catalog.json";
import { PROVIDER_COLOR } from "@/lib/indicator-providers";

interface CatalogEntry {
  code: string;
  name: string;
  provider: string;
  theme: string;
  description?: string;
  recipe_count?: number;
  in_play?: boolean;
}

export default function IndicatorsTable() {
  const all = (catalog as { indicators: CatalogEntry[] }).indicators;

  const providers = useMemo(
    () => Array.from(new Set(all.map((e) => e.provider))).sort(),
    [all]
  );
  const themes = useMemo(
    () => Array.from(new Set(all.map((e) => e.theme))).sort(),
    [all]
  );

  const [provider, setProvider] = useState("");
  const [theme, setTheme] = useState("");
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return all.filter((e) => {
      if (provider && e.provider !== provider) return false;
      if (theme && e.theme !== theme) return false;
      if (q && !e.name.toLowerCase().includes(q) && !e.code.toLowerCase().includes(q))
        return false;
      return true;
    });
  }, [all, provider, theme, search]);

  const selectStyle = {
    backgroundColor: "var(--qgi-bg)",
    border: "1px solid var(--qgi-border)",
    color: "var(--qgi-text)",
  } as const;

  return (
    <div>
      <div className="flex flex-wrap gap-3 mb-5 items-end">
        <div className="flex-1 min-w-[200px]">
          <label htmlFor="ind-search" className="sr-only">
            Search indicators
          </label>
          <input
            id="ind-search"
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name or code…"
            className="w-full px-3 py-2 rounded text-sm outline-none focus:border-[var(--qgi-accent)]"
            style={selectStyle}
          />
        </div>
        <div>
          <label htmlFor="ind-provider" className="sr-only">
            Filter by provider
          </label>
          <select
            id="ind-provider"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="px-3 py-2 rounded text-sm outline-none"
            style={selectStyle}
          >
            <option value="">All providers</option>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="ind-theme" className="sr-only">
            Filter by theme
          </label>
          <select
            id="ind-theme"
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            className="px-3 py-2 rounded text-sm outline-none"
            style={selectStyle}
          >
            <option value="">All themes</option>
            {themes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      <p
        className="text-[11px] tracking-wider uppercase mb-3"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        {filtered.length} of {all.length} indicators
      </p>

      <div
        className="rounded-lg border overflow-hidden"
        style={{ borderColor: "var(--qgi-border)" }}
      >
        {filtered.map((e, i) => (
          <div
            key={e.code}
            className="px-4 py-3 grid gap-3 items-start"
            style={{
              gridTemplateColumns: "minmax(0,1fr) auto",
              borderBottom:
                i < filtered.length - 1 ? "1px solid var(--qgi-border)" : "none",
              backgroundColor: i % 2 ? "var(--qgi-surface)" : "transparent",
            }}
          >
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{
                    color: PROVIDER_COLOR[e.provider] || "var(--qgi-text-muted)",
                    border: `1px solid ${PROVIDER_COLOR[e.provider] || "var(--qgi-border)"}40`,
                  }}
                >
                  {e.provider}
                </span>
                <span
                  className="text-sm font-medium"
                  style={{ color: "var(--qgi-text)" }}
                >
                  {e.name}
                </span>
                <code className="text-[10px]" style={{ color: "var(--qgi-text-dim)" }}>
                  {e.code}
                </code>
              </div>
              {e.description && (
                <p
                  className="text-[12px] mt-1 leading-snug max-w-2xl"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  {e.description}
                </p>
              )}
            </div>
            <div className="text-right">
              <div
                className="text-[10px] tracking-wider uppercase"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                {e.theme}
              </div>
              <div
                className="text-[11px] mt-0.5"
                style={{
                  color:
                    (e.recipe_count || 0) > 0
                      ? "var(--qgi-accent)"
                      : "var(--qgi-text-dim)",
                }}
              >
                {(e.recipe_count || 0) > 0
                  ? `${e.recipe_count} trend${e.recipe_count === 1 ? "" : "s"}`
                  : "tracked"}
              </div>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div
            className="px-4 py-8 text-center text-sm"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            No indicators match those filters.
          </div>
        )}
      </div>
    </div>
  );
}
