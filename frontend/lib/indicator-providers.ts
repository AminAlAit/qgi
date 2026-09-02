/**
 * Provider display metadata for the indicator catalog — the single source of
 * truth so the taxonomy tree, the indicators table, and the
 * /methodology/indicators pie charts all colour + order the 8 providers
 * identically. Add a row here when a new provider enters
 * data/indicator-catalog.json; every surface picks it up.
 *
 * Colours are chosen to stay distinguishable in both themes and from each
 * other (no two adjacent-in-order providers share a hue).
 */
export const PROVIDER_COLOR: Record<string, string> = {
  "World Bank": "#38bdf8", // cyan-blue
  "V-Dem": "#7B5EE6", // violet
  UCDP: "#E0603D", // red-orange (conflict)
  FAOSTAT: "#3FBF8F", // green
  UNHCR: "#E0A33C", // amber
  ILOSTAT: "#C2506A", // rose
  OWID: "#B074C9", // magenta
  UNDP: "#4F86C6", // steel blue
};

/** Provider display order, largest provider first. */
export const PROVIDER_ORDER = [
  "World Bank",
  "V-Dem",
  "UCDP",
  "FAOSTAT",
  "UNHCR",
  "ILOSTAT",
  "OWID",
  "UNDP",
];
