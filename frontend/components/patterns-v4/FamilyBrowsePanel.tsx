"use client";

/**
 * FamilyBrowsePanel — Section 4: browse pairs by L1 family.
 *
 * 8 chip filters (one per L1, "All" option). Filterable list of pairs
 * where at least one country in the pair is currently lit on a recipe
 * in that family. ~12 visible rows.
 *
 * Marcus binding subtitle: "Pairs where at least one country currently
 * lights a recipe in this family"
 *
 * METHODOLOGY: Family chips use familyColor(). Pair rows carry NO family-
 * color border or family-letter glyph -- the filter is a nav aid only.
 */
import { useState, useMemo } from "react";
import Link from "next/link";
import type { Route } from "next";
import { ChevronRight } from "lucide-react";
import type { PairRow } from "@/lib/te-mock/patterns-v4-main-data";
import { pairFlagFor, FAMILY_ACTIVE_ISOS } from "@/lib/te-mock/patterns-v4-main-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import {
  familyColor,
  familyLabel,
  L1_FAMILIES,
  NEUTRAL_SLATE,
} from "@/lib/te-mock/l1-families";

const FAMILIES = Object.values(L1_FAMILIES);
const DEFAULT_VISIBLE = 12;

interface FamilyBrowsePanelProps {
  allPairs: PairRow[];
}

export function FamilyBrowsePanel({ allPairs }: FamilyBrowsePanelProps) {
  const [activeFamily, setActiveFamily] = useState<string>("all");
  const [showAll, setShowAll] = useState(false);

  const activeIsos = useMemo<Set<string>>(() => {
    if (activeFamily === "all") return new Set<string>();
    return new Set((FAMILY_ACTIVE_ISOS[activeFamily] ?? []).map((s) => s.toLowerCase()));
  }, [activeFamily]);

  const filtered = useMemo(() => {
    if (activeFamily === "all") return allPairs;
    return allPairs.filter(
      (p) =>
        activeIsos.has(p.country_a_iso.toLowerCase()) ||
        activeIsos.has(p.country_b_iso.toLowerCase())
    );
  }, [allPairs, activeFamily, activeIsos]);

  const visible = showAll ? filtered : filtered.slice(0, DEFAULT_VISIBLE);

  return (
    <div
      data-tour="patterns-family-browse"
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
        BROWSE BY FAMILY
      </div>
      <h2
        style={{
          fontSize: "16px",
          fontWeight: 700,
          margin: "0 0 12px",
          color: "var(--qgi-text)",
        }}
      >
        Pairs by event family
      </h2>

      {/* Family chips */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "6px",
          marginBottom: "6px",
        }}
      >
        <FamilyChip
          id="all"
          label="All"
          color={NEUTRAL_SLATE}
          active={activeFamily === "all"}
          onClick={() => {
            setActiveFamily("all");
            setShowAll(false);
          }}
        />
        {FAMILIES.map((f) => (
          <FamilyChip
            key={f.id}
            id={f.id}
            label={f.label}
            color={familyColor(f.id)}
            active={activeFamily === f.id}
            onClick={() => {
              setActiveFamily(f.id);
              setShowAll(false);
            }}
          />
        ))}
      </div>
      <div
        style={{
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          fontStyle: "italic",
          marginBottom: "14px",
        }}
      >
        Pairs where at least one country currently lights a recipe in this family
      </div>

      {/* Pair list */}
      {visible.length === 0 ? (
        <div
          style={{
            padding: "24px 0",
            textAlign: "center",
            fontSize: "13px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
          }}
        >
          No pairs on record for this category yet.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
          {visible.map((pair) => (
            <FamilyPairRow key={pair.pair_id} pair={pair} />
          ))}
        </div>
      )}

      {filtered.length > DEFAULT_VISIBLE && (
        <button
          type="button"
          onClick={() => setShowAll((s) => !s)}
          style={{
            marginTop: "12px",
            background: "none",
            border: "1px solid var(--qgi-border)",
            borderRadius: "5px",
            color: "var(--qgi-text-muted)",
            fontSize: "11px",
            padding: "5px 12px",
            cursor: "pointer",
            fontFamily: "inherit",
          }}
        >
          {showAll ? "Collapse" : `Show all ${filtered.length} pairs`}
        </button>
      )}
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

function FamilyPairRow({ pair }: { pair: PairRow }) {
  return (
    <Link
      href={`/patterns/${pair.pair_id}` as Route}
      style={{ textDecoration: "none", color: "inherit" }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 6px",
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
        <div
          style={{ display: "flex", alignItems: "center", gap: "7px", flexWrap: "wrap" }}
        >
          <FlagImg
            emoji={pairFlagFor(pair.country_a_name)}
            name={pair.country_a_name}
            width={15}
          />
          <span style={{ fontSize: "13px", color: "var(--qgi-text)" }}>
            {pair.country_a_name}
          </span>
          <span
            style={{
              fontSize: "12px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            ↔
          </span>
          <FlagImg
            emoji={pairFlagFor(pair.country_b_name)}
            name={pair.country_b_name}
            width={15}
          />
          <span style={{ fontSize: "13px", color: "var(--qgi-text)" }}>
            {pair.country_b_name}
          </span>
          <span
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              marginLeft: "4px",
            }}
          >
            {pair.window_years}y
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
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
          <ChevronRight size={13} strokeWidth={1.8} color="var(--qgi-text-dim)" />
        </div>
      </div>
    </Link>
  );
}
