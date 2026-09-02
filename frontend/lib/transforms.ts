export type Transformation =
  | "raw"
  | "normalised"
  | "standardised"
  | "base_indexed"
  | "log"
  | "growth";

export const TRANSFORMATION_LABELS: Record<Transformation, string> = {
  raw: "Raw",
  normalised: "Normalised (0–1)",
  standardised: "Standardised (z-score)",
  base_indexed: "Base-year indexed",
  log: "Logarithmic",
  growth: "Growth rates (YoY %)",
};

export function applyTransformation(values: number[], mode: Transformation): number[] {
  if (values.length === 0) return [];

  switch (mode) {
    case "raw":
      return values;

    case "normalised": {
      const min = Math.min(...values);
      const max = Math.max(...values);
      const range = max - min;
      if (range === 0) return values.map(() => 0);
      return values.map((v) => (v - min) / range);
    }

    case "standardised": {
      const mean = values.reduce((s, v) => s + v, 0) / values.length;
      const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length;
      const std = Math.sqrt(variance);
      if (std === 0) return values.map(() => 0);
      return values.map((v) => (v - mean) / std);
    }

    case "base_indexed": {
      const base = values[0];
      if (base === 0) return values;
      return values.map((v) => (v / base) * 100);
    }

    case "log": {
      // Shift so all values are > 0 before log
      const min = Math.min(...values);
      const shift = min <= 0 ? Math.abs(min) + 1 : 0;
      return values.map((v) => Math.log(v + shift));
    }

    case "growth": {
      if (values.length < 2) return values;
      const result: number[] = [0]; // first year growth = 0 by convention
      for (let i = 1; i < values.length; i++) {
        const prev = values[i - 1];
        result.push(prev === 0 ? 0 : ((values[i] - prev) / Math.abs(prev)) * 100);
      }
      return result;
    }
  }
}
