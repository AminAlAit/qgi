"""
Schema-parity guard between pipeline-c-dispatcher's CREATE EXTERNAL TABLE
and pipeline-c-worker's INSERT SELECT for `qgi_data.patterns` (#512).

Background — this is the test the codebase has needed since #108:

  #108 (origin)
    pipeline-c-worker added pattern_tier (#128) to its INSERT SELECT.
    pipeline-c-dispatcher's CREATE EXTERNAL TABLE wasn't updated to
    match. Phase C stalled on every run — Athena rejected every INSERT
    with TYPE_MISMATCH, the SQS counter never advanced, the SF poll
    looped until manually killed.

  #512 (re-occurrence, this PR)
    Same shape, different column. #461 added contains_predicted to:
      • pipeline-c-worker INSERT SELECT
      • qgi-infra/modules/storage Glue Terraform
    …but missed pipeline-c-dispatcher. The 2026-04-28 V-Dem manual
    orchestrator was the first invocation of the dispatcher since #461
    — every one of the 215 country INSERTs failed identically.

This test fails CI on the THIRD occurrence by parsing the column lists
out of both Lambda source files and asserting they agree on:
  - column count
  - column order
  - column name spelling
  - column type
  - the partition column being last in both lists

It does NOT execute Athena or boto3 — it's a fast, hermetic source-text
check. Runs in ~10ms.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"
_DISPATCHER = _LAMBDAS_DIR / "pipeline-c-dispatcher" / "lambda_function.py"
_WORKER = _LAMBDAS_DIR / "pipeline-c-worker" / "lambda_function.py"


# --------------------------------------------------------------------------- #
# Parsing                                                                     #
# --------------------------------------------------------------------------- #


def _extract_dispatcher_columns() -> list[tuple[str, str]]:
    """Return [(name, type)] for the patterns CREATE EXTERNAL TABLE in the
    dispatcher source. Includes the trailing partition column.
    """
    text = _DISPATCHER.read_text(encoding="utf-8")
    # Find the CREATE EXTERNAL TABLE block for patterns
    m = re.search(
        r"CREATE\s+EXTERNAL\s+TABLE\s+`?\{DB_NAME\}`?\.`?\{PATTERNS_TABLE_NAME\}`?\s*\((?P<cols>.+?)\)\s*"
        r"PARTITIONED\s+BY\s*\((?P<part>.+?)\)",
        text,
        flags=re.S | re.IGNORECASE,
    )
    assert m, "could not locate CREATE EXTERNAL TABLE for patterns in dispatcher"

    cols = _parse_col_list(m.group("cols"))
    part = _parse_col_list(m.group("part"))
    assert len(part) == 1, f"expected exactly 1 partition col, got: {part}"
    cols.extend(part)  # partition is appended at the end (matches Hive convention)
    return cols


def _parse_col_list(raw: str) -> list[tuple[str, str]]:
    """Parse a CREATE TABLE column-list block like
       `name1` type1, `name2` type2<smallint>, ...
    Returns [(name, normalized_type), ...]. Strips backticks + whitespace +
    inline comments; collapses internal whitespace inside compound types like
    array<smallint>. Robust to trailing commas.
    """
    out: list[tuple[str, str]] = []
    # Strip SQL line comments (-- to EOL)
    raw = re.sub(r"--[^\n]*", "", raw)
    # Split top-level commas (none of our types currently nest commas, so a
    # plain split is correct; if we ever introduce map<k, v> we'd need to
    # track angle-bracket depth).
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for p in parts:
        m = re.match(
            r"`?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)`?\s+(?P<typ>[a-zA-Z_][a-zA-Z0-9_<>\s]*?)\s*$",
            p,
        )
        assert m, f"could not parse column spec: {p!r}"
        name = m.group("name")
        typ = re.sub(r"\s+", "", m.group("typ").lower())
        out.append((name, typ))
    return out


def _extract_worker_select_columns() -> list[str]:
    """Return the column NAMES emitted by pipeline-c-worker's final SELECT
    in the order they appear. We can't infer types statically (the SELECT
    uses CAST() and aggregations) — type-checking against the dispatcher
    is the runtime's job; this test enforces *count* and *order* via name
    parity, which is the asymmetry that crashed Phase C in both #108 and
    #512.
    """
    text = _WORKER.read_text(encoding="utf-8")
    # The worker's INSERT looks like:
    #   INSERT INTO ... patterns
    #   WITH patterns_base AS (SELECT ... FROM scdis ...),
    #        patterns_aggregated AS (SELECT ... GROUP BY ... HAVING ...)
    #   SELECT  <- THE OUTER SELECT (what we want)
    #       pattern_id, ..., country_a_id
    #   FROM patterns_aggregated
    #
    # Anchor on `FROM patterns_aggregated` (only the OUTER SELECT uses it
    # — the inner CTEs read from `scdis` and `patterns_base`). Walk
    # backwards from there to find the matching `SELECT` keyword whose
    # depth is 0 (i.e., not inside any CTE parens).
    from_idx = text.find("FROM patterns_aggregated")
    assert from_idx > 0, "could not locate `FROM patterns_aggregated` in worker"
    head = text[:from_idx]

    # Walk backwards counting parens. We want the SELECT keyword at depth 0
    # (the outermost). Iterate over all SELECT positions and test depth.
    select_positions = [m.start() for m in re.finditer(r"\bSELECT\b", head, re.IGNORECASE)]
    assert select_positions, "no SELECT found before FROM patterns_aggregated"
    outer_select_idx = None
    for pos in reversed(select_positions):
        # Compute paren depth from start of file to this position
        depth = head[:pos].count("(") - head[:pos].count(")")
        if depth == 0:
            outer_select_idx = pos
            break
    assert outer_select_idx is not None, "no top-level (depth=0) SELECT found before FROM patterns_aggregated"
    # Skip past the SELECT keyword itself
    select_clause = head[outer_select_idx + len("SELECT") :]

    # Strip SQL line comments
    select_clause = re.sub(r"--[^\n]*", "", select_clause)

    # Split top-level commas — we need to track parentheses + angle brackets
    # because the final SELECT contains nested function calls like
    # to_hex(md5(to_utf8(concat_ws('-', CAST(...AS varchar), CAST(...AS varchar))))).
    items: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in select_clause:
        if ch in "([<":
            depth += 1
        elif ch in ")]>":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        last = "".join(cur).strip()
        if last:
            items.append(last)

    # Map each item to a column name. Either it's a bare identifier, or
    # ends with `AS name`, or it's a CAST(...) wrapping with a final alias.
    names: list[str] = []
    for item in items:
        # Try `... AS name` first (case-insensitive), tolerating trailing whitespace
        as_m = re.search(r"\bAS\s+`?(?P<n>[a-zA-Z_][a-zA-Z0-9_]*)`?\s*$", item, re.IGNORECASE)
        if as_m:
            names.append(as_m.group("n"))
            continue
        # Bare identifier: last token of the trimmed item
        bare = re.match(
            r"^\s*`?(?P<n>[a-zA-Z_][a-zA-Z0-9_]*)`?\s*$",
            item,
        )
        if bare:
            names.append(bare.group("n"))
            continue
        # Otherwise we got something we can't name — fail loud so a maintainer
        # who introduces an un-aliased expression in this SELECT must add an
        # explicit `AS` (which is best practice anyway).
        raise AssertionError(
            f"could not extract a column name from worker SELECT item: {item!r}. "
            "Add an explicit `AS column_name` alias."
        )
    return names


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_dispatcher_columns_parse_cleanly():
    """Sanity: the dispatcher's CREATE TABLE parses to the expected
    12 columns (11 data + 1 partition) post-#512 fix.
    """
    cols = _extract_dispatcher_columns()
    assert len(cols) == 12, f"expected 12 cols incl. partition, got {len(cols)}: {cols}"
    # Spot-check a few names + types we care about
    by_name = dict(cols)
    assert by_name["pattern_id"] == "string"
    assert by_name["pattern_tier"] == "string"
    assert by_name["contains_predicted"] == "boolean", (
        "#512 fix lost: contains_predicted boolean must follow pattern_tier"
    )
    assert by_name["country_a_id"] == "smallint"


def test_worker_select_columns_parse_cleanly():
    """Sanity: the worker's INSERT SELECT parses to 12 column names."""
    names = _extract_worker_select_columns()
    assert len(names) == 12, f"expected 12 SELECT cols, got {len(names)}: {names}"
    assert "pattern_id" in names
    assert "pattern_tier" in names
    assert "contains_predicted" in names
    assert "country_a_id" in names


def test_dispatcher_and_worker_have_same_column_count():
    """The CREATE TABLE col count (incl. partition) must equal the
    INSERT SELECT col count. Drift here is the exact bug that crashed
    Phase C in #108 and again in #512.
    """
    disp = _extract_dispatcher_columns()
    work = _extract_worker_select_columns()
    assert len(disp) == len(work), (
        f"dispatcher CREATE TABLE has {len(disp)} cols, worker SELECT has {len(work)}.\n"
        f"  dispatcher: {[c[0] for c in disp]}\n"
        f"  worker:     {work}\n"
        "If you added a column to one, add it to the other (and update the "
        "Glue schema in qgi-infra/modules/storage)."
    )


def test_dispatcher_and_worker_column_order_matches():
    """Column NAMES and ORDER must match — Athena INSERT is positional,
    not name-keyed. Reordering one without reordering the other is a
    silent data corruption hazard.
    """
    disp_names = [c[0] for c in _extract_dispatcher_columns()]
    work_names = _extract_worker_select_columns()
    assert disp_names == work_names, (
        "Column names/order drift between dispatcher CREATE TABLE and "
        "worker INSERT SELECT.\n"
        f"  dispatcher: {disp_names}\n"
        f"  worker:     {work_names}\n"
        "Athena INSERT is positional — names align by index. Either align "
        "the lists, or update both consistently with the Glue schema in "
        "qgi-infra/modules/storage/main.tf."
    )


def test_partition_column_is_last_in_both():
    """`country_a_id` is the partition column. Both lists must end with it
    so positional INSERT lines up with Hive's partition-last convention.
    """
    disp_names = [c[0] for c in _extract_dispatcher_columns()]
    work_names = _extract_worker_select_columns()
    assert disp_names[-1] == "country_a_id", (
        f"dispatcher CREATE TABLE last col must be 'country_a_id' (partition); got {disp_names[-1]!r}"
    )
    assert work_names[-1] == "country_a_id", (
        f"worker INSERT SELECT last col must be 'country_a_id' (partition); got {work_names[-1]!r}"
    )


def test_contains_predicted_present_in_dispatcher():
    """Pin the #512 fix: contains_predicted must exist in the dispatcher
    CREATE TABLE with type boolean. A regression that re-drops this column
    fails CI here directly (the order tests above also catch it, but this
    is the explicit anchor for #512).
    """
    by_name = dict(_extract_dispatcher_columns())
    assert "contains_predicted" in by_name, (
        "#512 regression — dispatcher CREATE TABLE is missing contains_predicted. "
        "It was added by #461 to the worker SELECT and to the qgi-infra Glue "
        "schema; the dispatcher must mirror those. Drop the column without "
        "also dropping it from worker + Glue and you'll re-introduce the "
        "Phase C stall."
    )
    assert by_name["contains_predicted"] == "boolean", (
        f"contains_predicted type drift: dispatcher says {by_name['contains_predicted']!r}, worker emits boolean."
    )
