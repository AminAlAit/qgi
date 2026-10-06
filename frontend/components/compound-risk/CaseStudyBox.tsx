import Link from "next/link";
import type { Route } from "next";
import type { CompoundCaseStudy } from "@/lib/te-mock/compound-risk-data";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { familyColor } from "@/lib/te-mock/l1-families";

export function CaseStudyBox({ study }: { study: CompoundCaseStudy }) {
  return (
    <article
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <FlagImg emoji={flagFor(study.country)} name={study.country} width={32} />
          <Link
            href={`/countries/${study.iso.toLowerCase()}` as Route}
            style={{ textDecoration: "none", color: "var(--qgi-text)" }}
          >
            <div style={{ fontSize: "17px", fontWeight: 600, lineHeight: 1.2 }}>
              {study.country}
            </div>
            <div
              style={{
                fontSize: "10.5px",
                color: "var(--qgi-text-dim)",
                letterSpacing: "0.5px",
                fontFamily: "ui-monospace, monospace",
                marginTop: "2px",
              }}
            >
              {study.iso} · Compound Risk {study.compound_score.toFixed(1)} ·{" "}
              {study.recipes.length} recipes
            </div>
          </Link>
        </div>
      </header>

      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
        {study.recipes.map((r) => {
          return (
            <Link
              key={r.recipe_id}
              href={`/trends/${r.recipe_id}` as Route}
              title={`${r.label} · ${r.score.toFixed(1)}`}
              style={{
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "4px 8px",
                borderRadius: "4px",
                background: `${familyColor(r.l1_id, r.l1_color)}1A`,
                border: `1px solid ${familyColor(r.l1_id, r.l1_color)}`,
                color: familyColor(r.l1_id, r.l1_color),
                fontSize: "11px",
                fontFamily: "ui-monospace, monospace",
                letterSpacing: "0.3px",
              }}
            >
              <RecipeIcon recipeId={r.recipe_id} size={13} strokeWidth={1.8} />
              {r.label}
              <span style={{ opacity: 0.7 }}>· {r.score.toFixed(0)}</span>
            </Link>
          );
        })}
      </div>

      <p
        style={{
          fontSize: "13.5px",
          lineHeight: 1.65,
          color: "var(--qgi-text)",
          margin: 0,
        }}
      >
        {study.narrative}
      </p>

      <footer
        style={{
          marginTop: "4px",
          paddingTop: "10px",
          borderTop: "1px solid var(--qgi-border)",
          display: "flex",
          justifyContent: "flex-end",
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        <Link
          href={`/countries/${study.iso.toLowerCase()}` as Route}
          style={{
            color: "var(--qgi-accent)",
            textDecoration: "none",
            letterSpacing: "0.3px",
          }}
        >
          Open the full {study.country} view →
        </Link>
      </footer>
    </article>
  );
}
