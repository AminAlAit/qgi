"use client";

/**
 * All-verified-events table (#523).
 *
 * 2.4 MB JSON paged + filtered client-side. Cost-saving choice — no
 * Athena per page-flip, no API roundtrips.
 *
 * #707 (2026-05-16) — perf v1: JSON moved from static import to a
 * dynamic import inside `useEffect`. Pre-fix, the 2.4 MB JSON was
 * landing in the methodology/events route's initial client chunk;
 * post-fix, it's a separate async chunk loaded after the page hydrates.
 * Initial bundle savings ~2.4 MB; FCP unaffected; the table shows a
 * loading state for the ~200 ms the chunk is in flight.
 *
 * Filters: country dropdown, category dropdown, year-range inputs,
 * fulltext search on title. Source URL shown as domain inline; row
 * click opens source in a new tab.
 *
 * v2 follow-up (filed as #707 follow-up): convert page wrapper to async
 * Server Component, paginate server-side via URL search params, eliminate
 * the 2.4 MB JSON from any client chunk entirely. Out of scope for v1;
 * v1 unblocks the worst initial-load symptom without rewriting the
 * filter architecture.
 */
import { useEffect, useMemo, useState } from "react";

type Event = {
  country: string;
  year: number;
  title: string;
  category: string;
  source: string | null;
  sourceDomain: string | null;
};

const PAGE_SIZE = 50;

function prettyCategory(s: string): string {
  if (!s) return "—";
  return s
    .split("_")
    .map((w) => (w.length <= 2 ? w : w[0].toUpperCase() + w.slice(1)))
    .join(" ");
}

export default function EventsTable() {
  // #707 v1 — lazy-load the 2.4 MB JSON so it stays out of the methodology
  // /events initial client chunk. The page renders the filter shell + a
  // loading state immediately; the 2.4 MB chunk arrives on its own clock.
  const [all, setAll] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    import("@/data/verified-events.json")
      .then((mod) => {
        if (cancelled) return;
        // The JSON module's default export is the events array.
        setAll(mod.default as Event[]);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[EventsTable] failed to load verified-events.json:", err);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Distinct values for filters
  const countries = useMemo(
    () => Array.from(new Set(all.map((e) => e.country))).sort(),
    [all]
  );
  const categories = useMemo(
    () => Array.from(new Set(all.map((e) => e.category).filter(Boolean))).sort(),
    [all]
  );

  const [country, setCountry] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [yearMin, setYearMin] = useState<string>("");
  const [yearMax, setYearMax] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const yMin = yearMin ? parseInt(yearMin, 10) : null;
    const yMax = yearMax ? parseInt(yearMax, 10) : null;
    return all.filter((e) => {
      if (country && e.country !== country) return false;
      if (category && e.category !== category) return false;
      if (yMin != null && !isNaN(yMin) && e.year < yMin) return false;
      if (yMax != null && !isNaN(yMax) && e.year > yMax) return false;
      if (q && !e.title.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [all, country, category, yearMin, yearMax, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const slice = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  function resetFilters() {
    setCountry("");
    setCategory("");
    setYearMin("");
    setYearMax("");
    setSearch("");
    setPage(0);
  }

  return (
    <div>
      {/* Header counts */}
      <div className="mb-4 flex items-baseline justify-between flex-wrap gap-2">
        <div
          className="text-[11px] tracking-widest uppercase"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {loading
            ? "Loading events…"
            : `${filtered.length.toLocaleString()} of ${all.length.toLocaleString()} events`}
        </div>
        <div className="text-[11px]" style={{ color: "var(--qgi-text-muted)" }}>
          Page {safePage + 1} / {totalPages}
        </div>
      </div>

      {/*
       * Filters — WCAG 1.3.1 + 4.1.2 fix (#738 item 3, 2026-05-16).
       *
       * Pre-fix: each input/select had only `placeholder` text for context,
       * which fails 1.3.1 (Info and Relationships) because placeholder is
       * not a programmatic label. aria-label was added as a partial
       * mitigation but only satisfies 4.1.2.
       *
       * Post-fix: each filter input has an explicit visually-hidden
       * `<label htmlFor>` + `id` pair. The label is the canonical text;
       * placeholder remains as the visible hint for sighted users.
       * aria-label has been removed since the proper label association
       * makes it redundant (and double-naming can cause screen-reader
       * verbosity).
       */}
      <div
        className="rounded-lg border p-3 mb-4 flex flex-wrap gap-2 items-center"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-surface)",
        }}
      >
        <label htmlFor="events-search" className="sr-only">
          Search event titles
        </label>
        <input
          id="events-search"
          type="text"
          placeholder="Search title…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          disabled={loading}
          className="flex-1 min-w-[160px] text-xs px-3 py-2 rounded outline-none disabled:opacity-50"
          style={{
            backgroundColor: "var(--qgi-bg)",
            color: "var(--qgi-text)",
            border: "1px solid var(--qgi-border)",
          }}
        />
        <label htmlFor="events-country" className="sr-only">
          Filter by country
        </label>
        <select
          id="events-country"
          value={country}
          onChange={(e) => {
            setCountry(e.target.value);
            setPage(0);
          }}
          disabled={loading}
          className="text-xs px-3 py-2 rounded outline-none disabled:opacity-50"
          style={{
            backgroundColor: "var(--qgi-bg)",
            color: "var(--qgi-text)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          <option value="">All countries</option>
          {countries.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <label htmlFor="events-category" className="sr-only">
          Filter by category
        </label>
        <select
          id="events-category"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(0);
          }}
          disabled={loading}
          className="text-xs px-3 py-2 rounded outline-none disabled:opacity-50"
          style={{
            backgroundColor: "var(--qgi-bg)",
            color: "var(--qgi-text)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {prettyCategory(c)}
            </option>
          ))}
        </select>
        <label htmlFor="events-year-min" className="sr-only">
          Earliest year
        </label>
        <input
          id="events-year-min"
          type="number"
          placeholder="Year ≥"
          value={yearMin}
          onChange={(e) => {
            setYearMin(e.target.value);
            setPage(0);
          }}
          disabled={loading}
          className="text-xs px-3 py-2 rounded outline-none w-24 disabled:opacity-50"
          style={{
            backgroundColor: "var(--qgi-bg)",
            color: "var(--qgi-text)",
            border: "1px solid var(--qgi-border)",
          }}
        />
        <label htmlFor="events-year-max" className="sr-only">
          Latest year
        </label>
        <input
          id="events-year-max"
          type="number"
          placeholder="Year ≤"
          value={yearMax}
          onChange={(e) => {
            setYearMax(e.target.value);
            setPage(0);
          }}
          disabled={loading}
          className="text-xs px-3 py-2 rounded outline-none w-24 disabled:opacity-50"
          style={{
            backgroundColor: "var(--qgi-bg)",
            color: "var(--qgi-text)",
            border: "1px solid var(--qgi-border)",
          }}
        />
        <button
          onClick={resetFilters}
          disabled={loading}
          className="text-[11px] tracking-wider uppercase px-3 py-2 rounded transition-colors disabled:opacity-50"
          style={{
            color: "var(--qgi-text-muted)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          Reset
        </button>
      </div>

      {/* Table */}
      <div
        className="rounded-lg border overflow-hidden"
        style={{ borderColor: "var(--qgi-border)" }}
      >
        <table className="w-full text-xs">
          <thead>
            <tr
              className="text-[10px] tracking-widest uppercase"
              style={{
                backgroundColor: "var(--qgi-surface)",
                color: "var(--qgi-text-muted)",
              }}
            >
              <th scope="col" className="text-left px-4 py-3 font-normal">
                Year
              </th>
              <th scope="col" className="text-left px-4 py-3 font-normal">
                Country
              </th>
              <th scope="col" className="text-left px-4 py-3 font-normal">
                Title
              </th>
              <th
                scope="col"
                className="text-left px-4 py-3 font-normal hidden md:table-cell"
              >
                Category
              </th>
              <th
                scope="col"
                className="text-left px-4 py-3 font-normal hidden md:table-cell"
              >
                Source
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-8 text-center text-xs"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  Loading the 10,000+ verified events…
                </td>
              </tr>
            )}
            {!loading && slice.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-8 text-center text-xs"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  No events match these filters.
                </td>
              </tr>
            )}
            {!loading &&
              slice.map((e, i) => (
                <tr
                  key={i}
                  className="hover:bg-white/5 transition-colors border-t"
                  style={{ borderColor: "var(--qgi-border)" }}
                >
                  <td
                    className="px-4 py-3 font-data tabular-nums"
                    style={{ color: "var(--qgi-text)" }}
                  >
                    {e.year}
                  </td>
                  <td className="px-4 py-3" style={{ color: "var(--qgi-text)" }}>
                    {e.country}
                  </td>
                  <td className="px-4 py-3" style={{ color: "var(--qgi-text)" }}>
                    {e.title}
                  </td>
                  <td
                    className="px-4 py-3 hidden md:table-cell"
                    style={{ color: "var(--qgi-text-muted)" }}
                  >
                    {prettyCategory(e.category)}
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    {e.source ? (
                      <a
                        href={e.source}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-data hover:underline inline-flex items-center gap-1.5"
                        style={{ color: "var(--qgi-accent)" }}
                      >
                        <span aria-hidden>🔗</span>
                        {e.sourceDomain || "source"}
                      </a>
                    ) : (
                      <span style={{ color: "var(--qgi-text-muted)" }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && !loading && (
        <div className="mt-4 flex items-center justify-between text-xs">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={safePage === 0}
            className="px-3 py-2 rounded tracking-wider uppercase disabled:opacity-30"
            style={{
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            ← Prev
          </button>
          <span style={{ color: "var(--qgi-text-muted)" }}>
            Page {safePage + 1} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={safePage >= totalPages - 1}
            className="px-3 py-2 rounded tracking-wider uppercase disabled:opacity-30"
            style={{
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
