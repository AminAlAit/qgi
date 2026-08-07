#!/usr/bin/env python3
"""
enrich_analogues_common_length.py — rebuild analogues-enriched.json so
that every analogue row for a given (subject, category) shares the SAME
pattern length L (#354, QA Position C).

## The problem (see #354 body)

The prior enrichment picked each analogue's best-PPS window independently,
producing different lengths across the 5 rows of a single panel (Lebanon
civil_war: Rwanda 28yr, Syria 24yr, Pakistan 31yr, Myanmar 34yr, South
Sudan 61yr). The QGI pattern definition requires both windows of a pair
to share a length, so labeling all rows "Lebanon's current trajectory"
was mathematically false.

## The fix (Position C)

For each (subject, category):
  1. Read the top-5 analogues' best_pattern_length values.
  2. Pick L that MAXIMIZES coverage across those analogues within a
     tolerance of ±2 years (not the blind median — some analogues'
     best-lengths cluster in ranges where the median lies outside).
     Tie-break by sum of PPS across analogues.
  3. For each analogue, choose the highest-PPS pattern of length in
     [L-2, L+2] from pair-windows/{subject_id}.json[analogue_id].top.
     Prefer windows where `start_b <= event_year_b <= start_b + length`
     (event inside window).
  4. If an analogue has no pattern in [L-2, L+2], drop it from the panel.
     Downstream UI will show the surviving row count.
  5. Record `pair_length`, `pair_start_a`, `pair_start_b`,
     `event_in_window` per analogue. Add `canonical_length` to the
     (subject, category) block.

## Trade-offs (accepted per QA review)

- Median L can miss — using coverage-max instead (variance from QA's
  recipe, but closer to ground truth).
- Some analogues get dropped. Better than lying about Lebanon's window.
- Subject's start_year_a shifts slightly per row (each pair peaks at a
  slightly different subject-window position). Length is the invariant.

## Input / output

Input:
  qgi-frontend/data/pair-windows/{subject_id}.json   — per-pair window sets
  qgi-frontend/data/analogues-enriched.json          — existing enrichment (read subject metadata + event years)

Output (in-place rewrite):
  qgi-frontend/data/analogues-enriched.json
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

# Analogue pattern windows must end in the PAST or TODAY — an analogue
# bar extending into 2027 while the subject's NOW marker is 2026 is
# visually incoherent ("the historical event happens in the future").
# QA pre-mortem review flagged 34 such rows in the 2026-04-19 data.
CURRENT_YEAR = datetime.now().year


# Per-pair compact schema from generate_pair_windows.py:
#   l  = length
#   sa = start_year_a
#   sb = start_year_b
#   ic = indicator_count
#   ac = avg_correlation
#   pps = pattern_power_score


def best_common_length(
    pair_windows_by_analogue: dict[str, list[dict]],
    analogues: list[dict],
    length_tolerance: int = 2,
    end_tolerance: int = 2,
) -> int | None:
    """Pick L that maximizes coverage of EVENT-END-ALIGNED windows across
    the given analogues.

    #354 follow-up (2026-04-19): the original scorer counted any L±tol
    window as coverage. But post-fix we only keep windows whose right
    edge lines up with ``event_year_b`` (pattern → event invariant), so
    the L selector should be aware of that filter — otherwise we'd pick
    an L that looks well-covered but drops half the analogues at the
    alignment stage.

    For each candidate L, count how many analogues have at least one
    window satisfying BOTH:
      * ``|w.l - L| <= length_tolerance``
      * ``|(w.sb + w.l) - event_year_b| <= end_tolerance`` (when event year available)

    Pick L with max coverage. Tie-break by sum of best-PPS of the
    aligned windows. Returns None if no candidate L covers any analogue.

    ``analogues`` is a list of analogue dicts (need ``country_b_id`` and
    ``event_year_b``) rather than just IDs so we can honour the per-pair
    event anchor.
    """
    candidate_lengths: set[int] = set()
    for a in analogues:
        aid = a.get("country_b_id")
        if aid is None:
            continue
        for w in pair_windows_by_analogue.get(str(aid), {}).get("top", []):
            if isinstance(w.get("l"), int):
                candidate_lengths.add(w["l"])

    if not candidate_lengths:
        return None

    def score_length(L: int) -> tuple[int, int, float]:
        """Return (aligned_coverage, any_coverage, sum_best_pps).

        Sorts by aligned_coverage first (Tier 1/2 windows), then
        any_coverage (Tier 3 / pre-coverage-event fallback), then PPS.
        This keeps the preference for end-aligned windows without
        penalising (subject, category) blocks where every event pre-dates
        data coverage (e.g., Russia/China political_repression 1987).
        """
        aligned_cov = 0
        any_cov = 0
        total_pps = 0.0
        for a in analogues:
            aid = a.get("country_b_id")
            eyb = a.get("event_year_b")
            if aid is None:
                continue
            windows = pair_windows_by_analogue.get(str(aid), {}).get("top", [])
            best_aligned = None
            best_any = None
            for w in windows:
                if not isinstance(w.get("l"), int) or w.get("sb") is None:
                    continue
                if abs(w["l"] - L) > length_tolerance:
                    continue
                # Future-date guard (same as pick_analogue_window).
                if w["sb"] + w["l"] > CURRENT_YEAR:
                    continue
                pps = w.get("pps") or 0
                # Track best window at this L regardless of event alignment.
                if best_any is None or pps > (best_any.get("pps") or 0):
                    best_any = w
                # When we know the event year, also track end-aligned best.
                if eyb is not None:
                    if abs((w["sb"] + w["l"]) - eyb) <= end_tolerance:
                        if best_aligned is None or pps > (best_aligned.get("pps") or 0):
                            best_aligned = w
            if best_aligned is not None:
                aligned_cov += 1
                total_pps += best_aligned.get("pps") or 0
            elif best_any is not None:
                any_cov += 1
                total_pps += best_any.get("pps") or 0
        return (aligned_cov, any_cov, total_pps)

    best_L = max(candidate_lengths, key=score_length)
    # If the chosen L covers zero analogues at any tier (pathological case —
    # no pair has ANY window at this length, aligned or not), bail.
    sc = score_length(best_L)
    if sc[0] + sc[1] == 0:
        return None
    return best_L


def pick_analogue_window(
    windows: list[dict],
    target_L: int,
    event_year_b: int | None,
    length_tolerance: int = 2,
    end_tolerance: int = 2,
) -> dict | None:
    """Select the best-PPS window within [L-tolerance, L+tolerance] whose
    RIGHT edge aligns with ``event_year_b`` (pattern precedes event).

    #354 follow-up (2026-04-19): the first cut of this function preferred
    windows "containing the event" — allowing the event year to fall
    anywhere inside the window. That produced a visible misalignment on
    AnalogueMultiTimeline: the event star ★ could appear mid-bar or near
    the start, breaking the "pattern → event" narrative the panel claims
    to tell.

    Correct invariant: ``sb + l == event_year_b`` (pattern ends exactly
    at the event year). We relax this with a small ``end_tolerance`` to
    avoid dropping analogues whose best-length windows don't line up to
    the exact year because the pair-windows generator only sampled
    specific window positions. Preference order:

      1. Exact: ``sb + l == event_year_b``
      2. Near:  ``|sb + l - event_year_b| <= end_tolerance`` (default 2 yr)
      3. Best-PPS fallback: used when event_year_b pre-dates data coverage.
         ``event_in_window`` will be False; AnalogueMultiTimeline shows ⚠.
         Previously Tier 3 was "drop" — that discarded real pair-window data
         and forced the 15yr event-anchored approximation instead.

    Among windows tied on end-alignment, pick highest PPS.
    """
    if event_year_b is None:
        # No event year = no way to align. Analogues without event years
        # are already filtered upstream in AnalogueMultiTimeline, but be
        # defensive here.
        return None

    eligible = [
        w for w in windows
        if isinstance(w.get("l"), int)
        and w.get("sb") is not None
        and abs(w["l"] - target_L) <= length_tolerance
        # Drop future-dated windows. An analogue pattern extending past
        # the current year has no meaningful precedent semantics — the
        # "historical event" cannot be in the future relative to the
        # subject's NOW. See review note above.
        and w["sb"] + w["l"] <= CURRENT_YEAR
    ]
    if not eligible:
        return None

    def end_year(w: dict) -> int:
        return w["sb"] + w["l"]

    # Tier 1: exact end-alignment.
    exact = [w for w in eligible if end_year(w) == event_year_b]
    if exact:
        return max(exact, key=lambda w: w.get("pps") or 0)

    # Tier 2: near end-alignment (within ±end_tolerance years).
    near = [w for w in eligible if abs(end_year(w) - event_year_b) <= end_tolerance]
    if near:
        # Prefer ending at or BEFORE the event (precedent framing: pattern
        # → event implies pattern finishes first) over ending after it.
        # Sort key (lower is better):
        #   1) 0 if end <= event else 1 (before beats after)
        #   2) distance from event (ascending)
        #   3) -PPS (descending)
        near.sort(
            key=lambda w: (
                0 if end_year(w) <= event_year_b else 1,
                abs(end_year(w) - event_year_b),
                -(w.get("pps") or 0),
            )
        )
        return near[0]

    # Tier 3: best-PPS fallback for pre-coverage events.
    #
    # When event_year_b pre-dates the data coverage window (e.g., Russia
    # political_repression 1987, China 1987) there is NO window in pair-windows
    # whose end can align to 1987 — the earliest data starts ~1980 and a
    # 30-year window ends at 2010 at the earliest. Dropping these analogues
    # entirely forces the frontend into the 15yr event-anchored approximation
    # (which is also not end-aligned) and discards the real correlation signal
    # we have from pair-windows.
    #
    # Better: use the best-PPS eligible window. The bar will NOT end at the
    # event year, so `event_in_window` will be False, and AnalogueMultiTimeline
    # already renders a ⚠ indicator for those rows. The user sees the real
    # pair data, not a 15yr approximation, while the transparency flag stays.
    #
    # Only apply this when there are eligible windows (i.e. the pair has
    # real data at this length) — if eligible is empty we already returned
    # None above.
    return max(eligible, key=lambda w: w.get("pps") or 0)


def enrich(
    pair_windows_dir: Path,
    enriched_path: Path,
    length_tolerance: int = 2,
) -> int:
    with open(enriched_path, encoding="utf-8") as f:
        payload = json.load(f)

    countries = payload.get("countries", {})
    stats = {
        "subjects_processed": 0,
        "categories_processed": 0,
        "analogues_kept": 0,
        "analogues_dropped": 0,
        "events_in_window": 0,
        "events_outside_window": 0,
        # #471 V2.0 stats
        "events_overridden_by_max_pps": 0,
        "analogues_with_pair_instances": 0,
    }

    for subject_id, categories in countries.items():
        pw_path = pair_windows_dir / f"{subject_id}.json"
        if not pw_path.exists():
            # No pair-window data for this subject — leave categories as-is.
            continue
        with open(pw_path, encoding="utf-8") as f:
            pair_windows = json.load(f)

        stats["subjects_processed"] += 1

        for category, block in categories.items():
            analogues = block.get("analogues", [])
            if not analogues:
                continue
            stats["categories_processed"] += 1

            # #354v2 hygiene: WIPE any pair_* + canonical_length fields
            # from a previous enrichment pass. Without this, the v1 script
            # (which wrote non-end-aligned pair_* values) poisoned the
            # input file — every subsequent v2 run that legitimately
            # decides "no aligned L exists here" (returns None from
            # best_common_length → continue) would silently leave v1's
            # misaligned values in place. Explicit reset keeps the output
            # a pure reflection of the v2 algorithm's decisions.
            block.pop("canonical_length", None)
            for a in analogues:
                for k in (
                    "pair_length",
                    "pair_start_a",
                    "pair_start_b",
                    "pair_pps",
                    "pair_avg_corr",
                    "event_in_window",
                ):
                    a.pop(k, None)

            # #471 V2.0 (2026-04-26): the common-length force-fit is
            # dropped per #465 Q5 — each analogue picks its own native
            # length window via the inner loop below. The previous
            # `best_common_length` + `block["canonical_length"] = L` flow
            # is gone; both `canonical_lengths` and the `categories_no_aligned_L`
            # stat are dead and removed.

            # #354v3 (2026-04-19): NEVER drop analogues. Keep every one
            # the upstream enricher produced; when no aligned window
            # exists, leave pair_* fields null and let the frontend fall
            # back to the event-anchored 15yr approximation (which is
            # aligned by construction, just not "real" pair data).
            #
            # The earlier v2 ran .append only on keeper paths and wrote
            # the shortened list back — dropping 11,167 analogue rows
            # across 3,982 (subject, category) blocks system-wide.
            # Symptom: precedent-detail pages showed 5 analogue CARDS
            # (read from legacy analogues.json) but the TIMELINE showed
            # only 3 because the timeline read the destructively-reduced
            # enriched file. Fix: keep everything, never drop.
            rebuilt: list[dict] = []
            for a in analogues:
                a_new = dict(a)
                aid = a.get("country_b_id")
                # Strip any stale pair_* before re-deciding.
                for k in (
                    "pair_length",
                    "pair_start_a",
                    "pair_start_b",
                    "pair_pps",
                    "pair_avg_corr",
                    "event_in_window",
                ):
                    a_new.pop(k, None)

                if aid is None:
                    rebuilt.append(a_new)
                    stats["analogues_kept"] += 1
                    continue

                windows = pair_windows.get(str(aid), {}).get("top", [])

                # #471 V2.0 (Q4 max-PPS event picker + drop force-fit +
                # populate pair_instances). Replaces the previous
                # `pick_analogue_window` + common-length flow with
                # per-analogue independent length + max-PPS event choice.
                # #559 fix (2026-05-11): the legacy `chosen =
                # pick_analogue_window(windows, L, ...)` call that sat
                # here was removed — `L` was no longer defined after
                # the V1 `best_common_length()` call was dropped from
                # the enrich() flow, so the line raised
                # `UnboundLocalError` whenever exercised. The result
                # was also never read; the V2.0 per-year loop below
                # recomputes every alignment decision from scratch.
                #
                # Algorithm:
                #   1. Build the candidate event-year set from event_all_years_b
                #      (or fall back to event_year_b if the all-years field is
                #      absent on legacy data).
                #   2. For each candidate year, find pair-windows whose
                #      end (sb + l) is within ±2 of that year (terminus
                #      semantics per #457 item 8) AND ends in the past
                #      or today (no future-pattern bars).
                #   3. Pick the candidate year whose best aligned window
                #      has the highest PPS — this is Q4: "select the
                #      event that maximizes the recipe's PPS for that
                #      pair." For single-event analogues this is a no-op
                #      (one candidate, one pick).
                #   4. Sort that year's aligned windows by PPS desc; the
                #      top one becomes the canonical pair_* set
                #      (back-compat); the full top-N (cap 5) becomes
                #      pair_instances (Q2 progressive disclosure).
                #   5. Override event_year_b on the analogue to the chosen
                #      year (when it differs from the upstream median pick).
                #   6. Length is no longer force-fit to a common L —
                #      each analogue keeps its native pair length per Q5.
                if not windows:
                    # No pair-window data for this analogue. Frontend falls
                    # back to 15yr event-anchor on its own.
                    stats["analogues_without_aligned_window"] = (
                        stats.get("analogues_without_aligned_window", 0) + 1
                    )
                    rebuilt.append(a_new)
                    stats["analogues_kept"] += 1
                    continue

                candidate_event_years = a.get("event_all_years_b") or [
                    a.get("event_year_b")
                ]
                candidate_event_years = [
                    y for y in candidate_event_years if y is not None
                ]
                if not candidate_event_years:
                    rebuilt.append(a_new)
                    stats["analogues_kept"] += 1
                    continue

                # #561 fix (2026-05-11): the ±2 terminus-alignment
                # tolerance was hardcoded here; wire to length_tolerance
                # (also surfaced via --tolerance CLI flag, default 2)
                # so a single knob controls both length-band and
                # terminus-band tolerance consistently. The previous
                # hardcoded literal made the methodology assumption
                # invisible to callers.
                def _aligned_for(year, _windows=windows, _tol=length_tolerance):
                    return [
                        w for w in _windows
                        if w.get("sb") is not None
                        and w.get("l") is not None
                        and abs((w["sb"] + w["l"]) - year) <= _tol
                        and (w["sb"] + w["l"]) <= CURRENT_YEAR
                    ]

                best_year = None
                best_year_top_pps = float("-inf")
                best_year_aligned: list[dict] = []
                for y in candidate_event_years:
                    aligned = _aligned_for(y)
                    if not aligned:
                        continue
                    top_pps = max(w.get("pps", 0.0) for w in aligned)
                    if top_pps > best_year_top_pps:
                        best_year_top_pps = top_pps
                        best_year = y
                        best_year_aligned = sorted(
                            aligned, key=lambda w: -w.get("pps", 0.0)
                        )

                if best_year is None or not best_year_aligned:
                    # No event-aligned windows for ANY candidate year.
                    # Null pair_* + leave event_year_b as-is.
                    stats["analogues_without_aligned_window"] = (
                        stats.get("analogues_without_aligned_window", 0) + 1
                    )
                    rebuilt.append(a_new)
                    stats["analogues_kept"] += 1
                    continue

                # Q4: override event_year_b to the max-PPS chosen year.
                if best_year != a.get("event_year_b"):
                    stats["events_overridden_by_max_pps"] = (
                        stats.get("events_overridden_by_max_pps", 0) + 1
                    )
                a_new["event_year_b"] = best_year

                # Canonical (back-compat) pair_* fields = the top-PPS instance.
                canonical = best_year_aligned[0]
                a_new["pair_length"] = canonical.get("l")
                a_new["pair_start_a"] = canonical.get("sa")
                a_new["pair_start_b"] = canonical.get("sb")
                a_new["pair_pps"] = canonical.get("pps")
                a_new["pair_avg_corr"] = canonical.get("ac")
                # event_in_window True by construction — we filtered for
                # ±2 terminus alignment above.
                a_new["event_in_window"] = True
                a_new["contains_predicted"] = bool(canonical.get("cp", False))
                stats["events_in_window"] += 1

                # #465 Q2: full top-N instances (cap 5) for progressive
                # disclosure. First entry mirrors pair_*; the rest power
                # the chevron-expand UI in AnalogueMultiTimeline.
                a_new["pair_instances"] = best_year_aligned[:5]
                if len(best_year_aligned) > 1:
                    stats["analogues_with_pair_instances"] += 1

                rebuilt.append(a_new)
                stats["analogues_kept"] += 1
            block["analogues"] = rebuilt

    # Note the algorithm version so downstream consumers can detect + fail
    # loudly if they read an old-shape file.
    payload["enrichment_algorithm"] = (
        "v2.0-per-analogue-max-pps-no-force-fit (#471, 2026-04-26)"
    )
    payload["enrichment_length_tolerance"] = length_tolerance

    with open(enriched_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("\n== Enrichment stats ==")
    for k, v in stats.items():
        print(f"  {k:<30} {v}")
    # #559 fix (2026-05-11): the canonical-length distribution block that
    # used to print here iterated `canonical_lengths.values()` — a dict
    # the V1 code populated alongside `block["canonical_length"] = L`.
    # Both the dict and the per-block canonical_length write were removed
    # in the V2.0 refactor (per Q5: no force-fit), so the loop iterated
    # an undefined name. Block deleted; per-analogue pair_length is
    # already visible in the enrichment payload and in pair_instances.

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pair-windows-dir",
        type=Path,
        default=Path("qgi-frontend/data/pair-windows"),
    )
    parser.add_argument(
        "--enriched",
        type=Path,
        default=Path("qgi-frontend/data/analogues-enriched.json"),
    )
    parser.add_argument("--tolerance", type=int, default=2)
    args = parser.parse_args()
    return enrich(args.pair_windows_dir, args.enriched, args.tolerance)


if __name__ == "__main__":
    raise SystemExit(main())
