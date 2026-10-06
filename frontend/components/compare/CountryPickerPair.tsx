/**
 * CountryPickerPair — two adjacent comboboxes for /compare.
 *
 * Search-as-you-type by name or ISO. Each slot shows a FlagImg + name + ISO +
 * region in the dropdown. A "Swap" button between them reverses A and B.
 * Selecting either updates the URL querystring via router.replace() so the
 * comparison is shareable.
 *
 * Client component (uses router, state, keyboard interaction).
 * V4.1 bar: no em-dashes, no banned vocab, COUNTRIES_V4 as the source.
 */
"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { COUNTRIES_V4, type CountryV4 } from "@/lib/te-mock/countries-v4-data";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";

// ── Swap icon (two opposing arrows) ───────────────────────────────────────
function SwapIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M2 5h12M11 2l3 3-3 3M14 11H2M5 8l-3 3 3 3"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// ── Single combobox slot ───────────────────────────────────────────────────

interface SlotProps {
  label: "A" | "B";
  selected: CountryV4;
  otherIso: string;
  onChange: (iso: string) => void;
}

function CountrySlot({ label, selected, otherIso, onChange }: SlotProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const filtered = COUNTRIES_V4.filter((c) => {
    if (c.iso === otherIso) return false;
    if (!query) return true;
    const q = query.toLowerCase();
    return c.name.toLowerCase().includes(q) || c.iso.toLowerCase().includes(q);
  }).slice(0, 20);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handle = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!inputRef.current?.contains(target) && !dropdownRef.current?.contains(target)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  const handleSelect = (iso: string) => {
    onChange(iso);
    setOpen(false);
    setQuery("");
    inputRef.current?.blur();
  };

  const recipeCount = selected.recipes_lit_count;

  return (
    <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
      {/* Slot label */}
      <div
        style={{
          fontSize: "10px",
          letterSpacing: "0.8px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "6px",
          fontWeight: 600,
        }}
      >
        Country {label}
      </div>

      {/* Selected country display / search input toggle */}
      <div style={{ position: "relative" }}>
        {!open ? (
          <button
            type="button"
            onClick={() => {
              setOpen(true);
              setTimeout(() => inputRef.current?.focus(), 0);
            }}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "10px 12px",
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "5px",
              cursor: "pointer",
              color: "var(--qgi-text)",
              textAlign: "left",
            }}
          >
            <FlagImg emoji={selected.flag_emoji} name={selected.name} width={20} />
            <span style={{ flex: 1, fontSize: "14px", fontWeight: 600 }}>
              {selected.name}
            </span>
            <span
              style={{
                fontSize: "10px",
                fontFamily: "ui-monospace, monospace",
                color: "var(--qgi-text-dim)",
                letterSpacing: "0.3px",
              }}
            >
              {selected.iso}
            </span>
            <span
              title={`${recipeCount} trend${recipeCount === 1 ? "" : "s"} in play`}
              style={{
                fontSize: "10px",
                fontFamily: "ui-monospace, monospace",
                padding: "2px 7px",
                border: `1px solid ${NEUTRAL_SLATE}66`,
                borderRadius: "3px",
                color: NEUTRAL_SLATE,
                background: `${NEUTRAL_SLATE}14`,
                whiteSpace: "nowrap",
                letterSpacing: "0.2px",
              }}
            >
              {recipeCount} trends
            </span>
            <span
              style={{
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {selected.region}
            </span>
          </button>
        ) : (
          <input
            ref={inputRef}
            type="text"
            placeholder="Search by name or ISO..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setOpen(false);
                setQuery("");
              }
              if (e.key === "Enter" && filtered[0]) {
                handleSelect(filtered[0].iso);
              }
            }}
            style={{
              width: "100%",
              padding: "10px 12px",
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-accent)",
              borderRadius: "5px",
              color: "var(--qgi-text)",
              fontSize: "14px",
              outline: "none",
              boxSizing: "border-box",
            }}
            aria-label={`Search country ${label}`}
            aria-expanded={open}
            aria-haspopup="listbox"
          />
        )}

        {/* Dropdown */}
        {open && (
          <div
            ref={dropdownRef}
            role="listbox"
            aria-label={`Country ${label} options`}
            style={{
              position: "absolute",
              top: "calc(100% + 4px)",
              left: 0,
              right: 0,
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "5px",
              boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
              zIndex: 20,
              maxHeight: "280px",
              overflowY: "auto",
            }}
          >
            {filtered.length === 0 ? (
              <div
                style={{
                  padding: "12px 14px",
                  fontSize: "12px",
                  color: "var(--qgi-text-dim)",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                No countries match
              </div>
            ) : (
              filtered.map((c) => {
                const rc = c.recipes_lit_count;
                return (
                  <button
                    key={c.iso}
                    role="option"
                    aria-selected={c.iso === selected.iso}
                    type="button"
                    onClick={() => handleSelect(c.iso)}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      padding: "9px 14px",
                      background:
                        c.iso === selected.iso ? "var(--qgi-accent-glow)" : "transparent",
                      border: "none",
                      borderBottom: "1px solid var(--qgi-border)",
                      cursor: "pointer",
                      color: "var(--qgi-text)",
                      textAlign: "left",
                    }}
                  >
                    <FlagImg emoji={c.flag_emoji} name={c.name} width={18} />
                    <span style={{ flex: 1, fontSize: "13px" }}>{c.name}</span>
                    <span
                      style={{
                        fontSize: "10px",
                        color: "var(--qgi-text-dim)",
                        fontFamily: "ui-monospace, monospace",
                      }}
                    >
                      {c.iso}
                    </span>
                    <span
                      style={{
                        fontSize: "10px",
                        fontFamily: "ui-monospace, monospace",
                        color: NEUTRAL_SLATE,
                        padding: "1px 5px",
                        border: `1px solid ${NEUTRAL_SLATE}44`,
                        borderRadius: "3px",
                      }}
                    >
                      {rc}
                    </span>
                    <span
                      style={{
                        fontSize: "10px",
                        color: "var(--qgi-text-dim)",
                        fontFamily: "ui-monospace, monospace",
                      }}
                    >
                      {c.region}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

interface CountryPickerPairProps {
  isoA: string;
  isoB: string;
}

export function CountryPickerPair({ isoA, isoB }: CountryPickerPairProps) {
  const router = useRouter();

  const countryA = COUNTRIES_V4.find((c) => c.iso === isoA.toUpperCase());
  const countryB = COUNTRIES_V4.find((c) => c.iso === isoB.toUpperCase());

  const updateUrl = useCallback(
    (a: string, b: string) => {
      router.replace(`/compare?a=${a}&b=${b}` as Route);
    },
    [router]
  );

  const handleChangeA = (iso: string) => updateUrl(iso, isoB);
  const handleChangeB = (iso: string) => updateUrl(isoA, iso);
  const handleSwap = () => updateUrl(isoB, isoA);

  if (!countryA || !countryB) return null;

  return (
    <div
      data-tour="compare-picker"
      style={{
        display: "flex",
        alignItems: "flex-end",
        gap: "12px",
        flexWrap: "wrap",
      }}
    >
      <CountrySlot
        label="A"
        selected={countryA}
        otherIso={isoB}
        onChange={handleChangeA}
      />

      {/* Swap button */}
      <button
        type="button"
        onClick={handleSwap}
        aria-label="Swap country A and country B"
        title="Swap A and B"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: "36px",
          height: "36px",
          flexShrink: 0,
          marginBottom: "0px",
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "5px",
          color: "var(--qgi-text-muted)",
          cursor: "pointer",
          alignSelf: "flex-end",
          marginTop: "24px",
        }}
      >
        <SwapIcon />
      </button>

      <CountrySlot
        label="B"
        selected={countryB}
        otherIso={isoA}
        onChange={handleChangeB}
      />
    </div>
  );
}
