/**
 * Shared, framework-neutral data for StatPie. Kept OUT of the "use client"
 * StatPie module so server components can import PIE_PALETTE (a real array) and
 * the PieSlice type directly — importing a value from a client module yields a
 * client-reference proxy, not the array, which silently breaks colour lookups.
 */
export interface PieSlice {
  label: string;
  value: number;
  color: string;
}

export const PIE_PALETTE = [
  "#38bdf8",
  "#7B5EE6",
  "#3FBF8F",
  "#E68F29",
  "#E0556B",
  "#6FB1FC",
  "#B6924A",
  "#4FD1C5",
  "#C77DFF",
  "#F4A261",
  "#8AB4F8",
  "#9AE6B4",
  "#F08FB0",
  "#B8C0CC",
];
