"""scdi_core.py — pure ranking/selection/transform logic for the cascade SCDI bake (§H).

I/O-free + dependency-light so the founder's ranking directive is exhaustively testable.
The runnable baker (bake_pattern_scdis.py) wraps the S3 `pair-windows` reads, the
`pattern_indicator_lookup` query (the ~50 MB projection — NEVER the 1.98B `patterns`
table), and the per-indicator parquet reads around these pure functions.

Terminology: cascade country relationships are **patterns**, never "pairs" (founder rule).

Founder directive (2026-05-31, feedback_cascade_batch_ranking):
  - Do NOT rank by PPS (= corr * length * #indicators) — it is length-biased.
  - Balance correlation / length / #indicators ~equally, with a slight tilt to
    #indicators at the expense of length.
  - Size the batch by GREEDY FILL up to the Vercel limit, not a fixed N.
"""

from __future__ import annotations

import math
from collections.abc import Callable

# Balanced-score weights. Sum to 1.0; #indicators (0.36) sits slightly above
# correlation (0.34), and length (0.30) is the one shaved — the deliberate tilt.
W_CORR, W_NIND, W_LEN = 0.34, 0.36, 0.30


def _minmax(values: list[float]) -> tuple[float, float]:
    """(lo, span) for min-max normalisation; span never 0 (flat field -> all 0.5)."""
    lo, hi = min(values), max(values)
    span = hi - lo
    return lo, (span if span > 0 else 1.0)


def balanced_scores(windows: list[dict]) -> list[float]:
    """Per-window balanced score. `windows`: dicts with 'corr', 'length', 'n_ind'.
    Each field is min-max normalised across the corpus, then weighted W_CORR/W_NIND/
    W_LEN. Returns a list aligned to `windows`. This REPLACES PPS (which is the
    length-biased multiplicative product corr*length*n_ind)."""
    if not windows:
        return []
    c_lo, c_sp = _minmax([w["corr"] for w in windows])
    l_lo, l_sp = _minmax([w["length"] for w in windows])
    n_lo, n_sp = _minmax([w["n_ind"] for w in windows])
    out: list[float] = []
    for w in windows:
        nc = (w["corr"] - c_lo) / c_sp
        nl = (w["length"] - l_lo) / l_sp
        nn = (w["n_ind"] - n_lo) / n_sp
        out.append(round(W_CORR * nc + W_NIND * nn + W_LEN * nl, 6))
    return out


def rank_and_fill(
    windows: list[dict], size_cap_bytes: int, per_pattern_bytes: Callable[[dict], int]
) -> tuple[list[dict], int]:
    """Greedy fill (founder: NOT a fixed N). Rank windows by balanced score desc, then
    add best-first while the accumulated estimated baked size stays under
    `size_cap_bytes`. `per_pattern_bytes(window)` estimates a pattern's JSON footprint.
    A pattern that would overflow is skipped (a smaller lower-ranked one may still fit).
    Returns (selected windows in rank order, running total bytes)."""
    scores = balanced_scores(windows)
    order = sorted(range(len(windows)), key=lambda i: -scores[i])
    selected: list[dict] = []
    total = 0
    for i in order:
        cost = per_pattern_bytes(windows[i])
        if total + cost > size_cap_bytes:
            continue
        selected.append(windows[i])
        total += cost
    return selected, total


def build_slug(a_iso2: str, b_iso2: str, start_a: int, start_b: int, length: int) -> str:
    """The pattern-detail slug. 4-segment ALIGNED `{a}-{b}-{startA}-{endA}` when both
    countries start the same year; 5-segment OFFSET `{a}-{b}-{startA}-{startB}-{len}`
    otherwise. iso2 codes lowercased (matches the frontend scdi-mock slug convention)."""
    a, b = a_iso2.lower(), b_iso2.lower()
    if start_a == start_b:
        return f"{a}-{b}-{start_a}-{start_a + length - 1}"
    return f"{a}-{b}-{start_a}-{start_b}-{length}"


def zscore_downsample(values: list[float], n_epochs: int = 12) -> list[float]:
    """Z-score a country's indicator series over the window (per-country mean/std),
    then downsample to `n_epochs` evenly-spaced points (linear interpolation; endpoints
    preserved). Returns floats rounded to 4dp. Empty in -> empty out;
    n_epochs<=1 -> the first lead-point's z-score (single-epoch summary)."""
    n = len(values)
    if n == 0:
        return []
    mu = sum(values) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in values) / n) or 1.0
    z = [(v - mu) / sd for v in values]
    if n == n_epochs:
        return [round(x, 4) for x in z]
    if n_epochs <= 1:
        return [round(z[0], 4)]
    out: list[float] = []
    for k in range(n_epochs):
        pos = k * (n - 1) / (n_epochs - 1)
        lo = int(pos)
        frac = pos - lo
        if lo + 1 < n:
            out.append(round(z[lo] + frac * (z[lo + 1] - z[lo]), 4))
        else:
            out.append(round(z[lo], 4))
    return out


def pearson_r(a: list[float], b: list[float]) -> float | None:
    """Pearson correlation between two equal-length series. None when undefined
    (n<2, length mismatch, or a constant series)."""
    n = len(a)
    if n < 2 or len(b) != n:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = math.sqrt(sum((x - ma) ** 2 for x in a))
    vb = math.sqrt(sum((x - mb) ** 2 for x in b))
    if va == 0 or vb == 0:
        return None
    return round(cov / (va * vb), 4)


def direction(r: float | None) -> str | None:
    """Co-movement label from a correlation: 'same' if r>=0, 'opposite' if r<0."""
    if r is None:
        return None
    return "same" if r >= 0 else "opposite"
