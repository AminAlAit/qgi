"use client";

export default function PrintButton() {
  return (
    <button
      onClick={() => window.print()}
      className="px-4 py-2 rounded text-sm tracking-wide border transition-colors hover:bg-[var(--qgi-surface-2)] print:hidden"
      style={{
        borderColor: "var(--qgi-border)",
        color: "var(--qgi-text-muted)",
      }}
    >
      Print / Save PDF
    </button>
  );
}
