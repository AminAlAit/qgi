"use client";

import { useMemo, useState } from "react";
import { X, Plus } from "lucide-react";
import { TREND_CATALOG, TREND_LABEL } from "@/lib/trend-catalog";

/**
 * Searchable multi-select for the user's trend focus (recipe slugs). null =
 * no focus (show all trends); a non-empty array = show only those. Removing the
 * last one collapses back to null. Persisted via the parent (settings.trendFocus)
 * and used to filter the Risk Board rows.
 */
export function TrendFocusPicker({
  value,
  onChange,
}: {
  value: string[] | null;
  onChange: (next: string[] | null) => void;
}) {
  const [query, setQuery] = useState("");
  const selected = useMemo(() => value ?? [], [value]);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return TREND_CATALOG.filter(
      (t) =>
        !selected.includes(t.slug) &&
        (t.label.toLowerCase().includes(q) || t.l1Label.toLowerCase().includes(q))
    ).slice(0, 8);
  }, [query, selected]);

  function add(slug: string) {
    onChange([...selected, slug]);
    setQuery("");
  }
  function remove(slug: string) {
    const next = selected.filter((s) => s !== slug);
    onChange(next.length === 0 ? null : next);
  }

  return (
    <div className="w-full">
      {selected.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {selected.map((slug) => (
            <span
              key={slug}
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px]"
              style={{ background: "var(--qgi-surface-2)", color: "var(--qgi-text)" }}
            >
              {TREND_LABEL.get(slug) ?? slug}
              <button
                type="button"
                onClick={() => remove(slug)}
                aria-label={`Remove ${TREND_LABEL.get(slug) ?? slug}`}
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
          Showing all trends — search to focus on the ones you act on.
        </p>
      )}

      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Add a trend…"
          aria-label="Search trends to focus on"
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
            {matches.map((t) => (
              <li key={t.slug}>
                <button
                  type="button"
                  onClick={() => add(t.slug)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition-colors hover:bg-[var(--qgi-surface-2)] focus-visible:outline-none focus-visible:bg-[var(--qgi-surface-2)]"
                  style={{ color: "var(--qgi-text)", cursor: "pointer" }}
                >
                  <Plus
                    size={13}
                    strokeWidth={2}
                    aria-hidden="true"
                    style={{ color: "var(--qgi-text-dim)" }}
                  />
                  <span>
                    {t.label}
                    <span
                      className="ml-1.5 text-[11px]"
                      style={{ color: "var(--qgi-text-dim)" }}
                    >
                      {t.l1Label}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
