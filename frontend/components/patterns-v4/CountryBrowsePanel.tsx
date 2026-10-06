"use client";

/**
 * CountryBrowsePanel — Section 5: browse pairs by country.
 *
 * Typeahead input (pattern lifted from CountryPicker.tsx) returns every pair
 * the selected country appears in, sorted by pair strength. Two-column results.
 *
 * ISO codes come from pair data; we do not import the full COUNTRIES_V4 list
 * since it would make the bundle heavier than needed for a filter panel.
 */
import { useState, useMemo } from "react";
import Link from "next/link";
import type { Route } from "next";
import { Search, ChevronDown, ChevronRight } from "lucide-react";
import type { PairRow } from "@/lib/te-mock/patterns-v4-main-data";
import { pairFlagFor } from "@/lib/te-mock/patterns-v4-main-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";

interface CountryEntry {
  iso: string;
  name: string;
}

function buildCountryList(allPairs: PairRow[]): CountryEntry[] {
  const seen = new Map<string, string>();
  for (const p of allPairs) {
    if (!seen.has(p.country_a_iso)) seen.set(p.country_a_iso, p.country_a_name);
    if (!seen.has(p.country_b_iso)) seen.set(p.country_b_iso, p.country_b_name);
  }
  return Array.from(seen.entries())
    .map(([iso, name]) => ({ iso, name }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

interface CountryBrowsePanelProps {
  allPairs: PairRow[];
}

export function CountryBrowsePanel({ allPairs }: CountryBrowsePanelProps) {
  const countries = useMemo(() => buildCountryList(allPairs), [allPairs]);

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIso, setSelectedIso] = useState<string | null>(null);

  const filteredCountries = useMemo(
    () =>
      query.trim()
        ? countries.filter(
            (c) =>
              c.name.toLowerCase().includes(query.toLowerCase()) ||
              c.iso.toLowerCase().includes(query.toLowerCase())
          )
        : countries,
    [countries, query]
  );

  const selected = countries.find((c) => c.iso === selectedIso) ?? null;

  const matchingPairs = useMemo(() => {
    if (!selectedIso) return [];
    return allPairs
      .filter((p) => p.country_a_iso === selectedIso || p.country_b_iso === selectedIso)
      .sort((a, b) => b.pair_strength - a.pair_strength);
  }, [allPairs, selectedIso]);

  return (
    <div
      data-tour="patterns-country-browse"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginTop: "24px",
      }}
    >
      {/* Header */}
      <div
        style={{
          fontSize: "9px",
          letterSpacing: "1.6px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "4px",
          fontWeight: 600,
        }}
      >
        BROWSE BY COUNTRY
      </div>
      <h2
        style={{
          fontSize: "16px",
          fontWeight: 700,
          margin: "0 0 14px",
          color: "var(--qgi-text)",
        }}
      >
        All pairs for a country
      </h2>

      {/* Typeahead picker */}
      <div style={{ position: "relative", maxWidth: "480px", marginBottom: "16px" }}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-haspopup="listbox"
          style={{
            width: "100%",
            padding: "11px 14px",
            background: "var(--qgi-bg)",
            border: `1px solid ${open ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
            borderRadius: "7px",
            color: selected ? "var(--qgi-text)" : "var(--qgi-text-dim)",
            fontSize: "14px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            cursor: "pointer",
            fontFamily: "inherit",
            transition: "border-color 0.15s",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: "9px" }}>
            <Search size={14} strokeWidth={1.8} color="var(--qgi-text-dim)" />
            {selected ? (
              <>
                <FlagImg
                  emoji={pairFlagFor(selected.name)}
                  name={selected.name}
                  width={16}
                />
                <span style={{ fontWeight: 600 }}>{selected.name}</span>
              </>
            ) : (
              <span>Pick a country to see its pairs...</span>
            )}
          </span>
          <ChevronDown
            size={16}
            strokeWidth={1.8}
            color="var(--qgi-text-muted)"
            style={{
              transition: "transform 0.15s",
              transform: open ? "rotate(180deg)" : "rotate(0deg)",
            }}
          />
        </button>

        {open && (
          <div
            role="listbox"
            style={{
              position: "absolute",
              top: "calc(100% + 5px)",
              left: 0,
              right: 0,
              zIndex: 20,
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-accent)",
              borderRadius: "7px",
              padding: "7px",
              maxHeight: "320px",
              overflow: "auto",
              boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            }}
          >
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter countries..."
              autoFocus
              style={{
                width: "100%",
                padding: "8px 10px",
                background: "var(--qgi-bg)",
                border: "1px solid var(--qgi-border)",
                borderRadius: "5px",
                color: "var(--qgi-text)",
                fontSize: "12px",
                outline: "none",
                fontFamily: "inherit",
                marginBottom: "6px",
                boxSizing: "border-box",
              }}
            />
            {filteredCountries.length === 0 ? (
              <div
                style={{
                  padding: "14px",
                  fontSize: "12px",
                  color: "var(--qgi-text-dim)",
                  textAlign: "center",
                  fontStyle: "italic",
                }}
              >
                No match in the catalogue.
              </div>
            ) : (
              filteredCountries.map((c) => (
                <button
                  key={c.iso}
                  type="button"
                  role="option"
                  aria-selected={c.iso === selectedIso}
                  onClick={() => {
                    setSelectedIso(c.iso);
                    setOpen(false);
                    setQuery("");
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "7px",
                    width: "100%",
                    padding: "7px 10px",
                    background:
                      c.iso === selectedIso ? "rgba(56,189,248,0.1)" : "transparent",
                    border: `1px solid ${c.iso === selectedIso ? "var(--qgi-accent)" : "transparent"}`,
                    borderRadius: "4px",
                    color: "var(--qgi-text)",
                    fontSize: "12px",
                    cursor: "pointer",
                    textAlign: "left",
                    fontFamily: "inherit",
                    marginBottom: "1px",
                  }}
                >
                  <FlagImg emoji={pairFlagFor(c.name)} name={c.name} width={14} />
                  <span
                    style={{ flex: 1, fontWeight: c.iso === selectedIso ? 600 : 400 }}
                  >
                    {c.name}
                  </span>
                  <span
                    style={{
                      fontSize: "10px",
                      color: "var(--qgi-text-dim)",
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    {c.iso.toUpperCase()}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      {/* Results */}
      {!selected && (
        <div
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
            padding: "16px 0",
          }}
        >
          Select a country above to see every pair it appears in.
        </div>
      )}

      {selected && matchingPairs.length === 0 && (
        <div
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
            padding: "16px 0",
          }}
        >
          No pairs on record for {selected.name} yet.
        </div>
      )}

      {selected && matchingPairs.length > 0 && (
        <>
          <div
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-muted)",
              marginBottom: "12px",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {matchingPairs.length} pair{matchingPairs.length !== 1 ? "s" : ""} for{" "}
            {selected.name} -- sorted by strength
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: "8px",
            }}
          >
            {matchingPairs.map((pair) => {
              const partner =
                pair.country_a_iso === selected.iso
                  ? { iso: pair.country_b_iso, name: pair.country_b_name }
                  : { iso: pair.country_a_iso, name: pair.country_a_name };
              return (
                <Link
                  key={pair.pair_id}
                  href={`/patterns/${pair.pair_id}` as Route}
                  style={{ textDecoration: "none", color: "inherit" }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "10px 12px",
                      background: "var(--qgi-bg)",
                      border: "1px solid var(--qgi-border)",
                      borderRadius: "6px",
                      cursor: "pointer",
                      transition: "border-color 0.12s",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor =
                        "var(--qgi-accent)";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor =
                        "var(--qgi-border)";
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "7px",
                      }}
                    >
                      <FlagImg
                        emoji={pairFlagFor(partner.name)}
                        name={partner.name}
                        width={15}
                      />
                      <span
                        style={{
                          fontSize: "13px",
                          fontWeight: 500,
                          color: "var(--qgi-text)",
                        }}
                      >
                        {partner.name}
                      </span>
                      <span
                        style={{
                          fontSize: "11px",
                          color: "var(--qgi-text-dim)",
                          fontFamily: "ui-monospace, monospace",
                        }}
                      >
                        {pair.window_years}y
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "7px" }}>
                      <div
                        style={{
                          width: "48px",
                          height: "5px",
                          background: "var(--qgi-border)",
                          borderRadius: "3px",
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            width: `${Math.round((pair.pair_strength / 100) * 48)}px`,
                            height: "100%",
                            background: NEUTRAL_SLATE,
                            borderRadius: "3px",
                          }}
                        />
                      </div>
                      <span
                        style={{
                          fontSize: "12px",
                          fontFamily: "ui-monospace, monospace",
                          color: "var(--qgi-text-muted)",
                          fontWeight: 600,
                        }}
                      >
                        {pair.pair_strength}
                      </span>
                      <ChevronRight
                        size={12}
                        strokeWidth={1.8}
                        color="var(--qgi-text-dim)"
                      />
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
