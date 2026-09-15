"use client";

/**
 * RankingBand — Section 3: full-width inline pair-strength leaderboard.
 *
 * METHODOLOGY INTEGRITY GUARDS (Marcus, binding):
 * - No statusLabel() chip on pair rows.
 * - No family-color border or family-letter glyph on pair rows.
 * - Pair strength is a rank (0-100), not a probability.
 *   Column header subtitle: "Rank, not probability." at 10px caps.
 *
 * Row anatomy (left to right):
 *   [rank] [flag+name ↔ flag+name] [window] [strength bar + score] [→]
 *
 * Filters: family-overlap chips, min-window dropdown, country search.
 * Sort: Strength (default), Pair (alpha), Window.
 * URL persistence: ?sort=window etc.
 * Expand: Top 30 default, "Show all N pairs" expands.
 */
import { useState, useMemo, useCallback } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import Link from "next/link";
import type { Route } from "next";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import type { PairRow } from "@/lib/te-mock/patterns-v4-main-data";
import {
  pairFlagFor,
  FAMILY_ACTIVE_ISOS,
  getFullCatalogue,
} from "@/lib/te-mock/patterns-v4-main-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import {
  familyColor,
  familyLabel,
  L1_FAMILIES,
  NEUTRAL_SLATE,
} from "@/lib/te-mock/l1-families";

const RANK_ACCENT = "var(--qgi-accent)";
const FAMILIES = Object.values(L1_FAMILIES);

interface RankingBandProps {
  /** Full sorted catalogue (strength desc). Client filters/sorts locally. */
  allPairs: PairRow[];
  defaultSort?: "strength" | "window" | "pair";
}

type SortKey = "strength" | "window" | "pair";
type WindowFilter = "any" | "10" | "25" | "50";

export function RankingBand({ allPairs, defaultSort = "strength" }: RankingBandProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const sortFromUrl = (searchParams.get("sort") ?? defaultSort) as SortKey;
  const [sort, setSort] = useState<SortKey>(sortFromUrl);
  const [windowFilter, setWindowFilter] = useState<WindowFilter>("any");
  const [familyFilter, setFamilyFilter] = useState<string>("all");
  const [countryQuery, setCountryQuery] = useState("");
  const [expanded, setExpanded] = useState(false);

  // Persist sort to URL
  const applySort = useCallback(
    (next: SortKey) => {
      setSort(next);
      const p = new URLSearchParams(Array.from(searchParams.entries()));
      if (next === "strength") {
        p.delete("sort");
      } else {
        p.set("sort", next);
      }
      router.replace(`${pathname}?${p.toString()}` as Route, { scroll: false });
    },
    [router, pathname, searchParams]
  );

  // Active ISOs for the selected family (for family-overlap filter)
  const activeIsosForFamily = useMemo<Set<string>>(
    () =>
      familyFilter === "all"
        ? new Set<string>()
        : new Set((FAMILY_ACTIVE_ISOS[familyFilter] ?? []).map((s) => s.toLowerCase())),
    [familyFilter]
  );

  const filtered = useMemo(() => {
    let rows = [...allPairs];

    // Window filter
    if (windowFilter !== "any") {
      const min = parseInt(windowFilter, 10);
      rows = rows.filter((p) => p.window_years >= min);
    }

    // Family overlap filter
    if (familyFilter !== "all" && activeIsosForFamily.size > 0) {
      rows = rows.filter(
        (p) =>
          activeIsosForFamily.has(p.country_a_iso.toLowerCase()) ||
          activeIsosForFamily.has(p.country_b_iso.toLowerCase())
      );
    }

    // Country search
    if (countryQuery.trim()) {
      const q = countryQuery.toLowerCase();
      rows = rows.filter(
        (p) =>
          p.country_a_name.toLowerCase().includes(q) ||
          p.country_b_name.toLowerCase().includes(q) ||
          p.country_a_iso.toLowerCase().includes(q) ||
          p.country_b_iso.toLowerCase().includes(q)
      );
    }

    // Sort
    if (sort === "pair") {
      rows.sort((a, b) => a.country_a_name.localeCompare(b.country_a_name));
    } else if (sort === "window") {
      rows.sort((a, b) => b.window_years - a.window_years);
    } else {
      rows.sort((a, b) => b.pair_strength - a.pair_strength);
    }

    return rows;
  }, [allPairs, windowFilter, familyFilter, activeIsosForFamily, countryQuery, sort]);

  const visible = expanded ? filtered : filtered.slice(0, 30);
  const hasMore = filtered.length > 30;

  return (
    <div
      data-tour="patterns-ranking-table"
      style={{
        gridColumn: "1 / -1",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginTop: "28px",
      }}
    >
      {/* Panel header */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          marginBottom: "16px",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <div>
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
            CATALOGUE RANKING
          </div>
          <h2
            style={{
              fontSize: "17px",
              fontWeight: 700,
              margin: 0,
              color: "var(--qgi-text)",
            }}
          >
            Strongest pairs, by run length and rhyme
          </h2>
        </div>
        <div
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-muted)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {filtered.length} pair{filtered.length !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Filters */}
      <Filters
        familyFilter={familyFilter}
        onFamilyChange={setFamilyFilter}
        windowFilter={windowFilter}
        onWindowChange={setWindowFilter}
        countryQuery={countryQuery}
        onCountryQuery={setCountryQuery}
      />

      {/* Sort header */}
      <SortHeader sort={sort} onSort={applySort} />

      {/* Rows */}
      {visible.length === 0 ? (
        <div
          style={{
            padding: "32px 0",
            textAlign: "center",
            fontSize: "13px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
          }}
        >
          No pairs match the current filters.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
          {visible.map((pair, idx) => (
            <PairRow
              key={pair.pair_id}
              pair={pair}
              rank={sort === "strength" ? idx + 1 : undefined}
            />
          ))}
        </div>
      )}

      {/* Expand / collapse */}
      {hasMore && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          style={{
            marginTop: "16px",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            background: "none",
            border: "1px solid var(--qgi-border)",
            borderRadius: "6px",
            color: "var(--qgi-text-muted)",
            fontSize: "12px",
            padding: "7px 14px",
            cursor: "pointer",
            fontFamily: "inherit",
          }}
        >
          <ChevronDown
            size={14}
            strokeWidth={1.8}
            style={{
              transition: "transform 0.15s",
              transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
            }}
          />
          {expanded ? "Collapse" : `Show all ${filtered.length} pairs`}
        </button>
      )}
    </div>
  );
}

// ── Filters ────────────────────────────────────────────────────────────────

function Filters({
  familyFilter,
  onFamilyChange,
  windowFilter,
  onWindowChange,
  countryQuery,
  onCountryQuery,
}: {
  familyFilter: string;
  onFamilyChange: (v: string) => void;
  windowFilter: WindowFilter;
  onWindowChange: (v: WindowFilter) => void;
  countryQuery: string;
  onCountryQuery: (v: string) => void;
}) {
  return (
    <div style={{ marginBottom: "14px" }}>
      {/* Family chips */}
      <div style={{ marginBottom: "6px" }}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "6px",
            marginBottom: "4px",
          }}
        >
          <FamilyChip
            id="all"
            label="All families"
            color={NEUTRAL_SLATE}
            active={familyFilter === "all"}
            onClick={() => onFamilyChange("all")}
          />
          {FAMILIES.map((f) => (
            <FamilyChip
              key={f.id}
              id={f.id}
              label={f.label}
              color={familyColor(f.id)}
              active={familyFilter === f.id}
              onClick={() => onFamilyChange(f.id)}
            />
          ))}
        </div>
        <div
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
            letterSpacing: "0.2px",
          }}
        >
          Pairs where at least one country currently lights a recipe in this family
        </div>
      </div>

      {/* Window + country row */}
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              fontSize: "10px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
            }}
          >
            MIN WINDOW
          </span>
          <select
            value={windowFilter}
            onChange={(e) => onWindowChange(e.target.value as WindowFilter)}
            style={{
              background: "var(--qgi-bg)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "4px",
              color: "var(--qgi-text)",
              fontSize: "12px",
              padding: "4px 8px",
              fontFamily: "ui-monospace, monospace",
              cursor: "pointer",
            }}
          >
            <option value="any">Any</option>
            <option value="10">10 years+</option>
            <option value="25">25 years+</option>
            <option value="50">50 years+</option>
          </select>
        </div>

        <input
          type="text"
          value={countryQuery}
          onChange={(e) => onCountryQuery(e.target.value)}
          placeholder="Search by country..."
          style={{
            background: "var(--qgi-bg)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "4px",
            color: "var(--qgi-text)",
            fontSize: "12px",
            padding: "4px 10px",
            fontFamily: "inherit",
            outline: "none",
            minWidth: "180px",
          }}
        />
      </div>
    </div>
  );
}

function FamilyChip({
  id,
  label,
  color,
  active,
  onClick,
}: {
  id: string;
  label: string;
  color: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        padding: "4px 10px",
        borderRadius: "20px",
        border: `1px solid ${active ? color : "var(--qgi-border)"}`,
        background: active ? `${color}22` : "transparent",
        color: active ? color : "var(--qgi-text-muted)",
        fontSize: "11px",
        cursor: "pointer",
        fontFamily: "inherit",
        transition: "all 0.12s",
        whiteSpace: "nowrap",
      }}
    >
      {id !== "all" && (
        <span
          style={{
            width: "7px",
            height: "7px",
            borderRadius: "50%",
            background: color,
            flexShrink: 0,
          }}
        />
      )}
      {label}
    </button>
  );
}

// ── Sort header ────────────────────────────────────────────────────────────

function SortHeader({ sort, onSort }: { sort: SortKey; onSort: (s: SortKey) => void }) {
  const col = (key: SortKey, label: string, defaultOn: boolean) => (
    <button
      type="button"
      onClick={() => onSort(key)}
      style={{
        background: "none",
        border: "none",
        cursor: "pointer",
        color: sort === key ? "var(--qgi-accent)" : "var(--qgi-text-dim)",
        fontSize: "10px",
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.8px",
        padding: "0",
        fontWeight: sort === key ? 700 : 400,
        display: "flex",
        alignItems: "center",
        gap: "3px",
      }}
    >
      {label}
      {sort === key && (
        <span style={{ fontSize: "8px" }}>{key === "pair" ? " ↑A" : " ↓"}</span>
      )}
    </button>
  );

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "40px 1fr 140px 120px 32px",
        alignItems: "center",
        gap: "8px",
        paddingBottom: "8px",
        borderBottom: "1px solid var(--qgi-border)",
        marginBottom: "4px",
      }}
    >
      <span
        style={{
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.8px",
        }}
      >
        #
      </span>
      {col("pair", "PAIR", false)}
      {col("window", "WINDOW", false)}
      <div>
        {col("strength", "STRENGTH", true)}
        <div
          style={{
            fontSize: "9px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
            marginTop: "1px",
          }}
        >
          Rank, not probability.
        </div>
      </div>
      <span />
    </div>
  );
}

// ── Single pair row ────────────────────────────────────────────────────────

function PairRow({ pair, rank }: { pair: PairRow; rank?: number }) {
  const rankColor =
    rank === 1
      ? "var(--qgi-accent)"
      : rank === 2 || rank === 3
        ? "#9BA8B5"
        : "var(--qgi-text-muted)";

  const strengthFill = Math.round((pair.pair_strength / 100) * 80);

  return (
    <Link
      href={`/patterns/${pair.pair_id}` as Route}
      style={{ textDecoration: "none", color: "inherit" }}
      aria-label={`Open pair ${pair.country_a_name} and ${pair.country_b_name}`}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "40px 1fr 140px 120px 32px",
          alignItems: "center",
          gap: "8px",
          padding: "8px 4px",
          borderRadius: "5px",
          cursor: "pointer",
          transition: "background 0.1s",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.03)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.background = "transparent";
        }}
      >
        {/* Rank */}
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "13px",
            fontWeight: 700,
            color: rankColor,
            textAlign: "right",
          }}
        >
          {rank ?? ""}
        </span>

        {/* Pair block */}
        <div
          style={{ display: "flex", alignItems: "center", gap: "7px", flexWrap: "wrap" }}
        >
          <FlagImg
            emoji={pairFlagFor(pair.country_a_name)}
            name={pair.country_a_name}
            width={16}
          />
          <span
            style={{ fontSize: "13px", fontWeight: 500, color: "var(--qgi-text)" }}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              window.location.href = `/countries/${pair.country_a_iso}`;
            }}
          >
            {pair.country_a_name}
          </span>
          <span
            style={{
              fontSize: "13px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              userSelect: "none",
            }}
          >
            ↔
          </span>
          <FlagImg
            emoji={pairFlagFor(pair.country_b_name)}
            name={pair.country_b_name}
            width={16}
          />
          <span
            style={{ fontSize: "13px", fontWeight: 500, color: "var(--qgi-text)" }}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              window.location.href = `/countries/${pair.country_b_iso}`;
            }}
          >
            {pair.country_b_name}
          </span>
        </div>

        {/* Window block */}
        <span
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-muted)",
            fontFamily: "ui-monospace, monospace",
            whiteSpace: "nowrap",
          }}
        >
          {pair.start_year}
          {"–"}
          {pair.end_year}
          <span style={{ color: "var(--qgi-text-dim)", marginLeft: "4px" }}>
            {pair.window_years}y
          </span>
        </span>

        {/* Strength block */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div
            style={{
              width: "80px",
              height: "6px",
              background: "var(--qgi-border)",
              borderRadius: "3px",
              overflow: "hidden",
              flexShrink: 0,
            }}
          >
            <div
              style={{
                width: `${strengthFill}px`,
                height: "100%",
                background: NEUTRAL_SLATE,
                borderRadius: "3px",
                transition: "width 0.2s",
              }}
            />
          </div>
          <span
            style={{
              fontSize: "12px",
              fontFamily: "ui-monospace, monospace",
              color: "var(--qgi-text)",
              fontWeight: 600,
              minWidth: "24px",
              textAlign: "right",
            }}
          >
            {pair.pair_strength}
          </span>
        </div>

        {/* Open chevron */}
        <ChevronRight
          size={14}
          strokeWidth={1.8}
          aria-label="Open this pair"
          color="var(--qgi-text-dim)"
        />
      </div>
    </Link>
  );
}
