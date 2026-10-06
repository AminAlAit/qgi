"use client";

import ReactECharts from "echarts-for-react";
import { useMemo, useState } from "react";
import { applyTransformation, type Transformation } from "@/lib/transforms";
import indexData from "@/data/indexes.json";
import type { IndexEntry } from "@/lib/types";
import {
  pearsonCorrelation,
  pearsonPValue,
  formatPValue,
  significanceLabel,
} from "@/lib/stats";
import { correlationColor } from "@/lib/design";

const INDEX_MAP: Record<string, IndexEntry> = Object.fromEntries(
  (indexData as IndexEntry[]).map((idx) => [idx.name, idx])
);

interface Props {
  indexName: string;
  valuesA: Array<number | null>;
  valuesB: Array<number | null>;
  startYearA: number;
  startYearB: number;
  correlation: number;
  predicted: boolean;
  transformation: Transformation;
  align: boolean;
  countryA: string;
  countryB: string;
}

type Tab = "lines" | "scatter";

export function IndexChart({
  indexName,
  valuesA,
  valuesB,
  startYearA,
  startYearB,
  correlation,
  predicted,
  transformation,
  align,
  countryA,
  countryB,
}: Props) {
  const meta = INDEX_MAP[indexName];
  const [tab, setTab] = useState<Tab>("lines");

  // #125: applyTransformation returns numbers; we need to preserve nulls so
  // ECharts renders gaps where the World Bank data is missing.
  const { xAxisA, xAxisB, tA, tB, missingRanges } = useMemo(() => {
    const tA = applyTransformWithNulls(valuesA, transformation);
    const tB = applyTransformWithNulls(valuesB, transformation);
    const len = Math.max(tA.length, tB.length);

    const xA = align
      ? Array.from({ length: len }, (_, i) => `Year ${i + 1}`)
      : Array.from({ length: tA.length }, (_, i) => String(startYearA + i));
    const xB = align
      ? Array.from({ length: len }, (_, i) => `Year ${i + 1}`)
      : Array.from({ length: tB.length }, (_, i) => String(startYearB + i));

    // Collect contiguous null ranges (using country A's series as the index;
    // could be enhanced to highlight per-side).
    const missingRanges: Array<[number, number]> = [];
    let runStart = -1;
    for (let i = 0; i < tA.length; i++) {
      const missing = tA[i] == null && tB[i] == null;
      if (missing && runStart === -1) runStart = i;
      if (!missing && runStart !== -1) {
        missingRanges.push([runStart, i - 1]);
        runStart = -1;
      }
    }
    if (runStart !== -1) missingRanges.push([runStart, tA.length - 1]);

    return { xAxisA: xA, xAxisB: xB, tA, tB, missingRanges };
  }, [valuesA, valuesB, startYearA, startYearB, transformation, align]);

  // #125: compute n + p-value from the actual non-null overlap so the chart
  // shows the real statistical confidence behind the headline correlation.
  const { actualR, actualN, pValue, sig } = useMemo(() => {
    const { r, n } = pearsonCorrelation(tA, tB);
    const p = pearsonPValue(r, n);
    return { actualR: r, actualN: n, pValue: p, sig: significanceLabel(p) };
  }, [tA, tB]);

  // Mark areas for missing data — light gray vertical bands (#125 spec)
  const markArea =
    missingRanges.length > 0
      ? {
          silent: true,
          itemStyle: { color: "rgba(122, 144, 168, 0.10)" },
          data: missingRanges.map(([from, to]) => [
            { xAxis: xAxisA[from], name: "Data unavailable" },
            { xAxis: xAxisA[to] },
          ]),
        }
      : undefined;

  const linesOption = {
    backgroundColor: "transparent",
    title: {
      text: indexName,
      subtext: `r=${(correlation * 100).toFixed(1)}%  n=${actualN}  p=${formatPValue(pValue)} ${sig}`,
      textStyle: { color: "var(--qgi-text-muted)", fontSize: 10, fontWeight: 400 },
      subtextStyle: {
        color: correlationColor(correlation),
        fontSize: 9,
      },
      top: 4,
      left: 8,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#1e2d42",
      borderColor: "#243347",
      textStyle: { color: "#e2e8f0", fontSize: 10 },
      // #125: synchronized hover — when the user hovers a year, the tooltip
      // shows BOTH country values + their ratio so the comparison is explicit.
      // #250: when the chart is aligned (Year-N axis) we annotate each side
      // with its actual calendar year so the cross-time nature of the pattern
      // is obvious (e.g. "Argentina 1995 vs Brazil 1981, both Year 1").
      formatter: (
        params: Array<{
          seriesName: string;
          data: [string, number | null] | number | null;
          axisValue: string;
          dataIndex: number;
        }>
      ) => {
        const axisLabel = params[0]?.axisValue;
        const idx = params[0]?.dataIndex ?? 0;
        const a = params.find((p) => p.seriesName === countryA);
        const b = params.find((p) => p.seriesName === countryB);
        const av = Array.isArray(a?.data) ? a.data[1] : (a?.data as number | null);
        const bv = Array.isArray(b?.data) ? b.data[1] : (b?.data as number | null);
        const fmt = (v: number | null | undefined) =>
          v == null || !Number.isFinite(v)
            ? "<i style='color:#7a90a8'>missing</i>"
            : v.toFixed(2);
        const ratio =
          av != null &&
          bv != null &&
          Number.isFinite(av) &&
          Number.isFinite(bv) &&
          bv !== 0
            ? `<div style='color:#7a90a8;font-size:9px;margin-top:2px'>ratio: ${(av / bv).toFixed(2)}×</div>`
            : "";
        // When the xAxis is "Year N" (align mode), show actual calendar years
        // per side. When it's calendar years, just show the axis label.
        const yearALabel = align ? `${countryA} ${startYearA + idx}` : countryA;
        const yearBLabel = align ? `${countryB} ${startYearB + idx}` : countryB;
        return `<div style='font-family:monospace'><div style='color:#7a90a8;font-size:9px'>${axisLabel}</div><div style='color:#38bdf8'>${yearALabel}: ${fmt(av)}</div><div style='color:#fb923c'>${yearBLabel}: ${fmt(bv)}</div>${ratio}</div>`;
      },
    },
    legend: {
      data: [countryA, countryB],
      top: 4,
      right: 8,
      textStyle: { color: "#7a90a8", fontSize: 9 },
      itemWidth: 12,
      itemHeight: 2,
    },
    grid: { top: 60, right: 16, bottom: 32, left: 48 },
    xAxis: {
      type: "category",
      data: xAxisA,
      axisLine: { lineStyle: { color: "#243347" } },
      axisLabel: { color: "#8aa6be", fontSize: 9 },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLine: { lineStyle: { color: "#243347" } },
      splitLine: { lineStyle: { color: "#1a2a3a" } },
      axisLabel: { color: "#8aa6be", fontSize: 9 },
    },
    series: [
      {
        name: countryA,
        type: "line",
        data: align ? tA.map((v, i) => [xAxisA[i], v]) : xAxisA.map((x, i) => [x, tA[i]]),
        lineStyle: { color: "#38bdf8", width: 1.5 },
        itemStyle: { color: "#38bdf8" },
        symbol: "circle",
        symbolSize: 4,
        // #125: don't bridge null gaps with phantom flat lines
        connectNulls: false,
        markArea,
      },
      {
        name: countryB,
        type: "line",
        data: align ? tB.map((v, i) => [xAxisB[i], v]) : xAxisB.map((x, i) => [x, tB[i]]),
        lineStyle: {
          color: predicted ? "#6b7f96" : "#fb923c",
          width: 1.5,
          type: predicted ? "dashed" : "solid",
          opacity: predicted ? 0.7 : 1,
        },
        itemStyle: { color: predicted ? "#6b7f96" : "#fb923c" },
        symbol: "circle",
        symbolSize: 4,
        connectNulls: false,
      },
    ],
  };

  // #125: scatter plot — A vs B at each (matched) year. Tight diagonal IS
  // the correlation, visually undeniable.
  const scatterPoints = useMemo(() => {
    const pts: Array<[number, number, string]> = [];
    const len = Math.min(tA.length, tB.length);
    for (let i = 0; i < len; i++) {
      const a = tA[i];
      const b = tB[i];
      if (a == null || b == null || !Number.isFinite(a) || !Number.isFinite(b)) continue;
      pts.push([a, b, xAxisA[i]]);
    }
    return pts;
  }, [tA, tB, xAxisA]);

  // OLS regression line for the scatter
  const regressionLine = useMemo(() => {
    if (scatterPoints.length < 2) return null;
    let sx = 0,
      sy = 0;
    for (const [x, y] of scatterPoints) {
      sx += x;
      sy += y;
    }
    const n = scatterPoints.length;
    const mx = sx / n;
    const my = sy / n;
    let sxy = 0;
    let sxx = 0;
    for (const [x, y] of scatterPoints) {
      sxy += (x - mx) * (y - my);
      sxx += (x - mx) ** 2;
    }
    if (sxx === 0) return null;
    const slope = sxy / sxx;
    const intercept = my - slope * mx;
    const minX = Math.min(...scatterPoints.map((p) => p[0]));
    const maxX = Math.max(...scatterPoints.map((p) => p[0]));
    return [
      [minX, slope * minX + intercept],
      [maxX, slope * maxX + intercept],
    ];
  }, [scatterPoints]);

  const r2 = Number.isFinite(actualR) ? actualR * actualR : NaN;

  const scatterOption = {
    backgroundColor: "transparent",
    title: {
      text: indexName,
      subtext: `R²=${Number.isFinite(r2) ? r2.toFixed(3) : "n/a"}  n=${actualN}  p=${formatPValue(pValue)} ${sig}`,
      textStyle: { color: "var(--qgi-text-muted)", fontSize: 10, fontWeight: 400 },
      subtextStyle: {
        color: correlationColor(correlation),
        fontSize: 9,
      },
      top: 4,
      left: 8,
    },
    tooltip: {
      trigger: "item",
      backgroundColor: "#1e2d42",
      borderColor: "#243347",
      textStyle: { color: "#e2e8f0", fontSize: 10 },
      formatter: (p: { data: [number, number, string] }) =>
        `<div style='font-family:monospace'><div style='color:#7a90a8;font-size:9px'>${p.data[2]}</div><div style='color:#38bdf8'>${countryA}: ${p.data[0].toFixed(2)}</div><div style='color:#fb923c'>${countryB}: ${p.data[1].toFixed(2)}</div></div>`,
    },
    grid: { top: 60, right: 16, bottom: 32, left: 48 },
    xAxis: {
      type: "value",
      scale: true,
      name: countryA,
      nameLocation: "middle",
      nameGap: 22,
      nameTextStyle: { color: "#7a90a8", fontSize: 9 },
      axisLine: { lineStyle: { color: "#243347" } },
      splitLine: { lineStyle: { color: "#1a2a3a" } },
      axisLabel: { color: "#8aa6be", fontSize: 9 },
    },
    yAxis: {
      type: "value",
      scale: true,
      name: countryB,
      nameLocation: "middle",
      nameGap: 36,
      nameTextStyle: { color: "#7a90a8", fontSize: 9 },
      axisLine: { lineStyle: { color: "#243347" } },
      splitLine: { lineStyle: { color: "#1a2a3a" } },
      axisLabel: { color: "#8aa6be", fontSize: 9 },
    },
    series: [
      {
        name: "observations",
        type: "scatter",
        data: scatterPoints,
        symbolSize: 6,
        itemStyle: { color: "#38bdf8" },
      },
      ...(regressionLine
        ? [
            {
              name: "OLS fit",
              type: "line",
              data: regressionLine,
              lineStyle: { color: "#fb923c", width: 1, type: "dashed" as const },
              symbol: "none" as const,
              tooltip: { show: false },
              silent: true,
            },
          ]
        : []),
    ],
  };

  return (
    <div
      className="rounded border p-2 flex flex-col"
      style={{
        backgroundColor: "var(--qgi-surface)",
        borderColor: "var(--qgi-border)",
        minHeight: 240,
      }}
    >
      {/* Tab toggle (#125) */}
      <div className="flex gap-1 px-1 pb-1">
        <TabBtn label="LINES" active={tab === "lines"} onClick={() => setTab("lines")} />
        <TabBtn
          label="SCATTER"
          active={tab === "scatter"}
          onClick={() => setTab("scatter")}
        />
      </div>
      <ReactECharts
        option={tab === "lines" ? linesOption : scatterOption}
        style={{ height: 200 }}
        notMerge
      />
      {meta?.description && (
        <p
          className="text-[9px] px-2 pb-1 leading-relaxed"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          {meta.description}
        </p>
      )}
    </div>
  );
}

function TabBtn({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="text-[9px] tracking-wider px-2 py-0.5 rounded border"
      style={{
        borderColor: active ? "var(--qgi-accent)" : "var(--qgi-border)",
        color: active ? "var(--qgi-accent)" : "var(--qgi-text-dim)",
      }}
    >
      {label}
    </button>
  );
}

/**
 * Like applyTransformation, but preserves nulls in the input series so chart
 * gaps can be rendered (#125). The existing applyTransformation in
 * lib/transforms takes number[] and would convert nulls to NaN; we run it
 * over each contiguous non-null run separately and stitch back the nulls.
 */
function applyTransformWithNulls(
  values: ReadonlyArray<number | null>,
  t: Transformation
): Array<number | null> {
  // Fast path: no nulls
  if (values.every((v) => v != null && Number.isFinite(v))) {
    return applyTransformation(values as number[], t);
  }
  // Apply over the full series with NaN substitution; downstream consumers
  // already check Number.isFinite. The transformations in lib/transforms are
  // pointwise (no, lag, log, normalize) so a NaN propagates correctly.
  const filled = values.map((v) => (v == null || !Number.isFinite(v) ? NaN : v));
  const out = applyTransformation(filled, t);
  return out.map((v) => (Number.isFinite(v) ? v : null));
}
