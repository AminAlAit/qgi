"use client";

/**
 * Cross-platform country flag using SVG icons from country-flag-icons.
 * Replaces emoji flags which don't render on Windows.
 *
 * Usage: <CountryFlag alpha2="US" size={24} />
 */
import { hasFlag } from "country-flag-icons";
import * as Flags3x2 from "country-flag-icons/react/3x2";

interface Props {
  alpha2: string;
  size?: number;
  className?: string;
  /**
   * T15 #308 a11y fix (2026-04-19): optional country name for screen
   * readers. When provided, the flag is announced as "<countryName> flag".
   * When omitted and the flag is decorative (adjacent text already names
   * the country), callers should pass `ariaHidden`.
   */
  countryName?: string;
  ariaHidden?: boolean;
}

export function CountryFlag({
  alpha2,
  size = 24,
  className,
  countryName,
  ariaHidden,
}: Props) {
  const code = alpha2?.toUpperCase();
  // Resolve the accessible label: explicit countryName wins, then alpha-2
  // ("US flag"), else a generic "Country flag" fallback for unknown codes.
  const ariaLabel = ariaHidden
    ? undefined
    : countryName
      ? `${countryName} flag`
      : code
        ? `${code} flag`
        : "Country flag";
  const commonA11y = ariaHidden
    ? { "aria-hidden": true as const }
    : { role: "img" as const, "aria-label": ariaLabel };

  if (!code || !hasFlag(code)) {
    // Fallback: show alpha-2 code in a badge
    return (
      <span
        className={`inline-flex items-center justify-center font-data text-[9px] font-bold rounded ${className ?? ""}`}
        style={{
          width: size * 1.5,
          height: size,
          backgroundColor: "var(--qgi-surface-2)",
          color: "var(--qgi-text-muted)",
        }}
        {...commonA11y}
      >
        {code || "??"}
      </span>
    );
  }

  const FlagComponent = (
    Flags3x2 as Record<string, React.ComponentType<React.SVGProps<SVGSVGElement>>>
  )[code];

  if (!FlagComponent) {
    return (
      <span
        className={`inline-flex items-center justify-center font-data text-[9px] font-bold rounded ${className ?? ""}`}
        style={{
          width: size * 1.5,
          height: size,
          backgroundColor: "var(--qgi-surface-2)",
          color: "var(--qgi-text-muted)",
        }}
        {...commonA11y}
      >
        {code}
      </span>
    );
  }

  // If className includes width/height utilities (e.g. w-[85%] h-auto),
  // don't set inline width/height which would override them.
  const hasCustomSize = className?.includes("w-") || className?.includes("h-");

  return (
    <FlagComponent
      className={className}
      style={
        hasCustomSize
          ? { borderRadius: 2 }
          : { width: size * 1.5, height: size, borderRadius: 2 }
      }
      {...commonA11y}
    />
  );
}
