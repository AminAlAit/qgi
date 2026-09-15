"use client";

import { useEffect, useState } from "react";
import { IndexChart } from "@/components/patterns-v1/IndexChart";
import { correlationColor } from "@/lib/design";

interface ScdiEntry {
  indicator_numeric_id: number;
  index_name: string;
  sector: string;
  org: string;
  correlation: number;
  predicted: boolean;
  values_a: Array<number | null>;
  values_b: Array<number | null>;
}

interface DetailResponse {
  metadata: Record<string, string | number>;
  scdis: ScdiEntry[];
}

interface Props {
  country_a_id: string | number;
  country_b_id: string | number;
  start_year_a: number;
  start_year_b: number;
  length: number;
  countryAName: string;
  countryBName: string;
}

const PAGE_SIZE = 4;

export function PatternScdiPager({
  country_a_id,
  country_b_id,
  start_year_a,
  start_year_b,
  length,
  countryAName,
  countryBName,
}: Props) {
  const [scdis, setScdis] = useState<ScdiEntry[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "empty">("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [page, setPage] = useState(0);
  // Per-panel align state: keyed by indicator_numeric_id
  const [alignByPanel, setAlignByPanel] = useState<Record<number, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    // The resets below wipe stale page-position + alignment-toggle state when
    // the pattern slug changes, before the new fetch completes. The lint rule
    // for setStatus is a known false positive on fetch-on-prop-change patterns
    // (https://react.dev/learn/you-might-not-need-an-effect lists data
    // fetching as a legitimate effect use).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStatus("loading");
    setPage(0);
    setAlignByPanel({});

    const qs = new URLSearchParams({
      country_a: String(country_a_id),
      country_b: String(country_b_id),
      start_a: String(start_year_a),
      start_b: String(start_year_b),
      length: String(length),
    });

    fetch(`/api/patterns/detail?${qs.toString()}`)
      .then((res) => {
        if (!res.ok) {
          return res.json().then((body: { error?: string }) => {
            throw new Error(body?.error ?? `HTTP ${res.status}`);
          });
        }
        return res.json() as Promise<DetailResponse>;
      })
      .then((data) => {
        if (cancelled) return;
        const sorted = [...data.scdis].sort((a, b) => b.correlation - a.correlation);
        if (sorted.length === 0) {
          setStatus("empty");
        } else {
          setScdis(sorted);
          setStatus("idle");
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setErrorMessage(err instanceof Error ? err.message : "Failed to load indicators");
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [country_a_id, country_b_id, start_year_a, start_year_b, length]);

  const totalPages = Math.ceil(scdis.length / PAGE_SIZE);
  const pageItems = scdis.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  function toggleAlign(numId: number) {
    setAlignByPanel((prev) => ({ ...prev, [numId]: !prev[numId] }));
  }

  return (
    <section
      aria-labelledby="scdi-pager-heading"
      className="mb-5 rounded-lg border p-5"
      style={{
        backgroundColor: "var(--qgi-surface)",
        borderColor: "var(--qgi-border)",
      }}
    >
      <div className="flex items-center gap-2 mb-4">
        <h2
          id="scdi-pager-heading"
          className="text-xs tracking-widest uppercase font-semibold"
          style={{ color: "var(--qgi-text)" }}
        >
          Shared indicators
        </h2>
        {status === "idle" && scdis.length > 0 && (
          <span
            className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            {scdis.length} {scdis.length === 1 ? "indicator" : "indicators"}
          </span>
        )}
      </div>

      {status === "loading" && (
        <div className="flex items-center justify-center py-12">
          <span className="font-data text-xs" style={{ color: "var(--qgi-text-dim)" }}>
            Loading indicators...
          </span>
        </div>
      )}

      {status === "error" && (
        <div
          role="alert"
          className="rounded border-l-2 p-4 text-sm leading-relaxed"
          style={{
            borderLeftColor: "rgba(245, 158, 11, 0.6)",
            backgroundColor: "rgba(245, 158, 11, 0.06)",
            color: "var(--qgi-text-muted)",
          }}
        >
          <span
            className="block text-[10px] tracking-widest uppercase font-semibold mb-1"
            style={{ color: "rgba(245, 158, 11, 0.95)" }}
          >
            Indicator data unavailable
          </span>
          {errorMessage}
        </div>
      )}

      {status === "empty" && (
        <p className="text-xs py-6 text-center" style={{ color: "var(--qgi-text-dim)" }}>
          No shared indicators found for this pattern window.
        </p>
      )}

      {status === "idle" && scdis.length > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {pageItems.map((scdi) => {
              const aligned = alignByPanel[scdi.indicator_numeric_id] ?? false;
              return (
                <div key={scdi.indicator_numeric_id} className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 px-1">
                    <span
                      className="text-[9px] tracking-wider uppercase font-semibold px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor: "var(--qgi-surface-2)",
                        color: "var(--qgi-text-dim)",
                        border: "1px solid var(--qgi-border)",
                      }}
                    >
                      {scdi.sector}
                    </span>
                    <span
                      className="text-[9px] font-data font-semibold ml-auto"
                      style={{ color: correlationColor(scdi.correlation) }}
                    >
                      r={scdi.correlation.toFixed(3)}
                    </span>
                    <button
                      onClick={() => toggleAlign(scdi.indicator_numeric_id)}
                      title={
                        aligned
                          ? "Switch to calendar years"
                          : "Align to Year 1 / Year 2 / ..."
                      }
                      className="text-[9px] tracking-wider px-2 py-0.5 rounded border transition-colors"
                      style={{
                        borderColor: aligned ? "var(--qgi-accent)" : "var(--qgi-border)",
                        color: aligned ? "var(--qgi-accent)" : "var(--qgi-text-dim)",
                        backgroundColor: "transparent",
                      }}
                    >
                      {aligned ? "Aligned" : "Align"}
                    </button>
                  </div>

                  <IndexChart
                    indexName={scdi.index_name}
                    valuesA={scdi.values_a}
                    valuesB={scdi.values_b}
                    startYearA={start_year_a}
                    startYearB={start_year_b}
                    correlation={scdi.correlation}
                    predicted={scdi.predicted}
                    transformation="raw"
                    align={aligned}
                    countryA={countryAName}
                    countryB={countryBName}
                  />
                </div>
              );
            })}
          </div>

          {totalPages > 1 && (
            <div
              className="flex items-center justify-center gap-3 pt-2 border-t"
              style={{ borderColor: "var(--qgi-border)" }}
            >
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="text-[10px] tracking-widest uppercase px-3 py-1 rounded border transition-colors disabled:opacity-40"
                style={{
                  borderColor: "var(--qgi-border)",
                  color: page === 0 ? "var(--qgi-text-dim)" : "var(--qgi-text-muted)",
                  backgroundColor: "transparent",
                }}
              >
                Prev
              </button>
              <span
                className="text-[10px] font-data tracking-wider"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                Page {page + 1} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page === totalPages - 1}
                className="text-[10px] tracking-widest uppercase px-3 py-1 rounded border transition-colors disabled:opacity-40"
                style={{
                  borderColor: "var(--qgi-border)",
                  color:
                    page === totalPages - 1
                      ? "var(--qgi-text-dim)"
                      : "var(--qgi-text-muted)",
                  backgroundColor: "transparent",
                }}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
