"use client";

import { Sparkles } from "lucide-react";

export interface GenerateComparisonReportButtonProps {
  countryA: string;
  countryB: string;
}

export function GenerateComparisonReportButton({
  countryA,
  countryB,
}: GenerateComparisonReportButtonProps) {
  return (
    <button
      data-tour="generate-comparison-report-button"
      type="button"
      disabled
      aria-disabled="true"
      aria-label={`Generate Comparison Report for ${countryA} vs ${countryB} (coming soon)`}
      title={`Coming soon: a thinking AI model reads everything QGI knows about ${countryA} and ${countryB}, the trends in play, the indicator drivers, the analogues, and writes you a side-by-side intelligence report via API. Disabled today; live in a future release.`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "8px",
        padding: "7px 12px",
        background:
          "linear-gradient(135deg, rgba(56,189,248,0.18) 0%, rgba(56,189,248,0.05) 100%)",
        border: "1px solid rgba(56,189,248,0.55)",
        borderRadius: "5px",
        color: "var(--qgi-text)",
        fontSize: "11.5px",
        fontWeight: 600,
        letterSpacing: "0.3px",
        cursor: "not-allowed",
        opacity: 0.85,
        whiteSpace: "nowrap",
      }}
    >
      <Sparkles
        size={13}
        strokeWidth={1.8}
        aria-hidden="true"
        color="var(--qgi-accent)"
      />
      <span style={{ fontFamily: "var(--font-qg-brand)" }}>
        Generate Comparison Report
      </span>
      <span
        style={{
          fontSize: "9px",
          padding: "1px 6px",
          background: "rgba(56,189,248,0.25)",
          border: "1px solid rgba(56,189,248,0.55)",
          color: "var(--qgi-accent)",
          borderRadius: "3px",
          letterSpacing: "0.5px",
          textTransform: "uppercase",
          fontWeight: 700,
          fontFamily: "var(--font-qg-brand)",
        }}
      >
        Soon
      </span>
    </button>
  );
}
