"use client";

import { useMemo, useState } from "react";
import { X, Plus } from "lucide-react";
import countriesRaw from "@/data/countries.json";

type Country = { id: string; name: string; alpha_2: string };
const COUNTRIES: Country[] = (countriesRaw as Country[])
  .filter((c) => c.alpha_2 && c.name)
  .sort((a, b) => a.name.localeCompare(b.name));
const BY_CODE = new Map(COUNTRIES.map((c) => [c.alpha_2, c]));

/**
 * Searchable multi-select for the user's watchlist (country codes = alpha_2).
 * Persisted via the parent (settings.watchlist). This is the "configure" half;
 * a later slice wires the watchlist as the default lens on Risk Board / Briefing.
 */
export function WatchlistPicker({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const selected = value.map((code) => BY_CODE.get(code)).filter(Boolean) as Country[];

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return COUNTRIES.filter(
      (c) => !value.includes(c.alpha_2) && c.name.toLowerCase().includes(q)
    ).slice(0, 8);
  }, [query, value]);

  function add(code: string) {
    if (!value.includes(code)) onChange([...value, code]);
    setQuery("");
  }
  function remove(code: string) {
    onChange(value.filter((c) => c !== code));
  }

  return (
    <div className="w-full">
      {/* Selected chips */}
      {selected.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {selected.map((c) => (
            <span
              key={c.alpha_2}
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px]"
              style={{ background: "var(--qgi-surface-2)", color: "var(--qgi-text)" }}
            >
              {c.name}
              <button
                type="button"
                onClick={() => remove(c.alpha_2)}
                aria-label={`Remove ${c.name}`}
                className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-text-muted)", cursor: "pointer" }}
              >
                <X size={13} strokeWidth={2} aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="mb-2 text-[12px]" style={{ color: "var(--qgi-text-dim)" }}>
          No countries yet — search to add your coverage.
        </p>
      )}

      {/* Search input */}
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Add a country…"
          aria-label="Search countries to add to your watchlist"
          className="w-full rounded-md border px-3 py-2 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)]"
          style={{
            background: "var(--qgi-bg)",
            color: "var(--qgi-text)",
            borderColor: "var(--qgi-border)",
          }}
        />
        {matches.length > 0 && (
          <ul
            className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border shadow-lg"
            style={{ background: "var(--qgi-surface)", borderColor: "var(--qgi-border)" }}
          >
            {matches.map((c) => (
              <li key={c.alpha_2}>
                <button
                  type="button"
                  onClick={() => add(c.alpha_2)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition-colors hover:bg-[var(--qgi-surface-2)] focus-visible:outline-none focus-visible:bg-[var(--qgi-surface-2)]"
                  style={{ color: "var(--qgi-text)", cursor: "pointer" }}
                >
                  <Plus
                    size={13}
                    strokeWidth={2}
                    aria-hidden="true"
                    style={{ color: "var(--qgi-text-dim)" }}
                  />
                  {c.name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
