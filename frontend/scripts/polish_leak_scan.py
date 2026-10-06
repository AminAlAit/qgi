#!/usr/bin/env python3
"""
Phase A1 Polishing — Mechanical leak scanner for qgi-frontend.

Detects technical/engineering vocabulary that leaked into user-facing prose
across all routes in app/(app)/ and components/. Outputs two artifacts:

  scripts/output/polish-scan.csv  — machine-readable findings (one row / leak)
  scripts/output/polish-scan.md   — human-readable summary grouped by route

This is the FIRST pass of Phase A1 cleanup per founder direction 2026-05-12.
Catches the mechanical leaks (slug strings, indicator IDs, methodology jargon
without gloss, MOCK markers, em-dash density). The SEMANTIC pass (disclosure
copy that reads like internal notes, layout decisions that leak engineering
context, undefined acronyms inside flowing prose) is a separate persona-driven
walkthrough — out of scope for this scanner.

Heuristic, not perfect. Uses regex against extracted JSX text fragments. Some
findings will be false positives (e.g. a code identifier that happens to
appear in a comment) — review the output as a first-pass triage list, not a
ship-blocking gate.

Usage:
    cd qgi-frontend
    python scripts/polish_leak_scan.py
    # outputs land in scripts/output/

Re-runnable: existing output files are overwritten each run.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "scripts" / "output"

# Directories to scan
SCAN_ROOTS = [
    REPO_ROOT / "app",
    REPO_ROOT / "components",
]

# Skip patterns
SKIP_PATH_FRAGMENTS = (
    "/node_modules/",
    "/.next/",
    "/dist/",
    "/__tests__/",
)
SKIP_SUFFIXES = (".test.tsx", ".test.ts", ".spec.tsx", ".spec.ts")

# Methodology / disclosure paths — these are "show our work" venues where
# technical vocabulary IS the content. Scanning them produces noise; the
# legitimate fixes are in product surfaces (V1/V2 detail pages, dashboards,
# filter chrome, etc.). Treat these as out-of-scope.
METHODOLOGY_PATH_FRAGMENTS = (
    "/app/blog/",
    "/app/methodology/",
    "/app/(app)/examples/",
    # Next.js API route handlers — server-side JSON, never JSX. SQL strings
    # inside template literals create false-positive `>`/`<` matches when the
    # DOTALL JSX-text regex sees SQL operators as tag boundaries.
    "/app/api/",
)


# ============================================================================
# Leak detectors
# ============================================================================

@dataclass(frozen=True)
class Leak:
    file: str  # repo-relative path
    line: int
    leak_type: str
    snippet: str  # the offending text fragment
    suggestion: str  # one-liner fix hint


# --- Methodology jargon dictionary (acronyms / terms that need user-facing glossing)
# Tuples of (term-regex, suggestion). Matched as whole words (boundary).
JARGON_TERMS: list[tuple[str, str]] = [
    (r"\bLOCO\b", "Leave-one-country-out (out-of-country) — gloss inline on first use"),
    (r"\bAUC\b", "Discrimination score — explain in plain English or use 'discrimination'"),
    (r"\bECE\b", "Calibration error — explain inline or relabel 'calibration gap'"),
    (r"\bRCI\b", "Recipe Confidence Index — gloss inline on first use"),
    (r"\bAHI\b", "Anchor Health Index — gloss inline; or use 'anchor stability'"),
    (r"\bPPS\b", "Pattern Power Score — gloss inline on first use"),
    (r"\bRRF\b", "Reciprocal Rank Fusion — gloss inline on first use"),
    (r"\bn_pos[_a-zA-Z]*\b", "Internal metric (positive-class count). Hide or relabel."),
    (r"\bn_pos_LOCO\b", "Internal metric. Replace with 'held-out positives' or hide."),
    (r"\bLOCKed\b", "Internal status word. Relabel 'validated' or hide."),
    (r"\bLEAK\b", "Internal QA term. Hide from buyer-facing prose."),
    (r"\bMNAR\b", "Missing-not-at-random — gloss inline or use 'missingness pattern'"),
    (r"\bF-H-\d+\b", "Internal F-H-N rule reference. Hide or convert to user-facing phrasing."),
    (r"\bADVISORY-ONLY\b", "Internal pricing-gate term. Buyer-facing version: 'composite-signal only'"),
    (r"\bKI-\d+\b", "Internal Known-Issue ref. Hide entirely."),
    (r"\bDEFERRED\b", "Internal status. Replace with 'planned' or hide."),
    (r"\bSCDI\b", "Statistical Cross-Discovery Index — gloss inline on first use"),
    (r"\bdispatch_sha\b", "Internal dev-pipeline value. Hide entirely."),
    (r"\bcohort_ece\b", "Internal field. Relabel 'calibration by tier' or similar."),
    (r"\bf_rule_anomaly\b", "Internal flag. Hide or relabel 'in-sample F-test anomaly'."),
    (r"\bn_pos_test\b", "Internal metric. Hide or relabel 'test-window positives'."),
    (r"\bDeepHit\b", "Internal model name. Buyer-facing: 'survival model'."),
    (r"\bisotonic\b", "Internal calibration method. Either explain or hide."),
    (r"\bbootstrap CI\b", "Acceptable but worth glossing: 'uncertainty range from resampling'"),
    (r"\bD[25]\b(?=\s+(?:architecture|head))", "Internal architecture label. Relabel or hide."),
    (r"\bhybrid D2/D5\b", "Internal architecture name. Buyer-facing: 'hybrid prediction architecture'"),
    (r"\bpre-reg\b", "Internal preregistration term. Hide or relabel 'methodology lock'"),
    (r"\bLakatosian\b", "Internal methodology vocabulary. Hide from buyer prose."),
    (r"\bauditioner\b", "Internal QGI term. Hide."),
    (r"\b(?:Asas|Sard|Ihsa|Bina|Tasweeq|Tijara)\b", "Internal Majles persona group name. Hide entirely."),
    (r"\bMajles\b", "Internal advisory-council term. Hide from buyer prose."),
]
# Pre-compile JARGON regexes at module load (hot-loop perf fix per QA review).
JARGON_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p), s) for p, s in JARGON_TERMS
]


# --- Indicator-ID patterns (raw indicator codes that leaked to display)
INDICATOR_PATTERNS: list[tuple[str, str]] = [
    # V-Dem variables: v2x_polyarchy, v2cseeorgs, etc.
    (r"\bv2[a-z]+_[a-z][a-z0-9_]+\b", "V-Dem variable code — replace with indicator name (e.g. v2x_polyarchy → 'Electoral democracy index')"),
    (r"\bv2[a-z]{3,}\b", "Likely V-Dem code — verify + replace with display name"),
    # World Bank indicators: NY.GDP.MKTP.KD, SP.POP.TOTL, etc.
    (r"\b[A-Z]{2,3}\.[A-Z]{2,4}\.[A-Z0-9.]{2,}\b", "World Bank indicator code — replace with display name + unit"),
    # Custom diff/lag suffixes (e.g. VC.BTL.DETH__diff)
    (r"\b[A-Z0-9.]+__(diff|lag|zscore|change|delta|momentum)\b", "Engineered-feature code — replace with plain-English label"),
    # Sometimes shows up as standalone token
    (r"\b__diff\b|\b__lag\b", "Feature-transform suffix leaked. Convert to plain English."),
]
# Pre-compile INDICATOR regexes at module load (hot-loop perf fix per QA review).
INDICATOR_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p), s) for p, s in INDICATOR_PATTERNS
]


# --- Slug detection: snake_case identifier appearing as display text
# Strategy: a multi-token underscore-joined word inside a quoted string or
# JSX text content, where the word has 2+ underscores OR ends in known
# recipe slugs. Avoids matching variable names by requiring the token to
# appear inside text content (not as identifier).
SLUG_LIKE = re.compile(
    # Negative lookbehind `(?<!\.)`: exclude matches preceded by `.` because
    # `obj.field_name` is a JS field access, not display text. Real-world
    # false positive: `existing.pattern_power_score)` inside a ternary
    # captured between `}` and `{` JSX boundaries.
    r"(?<!\.)\b([a-z][a-z0-9]+(?:_[a-z][a-z0-9]+){2,})\b"
)
# Known recipe slugs — flagged with high confidence
KNOWN_RECIPE_SLUGS = {
    "civil_war_and_insurgency",
    "multilateral_agreement",
    "elections_and_voting",
    "bilateral_treaty",
    "terrorist_attack",
    "energy_policy",
    "epidemic_and_pandemic",
    "human_rights_violation",
    "foreign_intervention",
    "humanitarian_crisis",
    "peacekeeping_and_peace_process",
    "government_formation",
    "mass_protest",
    "territorial_disputes",
    "constitutional_change",
    "economic_recession",
    "executive_power_consolidation",
    "migration_and_refugees",
    "natural_disaster",
    "political_corruption",
    "political_repression",
    "sanctions_and_arms_embargo",
    "trade_agreement",
}


# --- AI-tell markers
MOCK_MARKERS = re.compile(r"\b(MOCK|TODO|FIXME|XXX|HACK|DEFERRED_TO_)\b")
EM_DASH = "—"  # U+2014
EM_DASH_THRESHOLD = 8  # per file; above this, flag as AI-tell density


# ============================================================================
# JSX text extraction (heuristic)
# ============================================================================

# Capture text between JSX boundaries. Boundary characters: < > { }
# (tag boundaries + JSX-expression boundaries). Text "fragments" are any
# stretch of non-boundary chars sandwiched between an opening boundary
# (`>` tag close or `}` expression close) and a closing boundary (`<` tag
# open or `{` expression open).
#
# DOTALL so capture spans newlines — multi-line JSX content like
#     <div ...>
#       LOCO AUC
#     </div>
# is otherwise invisible to per-line scanning (QA review #2 finding).
#
# `;` exclusion: statement terminator, only appears in JS/TS code (never in
# JSX text content). Without this, TS generics like `useState<string>` close
# bracket `>` matches against the next `useState<...>` open `<` with the
# intervening JS statement body as "captured text". Real-world example:
# CountryProfileClient.tsx l.94 captured TS statement body.
#
# Why both `[>}]` start and `[<{]` end: real JSX text often gets interrupted
# by inline JSX expressions like `for {country}`. With only `>...<`, the
# fragment AFTER the `{country}` (e.g. " against this recipe.") would be
# missed because the `}` of the expression is followed by text not `<`.
# Real-world example: SignalsV2Detail.tsx l.104 LOCO leak hidden behind
# `for {country} against`.
JSX_TEXT_RE = re.compile(r"[>}]([^<>{};]+?)[<{]", re.DOTALL)

# Capture attribute values that render as user-facing strings.
JSX_ATTR_RE = re.compile(
    r'\b(title|aria-label|placeholder|alt|aria-description|label)="([^"]+)"'
)

# Capture template-literal user text inside curly braces. Best-effort.
JSX_TEMPLATE_RE = re.compile(r"\{`([^`]+)`\}")

# ${...} JS interpolations inside template literals are evaluated as code,
# not rendered as literal text. The user sees the EVALUATED value, never
# the field-path syntax. Strip these from captured template fragments so
# `${recipe.coverage_bias_diagnostic.oecd_share}` doesn't get flagged as
# a snake_case-in-display leak. (Simple regex — no nested-brace support;
# none of the QGI codebase uses nested braces in template interpolations.)
JS_INTERP_RE = re.compile(r"\$\{[^}]*\}")

# Capture string-literal text inside curly braces: {"foo"} or {'foo'}
JSX_STRING_LITERAL_RE = re.compile(r"\{[\"']([^\"']+)[\"']\}")

# Lines inside `//` comments — skip these from leak detection
COMMENT_LINE_RE = re.compile(r"^\s*//")
JSDOC_BLOCK_START_RE = re.compile(r"^\s*/\*")
JSDOC_BLOCK_END_RE = re.compile(r"\*/\s*$")

# Inline-on-same-line block comment: /* ... */ within a single line.
INLINE_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/")

# JSX <code>...</code>, <pre>...</pre>, and <footer>...</footer> blocks —
# all intentional technical-disclosure venues:
#   <code>/<pre> show schema slugs, file paths, code identifiers verbatim
#     in blog posts and inline disclosure prose.
#   <footer> by QGI convention carries the methodology disclosure line
#     ("V1.8.1 z-score + RRF · Pearson r ≥ 0.65 · PPS quintiles..."). Terse
#     acronym-dense by design; analyst context implied by venue.
# All NEVER leaks. Strip before scanning for jargon/slugs.
CODE_PRE_INLINE_RE = re.compile(
    r"<(code|pre|footer)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)


def _strip_preserving_newlines(text: str, pattern: re.Pattern[str]) -> str:
    """Replace each pattern match with its newline count so file positions
    (and therefore line numbers via newline-count math) are preserved."""

    def replacer(m: re.Match[str]) -> str:
        return "\n" * m.group(0).count("\n")

    return pattern.sub(replacer, text)


# Multi-line aware skip-region patterns. Strip in this order:
#   1. JSDoc /* ... */ blocks across lines
#   2. <code>...</code> / <pre>...</pre> across lines
#   3. // line comments
# All three preserve newlines so subsequent line numbers stay correct.
JSDOC_MULTILINE_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT_RE = re.compile(r"(?m)^[ \t]*//[^\n]*$")

# Heuristic JS-code detection. The broadened JSX_TEXT_RE (which captures
# from `}` to `{` for fragments split by inline JSX expressions) also picks
# up JS code stretches between `} ... {` braces in things like ternaries,
# arrow function bodies, and object literals. None of those contain real
# user-facing prose. If the captured fragment contains any of these JS
# syntactic markers it is JS, not text. Real-world false-positive examples:
#   existing.pattern_power_score) (ternary RHS between } and {)
#   a.best_pattern_length !== undefined && b.best_pattern_length !== undef…
JS_CODE_MARKERS_RE = re.compile(r"===|!==|&&|\|\||=>|\?\.|!=\s|==\s")


def iter_text_fragments(file_path: Path) -> Iterator[tuple[int, str, str]]:
    """Yield (line_number, kind, text) for probable user-facing text fragments.

    kind ∈ {'jsx-text', 'jsx-attr', 'template', 'string-literal'}.

    Excludes:
      - `//` line comments
      - `/* */` block comments (multi-line aware)
      - JSX `<code>...</code>` and `<pre>...</pre>` content across lines
        (intentional technical disclosures — schema slugs, file paths,
        code identifiers deliberately shown verbatim in blog posts and
        inline `<code>` spans)

    JSX-text capture uses re.DOTALL so multi-line content like
        <div ...>
          LOCO AUC
        </div>
    is caught (per QA review #2 finding — per-line scan missed this).
    Line numbers are computed from match position, pointing at the line
    where the captured TEXT begins (not where the `>` is).

    Heuristic, not perfect. See top-of-file docstring for caveats.
    """
    try:
        raw = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return

    # Strip skip-regions (multi-line aware), preserving newlines for line math.
    text = _strip_preserving_newlines(raw, JSDOC_MULTILINE_RE)
    text = _strip_preserving_newlines(text, CODE_PRE_INLINE_RE)
    text = LINE_COMMENT_RE.sub("", text)  # ^...$ via (?m) — newlines preserved

    # --- JSX text (multi-line aware): > THIS TEXT < (also } TEXT { boundaries)
    for m in JSX_TEXT_RE.finditer(text):
        captured = m.group(1)
        frag = captured.strip()
        if not frag or frag.startswith("//"):
            continue
        # Heuristic: drop captures that look like JS code (ternary RHS,
        # arrow function body, object-literal value). They contain syntactic
        # markers that never appear in real user-facing prose.
        if JS_CODE_MARKERS_RE.search(frag):
            continue
        # Line number = where the first non-whitespace character of the
        # captured content starts (not the `>` itself, which may be on the
        # previous line for multi-line content).
        content_start = m.start(1)
        leading_ws_len = len(captured) - len(captured.lstrip())
        text_start = content_start + leading_ws_len
        line_no = text[:text_start].count("\n") + 1
        yield line_no, "jsx-text", frag

    # --- Per-line patterns: attribute values, template literals, string literals.
    # These are JSX-syntactically line-local; multi-line DOTALL would over-match.
    for line_no, line in enumerate(text.splitlines(), 1):
        for m in JSX_ATTR_RE.finditer(line):
            attr, val = m.group(1), m.group(2)
            yield line_no, f"jsx-attr:{attr}", val
        for m in JSX_TEMPLATE_RE.finditer(line):
            # Strip ${...} JS interpolations — only literal text is rendered.
            literal = JS_INTERP_RE.sub("", m.group(1)).strip()
            if literal:
                yield line_no, "template", literal
        for m in JSX_STRING_LITERAL_RE.finditer(line):
            yield line_no, "string-literal", m.group(1)


# ============================================================================
# Leak detection per fragment
# ============================================================================

def detect_leaks_in_fragment(file_rel: str, line_no: int, frag: str) -> Iterator[Leak]:
    """Run all leak detectors against a single text fragment."""

    # --- Known recipe slugs (high-confidence)
    for slug in KNOWN_RECIPE_SLUGS:
        if slug in frag:
            yield Leak(
                file=file_rel,
                line=line_no,
                leak_type="recipe-slug-in-display",
                snippet=_excerpt(frag, slug),
                suggestion=f"Replace '{slug}' with title-case display: '{slug.replace('_', ' ').capitalize()}'",
            )

    # --- Generic slug-like identifiers (lower confidence)
    for m in SLUG_LIKE.finditer(frag):
        token = m.group(1)
        if token in KNOWN_RECIPE_SLUGS:
            continue  # already caught
        # Skip very common technical words that are intentionally rendered
        if token in {"recipe_id", "country_id", "data_id"}:
            continue
        yield Leak(
            file=file_rel,
            line=line_no,
            leak_type="snake_case-identifier-in-display",
            snippet=_excerpt(frag, token),
            suggestion=f"'{token}' looks like an internal identifier — replace with display label",
        )

    # --- Indicator codes (pre-compiled patterns; perf fix per QA review)
    for pattern, suggestion in INDICATOR_COMPILED:
        for m in pattern.finditer(frag):
            yield Leak(
                file=file_rel,
                line=line_no,
                leak_type="indicator-id-in-display",
                snippet=_excerpt(frag, m.group(0)),
                suggestion=suggestion,
            )

    # --- Methodology jargon (pre-compiled patterns; perf fix per QA review)
    for pattern, suggestion in JARGON_COMPILED:
        for m in pattern.finditer(frag):
            yield Leak(
                file=file_rel,
                line=line_no,
                leak_type="methodology-jargon",
                snippet=_excerpt(frag, m.group(0)),
                suggestion=suggestion,
            )

    # --- MOCK / TODO markers leaking to display
    for m in MOCK_MARKERS.finditer(frag):
        yield Leak(
            file=file_rel,
            line=line_no,
            leak_type="dev-marker-leaked",
            snippet=_excerpt(frag, m.group(0)),
            suggestion=f"'{m.group(0)}' is a dev marker. Remove from user-facing prose before merge.",
        )


def detect_em_dash_density(file_path: Path, file_rel: str) -> Iterator[Leak]:
    """Flag files where em-dash count in USER-FACING text fragments exceeds the
    threshold. We deliberately exclude JSDoc/comment em-dashes since those are
    invisible to users — only display-rendered em-dashes count as AI-tells.
    """
    fragments = list(iter_text_fragments(file_path))
    if not fragments:
        return
    # Count em-dashes in user-facing fragments only
    total = sum(f[2].count(EM_DASH) for f in fragments)
    if total > EM_DASH_THRESHOLD:
        first_line = next((ln for ln, _k, frag in fragments if EM_DASH in frag), 1)
        yield Leak(
            file=file_rel,
            line=first_line,
            leak_type="em-dash-density-ai-tell",
            snippet=f"{total} em-dashes across user-facing text (threshold {EM_DASH_THRESHOLD})",
            suggestion="High em-dash count is an AI-tell. Replace some with periods or commas; vary sentence rhythm.",
        )


def _excerpt(text: str, focus: str, window: int = 40) -> str:
    """Return ≤ window-char excerpt centered on `focus`."""
    text = text.replace("\n", " ").strip()
    idx = text.find(focus)
    if idx < 0:
        return text[:window]
    start = max(0, idx - window // 2)
    end = min(len(text), idx + len(focus) + window // 2)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


# ============================================================================
# File walking
# ============================================================================

def should_skip(path: Path) -> bool:
    p = str(path).replace("\\", "/")
    if any(frag in p for frag in SKIP_PATH_FRAGMENTS):
        return True
    if any(p.endswith(suf) for suf in SKIP_SUFFIXES):
        return True
    # Methodology / blog / examples are intentional disclosure venues —
    # technical vocab there is content, not leak. Skip wholesale.
    if any(frag in p for frag in METHODOLOGY_PATH_FRAGMENTS):
        return True
    return False


def iter_scan_files() -> Iterator[Path]:
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for ext in ("*.tsx", "*.ts"):
            for path in root.rglob(ext):
                if not should_skip(path):
                    yield path


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_leaks: list[Leak] = []
    files_scanned = 0
    for file_path in iter_scan_files():
        files_scanned += 1
        file_rel = str(file_path.relative_to(REPO_ROOT)).replace("\\", "/")
        for line_no, _kind, frag in iter_text_fragments(file_path):
            all_leaks.extend(detect_leaks_in_fragment(file_rel, line_no, frag))
        all_leaks.extend(detect_em_dash_density(file_path, file_rel))

    # ----- CSV output --------------------------------------------------------
    csv_path = OUTPUT_DIR / "polish-scan.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "line", "leak_type", "snippet", "suggestion"])
        for leak in sorted(all_leaks, key=lambda x: (x.file, x.line, x.leak_type)):
            w.writerow([leak.file, leak.line, leak.leak_type, leak.snippet, leak.suggestion])

    # ----- Markdown summary --------------------------------------------------
    md_path = OUTPUT_DIR / "polish-scan.md"
    by_route: dict[str, list[Leak]] = defaultdict(list)
    by_type: dict[str, int] = defaultdict(int)
    for leak in all_leaks:
        # Group by top-level route or component family
        parts = leak.file.split("/")
        if parts[0] == "app":
            # app/(app)/<route>/...
            family = "app/(app)/" + (parts[2] if len(parts) > 2 else "")
        elif parts[0] == "components":
            family = "components/" + (parts[1] if len(parts) > 1 else "")
        else:
            family = parts[0]
        by_route[family].append(leak)
        by_type[leak.leak_type] += 1

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# Phase A1 Polishing — Mechanical Leak Scan\n\n")
        f.write(f"**Generated by** `scripts/polish_leak_scan.py`\n")
        f.write(f"**Files scanned**: {files_scanned}\n")
        f.write(f"**Total leaks**: {len(all_leaks)}\n")
        f.write(f"**Routes / component families affected**: {len(by_route)}\n\n")

        f.write("## Findings by type\n\n")
        f.write("| Leak type | Count |\n|---|---|\n")
        for leak_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
            f.write(f"| `{leak_type}` | {count} |\n")
        f.write("\n")

        f.write("## Findings by route / family\n\n")
        for family in sorted(by_route.keys()):
            leaks = by_route[family]
            f.write(f"### `{family}` ({len(leaks)} leaks)\n\n")
            # Group by leak_type inside the family
            sub: dict[str, list[Leak]] = defaultdict(list)
            for leak in leaks:
                sub[leak.leak_type].append(leak)
            for leak_type in sorted(sub.keys()):
                items = sub[leak_type]
                f.write(f"- **{leak_type}** ({len(items)})\n")
                for leak in items[:5]:  # cap to 5 examples per type per family
                    f.write(f"  - `{leak.file}:{leak.line}` — `{leak.snippet}` — *{leak.suggestion}*\n")
                if len(items) > 5:
                    f.write(f"  - ... and {len(items) - 5} more (see CSV)\n")
            f.write("\n")

    print(f"Scanned {files_scanned} files.")
    print(f"Found {len(all_leaks)} leaks across {len(by_route)} route/component families.")
    print(f"CSV:   {csv_path.relative_to(REPO_ROOT)}")
    print(f"MD:    {md_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
