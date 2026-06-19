"""bake_pattern_scdis.py — cascade SCDI baker (§H of the frontend zero-mocks bake).

Produces ``data/cascade/pattern-scdis.json`` = ``{ slug: PatternIndicator[] }`` — the
real replacement for ``lib/cascade-patterns/scdi-mock.ts``'s ``MOCKED_INDICATORS``.
Once the file lands, the frontend swap is one line (read it instead of the static map)
and ``/patterns/[slug]`` un-redirects (it currently redirects to ``/patterns`` so no
mock detail is ever shown — "zero mocks").

Pipeline (founder directive ``feedback_cascade_batch_ranking``, 2026-05-31):

  1. Read the pre-baked **pair-windows** (the ``pipeline-pair-windows-generator``
     output, already top-patterns-per-pair). Each window carries length / start-years /
     #indicators / correlation, plus ``ind`` (``indicator_numeric_ids``) once the
     generator's SELECT is enriched — see ``cascade-patterns-scdi-reply-v2`` §2.
  2. Re-rank candidate windows by the **balanced score** (``scdi_core`` — NOT PPS,
     which is length-biased) and **greedy-fill** to the Vercel size cap (NOT a fixed N).
  3. For each selected pattern, emit per-indicator SCDI detail: ``series_a`` /
     ``series_b`` (12-pt z-score trajectories from the indicator panels), ``pearson_r``,
     ``direction``.

Terminology: cascade country relationships are **patterns**, never "pairs" (founder rule).

The PatternIndicator contract (mirrors ``scdi-mock.ts``)::

    { code, numeric_id, name, sector, pearson_r, direction("same"|"opposite"),
      series_a: number[12], series_b: number[12] }

Slug: 4-segment aligned ``{a}-{b}-{startA}-{endA}`` or 5-segment offset
``{a}-{b}-{startA}-{startB}-{len}``, iso2 in alphabetical order — produced by
``scdi_core.build_slug``. ``series_a``/``series_b`` follow the slug's A/B order.

PREREQUISITE to RUN: pair-windows must carry ``ind``. That column
(``indicator_numeric_ids``) already exists in ``qgi_data.patterns``; the generator
Lambda just adds it to its SELECT (one column — the table already has it). Windows
without ``ind`` are skipped with a loud count, so a partial run is obvious rather than
silently empty.

Runs locally (pair-windows live in ``qgi-frontend/data/pair-windows``; panels via the
same sync the TE bake uses) or in-region as a Batch job. No egress beyond the panels
the TE bake already pulls.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scdi_core as sc  # noqa: E402

LOG = logging.getLogger("bake_pattern_scdis")

# Per-PatternIndicator JSON footprint estimate (code+name+sector + 2×12 floats +
# keys) used to greedy-fill to the Vercel cap. ~260 B is a deliberately generous
# upper bound so the baked file lands UNDER the cap, never over.
_BYTES_PER_INDICATOR = 260
_BYTES_PER_PATTERN_OVERHEAD = 120  # slug key + array brackets

DEFAULT_EPOCHS = 12
DEFAULT_SIZE_CAP_MB = 40.0


# ---------------------------------------------------------------------------
# Reference loaders (pure — operate on already-parsed JSON)
# ---------------------------------------------------------------------------
def load_indexes(entries: list[dict]) -> dict[int, dict]:
    """``numeric_id -> {code, name, sector}`` from ``indexes.json`` entries
    (each entry is ``{id, numeric_id, name, sector, ...}`` — ``id`` is the code)."""
    out: dict[int, dict] = {}
    for e in entries:
        nid = e.get("numeric_id")
        if nid is None:
            continue
        out[int(nid)] = {
            "code": e["id"],
            "name": e.get("name", e["id"]),
            "sector": e.get("sector", ""),
        }
    return out


def load_partner_meta(partners_index: dict) -> dict[int, dict]:
    """``numeric_id -> {a2, name}`` from ``country-partners-index.json`` (partner
    entries carry ``p`` = numeric id, ``a2`` = iso2, ``n`` = country name). The name
    is the panel join key (panels are keyed by country name). Relies on the index being
    bidirectional (A lists B and B lists A) — the generator writes both directions, so
    every country that appears as a window endpoint also appears as a partner entry."""
    out: dict[int, dict] = {}
    for partners in partners_index.values():
        for p in partners:
            pid = int(p["p"])
            if pid not in out:
                out[pid] = {"a2": p.get("a2", ""), "name": p.get("n", "")}
    return out


# ---------------------------------------------------------------------------
# Candidate windows + selection
# ---------------------------------------------------------------------------
def candidate_windows(pair_windows: dict[str, dict]) -> list[dict]:
    """Flatten ``{country_id: {partner_id: {top: [win...], hist}}}`` into a flat list
    of candidate windows. The file-side country is country A (its ``sa`` is start_a;
    the partner's ``sb`` is start_b). ``ind`` is carried through when present."""
    out: list[dict] = []
    for a_id_str, partners in pair_windows.items():
        try:
            a_id = int(a_id_str)
        except (TypeError, ValueError):
            continue
        for b_id_str, rec in (partners or {}).items():
            try:
                b_id = int(b_id_str)
            except (TypeError, ValueError):
                continue
            for w in (rec or {}).get("top", []):
                out.append(
                    {
                        "a_id": a_id,
                        "b_id": b_id,
                        "l": int(w["l"]),
                        "sa": int(w["sa"]),
                        "sb": int(w["sb"]),
                        "ic": int(w.get("ic", 0)),
                        "ac": float(w.get("ac", 0.0)),
                        "pps": float(w.get("pps", 0.0)),
                        "ind": [int(x) for x in (w.get("ind") or [])],
                    }
                )
    return out


def representative_per_pair(cands: list[dict]) -> list[dict]:
    """One showcase window per canonical (min_id, max_id) pair: the richest window —
    most indicators, then highest correlation, then longest. Balanced ranking then
    decides which *pairs* ship; this only de-dups A→B vs B→A and multiple windows of
    the same pair down to its single best representative."""
    best: dict[tuple[int, int], tuple[tuple, dict]] = {}
    for c in cands:
        key = (min(c["a_id"], c["b_id"]), max(c["a_id"], c["b_id"]))
        # Richness = the ACTUAL enriched id count (len(ind)), not the recorded `ic`
        # (which can lag the shipped ids after partial enrichment) — keeps de-dup and
        # the balanced rank below consistent on the same source of truth.
        rank = (len(c["ind"]) or c["ic"], c["ac"], c["l"])
        prev = best.get(key)
        if prev is None or rank > prev[0]:
            best[key] = (rank, c)
    return [c for _, c in best.values()]


def estimate_pattern_bytes(window: dict) -> int:
    """Greedy-fill cost estimate for one pattern: its indicator count (the actual
    ``ind`` length when enriched, else the recorded ``ic``) × per-indicator footprint."""
    n = len(window["ind"]) or window["ic"] or 0
    return n * _BYTES_PER_INDICATOR + _BYTES_PER_PATTERN_OVERHEAD


def select_patterns(cands: list[dict], size_cap_bytes: int) -> tuple[list[dict], int]:
    """De-dup to one window per pair, then balanced-rank + greedy-fill to the cap
    (delegates the ranking maths to the tested ``scdi_core``). Returns
    ``(selected_windows_in_rank_order, total_estimated_bytes)``."""
    reps = representative_per_pair(cands)
    # scdi_core.rank_and_fill keys on corr/length/n_ind — map the window fields in
    # (it returns the SAME dicts, so a_id/b_id/sa/sb/ind survive). n_ind is the ACTUAL
    # enriched id count (len(ind)) so the balanced rank and estimate_pattern_bytes agree
    # on the same source of truth — NOT the recorded `ic`, which can lag post-enrichment.
    for r in reps:
        r["corr"], r["length"] = r["ac"], r["l"]
        r["n_ind"] = len(r["ind"]) or r["ic"]
    return sc.rank_and_fill(reps, size_cap_bytes, estimate_pattern_bytes)


# ---------------------------------------------------------------------------
# Slug + orientation
# ---------------------------------------------------------------------------
def slug_and_orientation(window: dict, partner_meta: dict[int, dict]) -> tuple[str, dict, dict]:
    """Build the iso2-year slug (alphabetical iso2 order) and return the two countries
    oriented to the slug: ``(slug, first, second)`` where first/second are
    ``{a2, start, country_id, name}``. ``series_a`` is first's trajectory, ``series_b``
    is second's — matching the slug's A/B order so the frontend overlay is consistent."""
    a_id, b_id = window["a_id"], window["b_id"]
    a_meta = partner_meta.get(a_id, {})
    b_meta = partner_meta.get(b_id, {})
    A = {"a2": a_meta.get("a2", ""), "start": window["sa"], "country_id": a_id, "name": a_meta.get("name", "")}
    B = {"a2": b_meta.get("a2", ""), "start": window["sb"], "country_id": b_id, "name": b_meta.get("name", "")}
    first, second = (A, B) if A["a2"] <= B["a2"] else (B, A)
    slug = sc.build_slug(first["a2"], second["a2"], first["start"], second["start"], window["l"])
    return slug, first, second


# ---------------------------------------------------------------------------
# Per-indicator SCDI detail
# ---------------------------------------------------------------------------
def aligned_series(
    value_at: Callable[[str, int], float | None],
    first_name: str,
    first_start: int,
    second_name: str,
    second_start: int,
    length: int,
) -> tuple[list[float], list[float]]:
    """Walk the window position-by-position (position k = first[start+k] vs
    second[start+k] — handles the offset case where the two countries start in
    different years). A position is kept only when BOTH countries have a value there,
    so the returned series stay aligned and equal-length for pearson + z-score."""
    raw_first: list[float] = []
    raw_second: list[float] = []
    for k in range(length):
        va = value_at(first_name, first_start + k)
        vb = value_at(second_name, second_start + k)
        if va is None or vb is None:
            continue
        raw_first.append(va)
        raw_second.append(vb)
    return raw_first, raw_second


def build_pattern_indicators(
    window: dict,
    first: dict,
    second: dict,
    indexes: dict[int, dict],
    panel_value_at: Callable[[str], Callable[[str, int], float | None]],
    epochs: int = DEFAULT_EPOCHS,
) -> list[dict]:
    """Build the ``PatternIndicator[]`` for one selected pattern. ``panel_value_at(code)``
    returns a ``(country_name, year) -> value|None`` accessor for that indicator's panel.
    Indicators with no usable aligned data for this window are dropped (so the grid
    never renders an empty sparkline)."""
    out: list[dict] = []
    for nid in window["ind"]:
        meta = indexes.get(int(nid))
        if not meta:
            continue
        value_at = panel_value_at(meta["code"])
        raw_first, raw_second = aligned_series(
            value_at, first["name"], first["start"], second["name"], second["start"], window["l"]
        )
        if len(raw_first) < 2:  # need ≥2 aligned points for correlation + a trajectory
            continue
        r = sc.pearson_r(raw_first, raw_second)
        out.append(
            {
                "code": meta["code"],
                "numeric_id": int(nid),
                "name": meta["name"],
                "sector": meta["sector"],
                "pearson_r": r if r is not None else 0.0,
                "direction": sc.direction(r) or "same",
                "series_a": sc.zscore_downsample(raw_first, epochs),
                "series_b": sc.zscore_downsample(raw_second, epochs),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Bake orchestration (pure — all I/O injected)
# ---------------------------------------------------------------------------
def bake(
    pair_windows: dict[str, dict],
    indexes_entries: list[dict],
    partners_index: dict,
    panel_value_at: Callable[[str], Callable[[str, int], float | None]],
    size_cap_bytes: int,
    epochs: int = DEFAULT_EPOCHS,
) -> dict[str, list[dict]]:
    """End-to-end bake with every I/O dependency injected (so it is fully unit-testable).
    Returns the ``{slug: PatternIndicator[]}`` map. Patterns whose every indicator drops
    out (no panel data in-window) are omitted entirely rather than shipped empty."""
    indexes = load_indexes(indexes_entries)
    partner_meta = load_partner_meta(partners_index)

    cands = candidate_windows(pair_windows)
    enriched = [c for c in cands if c["ind"]]
    if not enriched:
        LOG.warning(
            "No candidate windows carry `ind` (indicator_numeric_ids). Enrich the "
            "pipeline-pair-windows-generator SELECT first (see cascade-patterns-scdi-"
            "reply-v2 §2) — emitting an empty SCDI map."
        )
    elif len(enriched) < len(cands):
        LOG.warning(
            "%d/%d candidate windows lack `ind` and were skipped (un-enriched).",
            len(cands) - len(enriched),
            len(cands),
        )

    selected, total_bytes = select_patterns(enriched, size_cap_bytes)
    LOG.info(
        "Selected %d patterns (balanced rank, greedy-fill) ≈ %.1f MB / %.1f MB cap.",
        len(selected),
        total_bytes / 1e6,
        size_cap_bytes / 1e6,
    )

    out: dict[str, list[dict]] = {}
    dropped_empty = 0
    for window in selected:
        slug, first, second = slug_and_orientation(window, partner_meta)
        if not first["a2"] or not second["a2"] or not first["name"] or not second["name"]:
            LOG.warning("Skipping window %s-%s: missing iso2/name in partner index.", window["a_id"], window["b_id"])
            continue
        indicators = build_pattern_indicators(window, first, second, indexes, panel_value_at, epochs)
        if not indicators:
            dropped_empty += 1
            continue
        out[slug] = indicators

    if dropped_empty:
        LOG.info("Dropped %d selected patterns with no in-window panel data.", dropped_empty)
    LOG.info("Baked SCDI detail for %d patterns.", len(out))
    return out


# ---------------------------------------------------------------------------
# Real I/O wiring + CLI
# ---------------------------------------------------------------------------
def _make_panel_value_at(panel_root: Path) -> Callable[[str], Callable[[str, int], float | None]]:
    """Real panel accessor factory: ``code -> ((country, year) -> value|None)``. Each
    indicator panel (``panel_root/{code}`` parquet, columns country/year/value) is
    loaded once and indexed into a ``{(country, year): value}`` dict, cached per code."""
    import pandas as pd

    panel_cache: dict[str, dict[tuple[str, int], float]] = {}

    def value_at_factory(code: str) -> Callable[[str, int], float | None]:
        idx = panel_cache.get(code)
        if idx is None:
            idx = {}
            p = panel_root / code
            if p.exists():
                try:
                    df = pd.read_parquet(p)
                    valid = df[df["value"].notna()]
                    for country, year, value in zip(valid["country"], valid["year"], valid["value"]):
                        idx[(str(country), int(year))] = float(value)
                except Exception as exc:  # noqa: BLE001 — a bad panel must not kill the bake
                    LOG.warning("Panel %s unreadable (%s) — its indicator is skipped.", code, exc)
            panel_cache[code] = idx

        def value_at(country: str, year: int) -> float | None:
            return idx.get((country, year))

        return value_at

    return value_at_factory


def _load_pair_windows_dir(pw_dir: Path) -> dict[str, dict]:
    """Read every ``{country_id}.json`` in the pair-windows dir into one
    ``{country_id: {partner_id: record}}`` map."""
    merged: dict[str, dict] = {}
    for f in sorted(pw_dir.glob("*.json")):
        try:
            merged[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Skipping unreadable pair-windows file %s (%s).", f.name, exc)
    return merged


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Bake cascade SCDI per-pattern indicator detail (§H).")
    ap.add_argument(
        "--pair-windows-dir", required=True, type=Path, help="dir of {country_id}.json (enriched with `ind`)"
    )
    ap.add_argument("--panel-root", required=True, type=Path, help="dir of per-code indicator panels (parquet)")
    ap.add_argument("--indexes", required=True, type=Path, help="indexes.json (numeric_id -> code/name/sector)")
    ap.add_argument(
        "--partners-index", required=True, type=Path, help="country-partners-index.json (numeric_id -> a2/name)"
    )
    ap.add_argument("--out", required=True, type=Path, help="output pattern-scdis.json")
    ap.add_argument("--size-cap-mb", type=float, default=DEFAULT_SIZE_CAP_MB, help="Vercel budget for the SCDI file")
    ap.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS, help="z-score trajectory points per country")
    args = ap.parse_args(argv)

    pair_windows = _load_pair_windows_dir(args.pair_windows_dir)
    indexes_entries = json.loads(args.indexes.read_text(encoding="utf-8"))
    partners_index = json.loads(args.partners_index.read_text(encoding="utf-8"))
    panel_value_at = _make_panel_value_at(args.panel_root)

    result = bake(
        pair_windows,
        indexes_entries,
        partners_index,
        panel_value_at,
        size_cap_bytes=int(args.size_cap_mb * 1e6),
        epochs=args.epochs,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    size_bytes = args.out.stat().st_size
    cap_bytes = int(args.size_cap_mb * 1e6)
    if size_bytes > cap_bytes:
        # The greedy-fill budgets on an ESTIMATE; if the real file still overshoots,
        # the per-indicator byte estimate under-counted — surface it loudly rather than
        # silently ship an over-cap file to Vercel.
        LOG.warning(
            "Baked file %.1f MB EXCEEDS the %.1f MB cap — per-indicator byte estimate "
            "under-counted; lower --size-cap-mb or raise _BYTES_PER_INDICATOR.",
            size_bytes / 1e6,
            cap_bytes / 1e6,
        )
    LOG.info("Wrote %s (%d patterns, %.1f KB).", args.out, len(result), size_bytes / 1024)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
