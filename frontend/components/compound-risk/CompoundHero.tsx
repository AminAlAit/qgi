import { Layers } from "lucide-react";

interface Props {
  litAtThreshold: number;
  minThreshold: number;
  totalCountries: number;
}

export function CompoundHero({ litAtThreshold, minThreshold, totalCountries }: Props) {
  return (
    <section data-tour="compound-hero" style={{ marginBottom: "8px" }}>
      <div
        style={{
          color: "var(--qgi-accent)",
          fontSize: "10px",
          letterSpacing: "4px",
          textTransform: "uppercase",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "8px",
        }}
      >
        Compound Risk
      </div>
      <h1
        style={{
          fontSize: "32px",
          fontWeight: 600,
          lineHeight: 1.15,
          margin: "0 0 16px",
        }}
      >
        Where multiple crisis shapes pile up on the same country
      </h1>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(260px, 320px) 1fr",
          gap: "24px",
          alignItems: "stretch",
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "10px",
          padding: "24px",
        }}
      >
        {/* Big number */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "flex-start",
            borderRight: "1px solid var(--qgi-border)",
            paddingRight: "24px",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "8px",
            }}
          >
            <Layers size={18} strokeWidth={1.6} color="var(--qgi-accent)" />
            <span
              style={{
                fontSize: "10px",
                letterSpacing: "1.5px",
                fontFamily: "ui-monospace, monospace",
                color: "var(--qgi-text-dim)",
                textTransform: "uppercase",
              }}
            >
              Currently compounded
            </span>
          </div>
          <div
            style={{
              fontSize: "88px",
              fontWeight: 600,
              fontFamily: "ui-monospace, monospace",
              color: "var(--qgi-amber)",
              lineHeight: 1,
              letterSpacing: "-2px",
            }}
          >
            {litAtThreshold}
          </div>
          <div
            style={{
              marginTop: "10px",
              fontSize: "13px",
              color: "var(--qgi-text)",
              lineHeight: 1.45,
            }}
          >
            countries currently match{" "}
            <strong style={{ color: "var(--qgi-amber)" }}>{minThreshold} or more</strong>{" "}
            of our crisis recipes at once
          </div>
          <div
            style={{
              marginTop: "8px",
              fontSize: "10.5px",
              letterSpacing: "0.4px",
              fontFamily: "ui-monospace, monospace",
              color: "var(--qgi-text-dim)",
            }}
          >
            of {totalCountries} countries in the corpus
          </div>
        </div>

        {/* Explanation */}
        <div
          style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}
        >
          <p
            style={{
              fontSize: "14.5px",
              lineHeight: 1.6,
              color: "var(--qgi-text)",
              margin: "0 0 12px",
            }}
          >
            <strong>Compound Risk</strong> is a single 0-100 score that captures how
            strongly a country&apos;s recent signals resemble multiple crisis shapes at
            once. Civil-war shape <em>and</em> economic-recession shape <em>and</em>{" "}
            mass-protest shape can each light up on the same body politic. The score
            averages those resemblances, weighted toward the strongest, and is dampened
            when the country only matches a recipe or two.
          </p>
          <p
            style={{
              fontSize: "13px",
              lineHeight: 1.55,
              color: "var(--qgi-text-muted)",
              margin: 0,
            }}
          >
            The page answers one question:{" "}
            <em>where do structural pressures pile up on the same country?</em> It does
            not claim those pressures interact causally, nor that the recipes will fire
            jointly. It is a multi-lens resemblance read, bounded so the score does not
            grow simply because we ship more recipes.
          </p>
        </div>
      </div>
    </section>
  );
}
