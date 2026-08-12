"""Unit tests for build_indicator_directions.py.

Covers the regex row-parser, tag normalization, conflict resolution
(cascade wins per Lane B R2), and the emit-JSON shape. The generator
script is a one-shot data-massage tool, but it's the load-bearing
input for arms A/B of Phase 5 v0.1a so the parser correctness matters.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_indicator_directions.py"
_spec = importlib.util.spec_from_file_location("build_indicator_directions", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["build_indicator_directions"] = mod
_spec.loader.exec_module(mod)


# ===========================================================================
# Column-split parser (T1 fix — replaced single-shot regex)
# ===========================================================================
#
# These tests use parse_draft() end-to-end (via temp files), which is the
# stable public surface. The internal parsers (INDICATOR_CELL_RE,
# DIRECTION_CELL_RE, _split_table_row) are exercised through parse_draft.

def _parse_one_line(tmp_path, line):
    """Helper: write a single Markdown line to a temp .md and parse it."""
    p = tmp_path / "single.md"
    p.write_text(line + "\n", encoding="utf-8")
    return mod.parse_draft(p, source_label="test")


def test_row_re_cascade_vdem_style(tmp_path):
    """Cascade V-Dem rows parse: `| **VD-NN api_code** (...) | **+1** | text | `[tag]` |`"""
    rows = _parse_one_line(
        tmp_path,
        "| **VD-01 v2x_polyarchy** (Electoral Democracy Index, 0-1) | **+1** | "
        "Justification text. | `[lit-only]` |"
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["catalog_code"] == "VD-01"
    assert r["api_code"] == "v2x_polyarchy"
    assert r["direction"] == 1
    assert "Justification" in r["justification"]
    assert r["tag"] == "[lit-only]"


def test_row_re_cascade_wgi_bare_style(tmp_path):
    """WGI rows have NO catalog code: `| **CC.EST** (...) | **+1** | ... | `[tag]` |`"""
    rows = _parse_one_line(
        tmp_path,
        "| **CC.EST** (Control of Corruption, point estimate) | **+1** | text. | `[lit-only]` |"
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["catalog_code"] is None
    assert r["api_code"] == "CC.EST"
    assert r["direction"] == 1


def test_row_re_cascade_negative_one(tmp_path):
    """Negative signs parse correctly."""
    rows = _parse_one_line(
        tmp_path,
        "| **GC.DOD.TOTL.GD.ZS** (Govt debt, % GDP) | **-1** | text. | `[lit-only]` |"
    )
    assert len(rows) == 1
    assert rows[0]["api_code"] == "GC.DOD.TOTL.GD.ZS"
    assert rows[0]["direction"] == -1


def test_row_re_cascade_zero_direction(tmp_path):
    """direction:0 rows parse correctly."""
    rows = _parse_one_line(
        tmp_path,
        "| **VD-10 v2x_regime** (Regime Type, 0-3 categorical) | **0** | "
        "Categorical: text. | `[no lit, direction: 0]` |"
    )
    assert len(rows) == 1
    assert rows[0]["direction"] == 0
    assert "no lit" in rows[0]["tag"]


def test_row_re_ml_wb_coded_style(tmp_path):
    """ML rows with WB catalog code parse, including free-text tag."""
    rows = _parse_one_line(
        tmp_path,
        "| **WB-03 SM.POP.REFG.OR** (Refugees by country of origin) | **+1** | "
        "Justification text. | High confidence (UCDP/UNHCR literature). |"
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["catalog_code"] == "WB-03"
    assert r["api_code"] == "SM.POP.REFG.OR"
    assert r["direction"] == 1
    assert "High confidence" in r["tag"]


def test_row_re_ml_bare_api_code_style(tmp_path):
    """ML rows without catalog code (bare api): `| **API.CODE** (...) | ... |`"""
    rows = _parse_one_line(
        tmp_path,
        "| **SE.ADT.LITR.ZS** (Adult literacy rate) | **-1** | "
        "Higher literacy = stable. | High confidence; SHAP consistently negative. |"
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["catalog_code"] is None
    assert r["api_code"] == "SE.ADT.LITR.ZS"
    assert r["direction"] == -1


def test_row_re_skips_non_matching_lines(tmp_path):
    """Header/separator/explanation lines must NOT produce rows."""
    p = tmp_path / "no_rows.md"
    p.write_text(
        "| Indicator | Direction | Justification (literature) | Tag |\n"
        "|---|---|---|---|\n"
        "## Sub-batch 1 - V-Dem governance + civil liberties (39 indicators)\n"
        "Per Lane B R1 (locked 2026-05-10): every signed indicator cites.\n",
        encoding="utf-8",
    )
    assert mod.parse_draft(p, source_label="test") == []


# ===========================================================================
# T1 fix (PR #47): justification pipe-safety
# ===========================================================================

def test_parse_draft_justification_with_escaped_pipe(tmp_path):
    """T1: A justification cell containing `\\|` (Markdown-escaped pipe)
    must NOT silently truncate to the first pipe. The column-split
    parser should preserve the escaped pipe in the justification.

    Before the T1 fix, the single-regex parser would treat `\\|` as a
    column separator and yield a truncated justification + swallowed tag.
    """
    rows = _parse_one_line(
        tmp_path,
        "| **CC.EST** (Control of Corruption) | **+1** | "
        "Reinhart \\| Rogoff 2009 establishes mechanism. | `[lit-only]` |"
    )
    assert len(rows) == 1
    r = rows[0]
    # Justification must contain the pipe character literally (after unescaping)
    assert "|" in r["justification"], (
        f"escaped pipe lost from justification: {r['justification']!r}"
    )
    assert "Reinhart" in r["justification"]
    assert "Rogoff" in r["justification"]
    # Tag must NOT have swallowed the rest of the justification
    assert r["tag"] == "[lit-only]"


# ===========================================================================
# T5 fix (PR #47): bare-catalog-as-api-code shape (forward-compat)
# ===========================================================================

def test_row_re_t5_bare_catalog_as_api_code(tmp_path):
    """T5: forward-compat for a future row that uses `FA-01` as the
    api_code directly (no separate token after the catalog prefix).
    Current drafts don't have this shape but the parser should handle it.
    """
    rows = _parse_one_line(
        tmp_path,
        "| **FA-01** (Prevalence of undernourishment, %) | **+1** | "
        "FAO methodology. | `[lit-only]` |"
    )
    assert len(rows) == 1
    r = rows[0]
    # When the catalog code is the only thing in the **...**, the parser
    # should treat the catalog code itself as the api_code (T5 fix).
    assert r["api_code"] == "FA-01"
    assert r["catalog_code"] == "FA-01"
    assert r["direction"] == 1


# ===========================================================================
# Tag normalization
# ===========================================================================

def test_normalize_tag_backtick_bracket():
    """Cascade-style `[lit-only]` → [lit-only] (no backticks in JSON)."""
    assert mod._normalize_tag("`[lit-only]`") == "[lit-only]"
    assert mod._normalize_tag("`[no lit, direction: 0]`") == "[no lit, direction: 0]"


def test_normalize_tag_free_text_passthrough():
    """ML free-text tags pass through unchanged."""
    raw = "High confidence (UCDP/UNHCR literature; surfaces in civil_war heads)."
    assert mod._normalize_tag(raw) == raw


def test_normalize_tag_strips_trailing_pipe():
    """Tag column captured up to but not including the closing pipe."""
    assert mod._normalize_tag("`[lit-only]` |") == "[lit-only]"


# ===========================================================================
# Conflict resolution (Lane B R2: cascade wins)
# ===========================================================================

def test_merge_no_conflict_same_sign_cascade_wins_source():
    """Same api_code, same direction → emit once with cascade source."""
    cascade = [{"api_code": "X", "direction": 1, "tag": "[lit-only]",
                "justification": "c", "source": "cascade", "catalog_code": None}]
    ml = [{"api_code": "X", "direction": 1, "tag": "High conf",
           "justification": "m", "source": "ml-opus", "catalog_code": None}]
    merged, conflicts = mod.merge_with_conflict_resolution(cascade, ml)
    assert len(merged) == 1
    assert merged[0]["source"] == "cascade"
    assert len(conflicts) == 0


def test_merge_conflict_different_sign_cascade_wins():
    """Same api_code, DIFFERENT NON-ZERO directions → R2 sign_conflict;
    cascade wins."""
    cascade = [{"api_code": "X", "direction": 1, "tag": "[lit-only]",
                "justification": "c", "source": "cascade", "catalog_code": None}]
    ml = [{"api_code": "X", "direction": -1, "tag": "High conf",
           "justification": "m", "source": "ml-opus", "catalog_code": None}]
    merged, conflicts = mod.merge_with_conflict_resolution(cascade, ml)
    assert len(merged) == 1
    assert merged[0]["direction"] == 1  # cascade wins
    assert len(conflicts) == 1
    assert conflicts[0]["api_code"] == "X"
    assert conflicts[0]["resolved_to"] == 1
    assert conflicts[0]["resolved_source"] == "cascade"
    # T4 strict review fix: conflict_type discriminator
    assert conflicts[0]["conflict_type"] == "sign"
    assert "R2" in conflicts[0]["reason"]


def test_merge_conflict_cascade_zero_vs_ml_nonzero():
    """Cascade direction:0 (Majles-deferred) + ML +1 → R1 deferral_override
    (semantically distinct from R2 sign conflict per T4 strict review)."""
    cascade = [{"api_code": "v2cseeorgs", "direction": 0,
                "tag": "[no lit, direction: 0]", "justification": "deferred",
                "source": "cascade", "catalog_code": "VD-24"}]
    ml = [{"api_code": "v2cseeorgs", "direction": 1, "tag": "High conf",
           "justification": "Putnam mechanism", "source": "ml-opus",
           "catalog_code": None}]
    merged, conflicts = mod.merge_with_conflict_resolution(cascade, ml)
    assert len(merged) == 1
    assert merged[0]["direction"] == 0
    assert len(conflicts) == 1
    assert conflicts[0]["resolved_to"] == 0
    # T4: deferral, NOT sign conflict
    assert conflicts[0]["conflict_type"] == "deferral"
    assert "R1" in conflicts[0]["reason"]
    assert "Majles" in conflicts[0]["reason"]


def test_emit_json_source_drafts_uses_posix_paths():
    """T2 strict review fix: source_drafts paths use forward slashes
    (POSIX), not Windows backslashes, for cross-platform diff stability."""
    rows = [{"api_code": "X", "direction": 1, "tag": "[lit-only]",
             "justification": "j", "source": "cascade", "catalog_code": None}]
    payload = mod.emit_json(rows, conflicts=[], cascade_n=1, ml_n=0)
    assert "\\" not in payload["source_drafts"]["cascade"], (
        f"backslashes in source_drafts: {payload['source_drafts']!r}"
    )
    assert "\\" not in payload["source_drafts"]["ml"]
    # Sanity: paths should start with the qgi-docs/internal/ops prefix
    assert payload["source_drafts"]["cascade"].startswith("qgi-docs/")
    assert payload["source_drafts"]["ml"].startswith("qgi-docs/")


def test_merge_disjoint_keys_concatenates():
    """Cascade has X, ML has Y → both emitted, sorted by api_code."""
    cascade = [{"api_code": "X", "direction": 1, "tag": "[lit-only]",
                "justification": "c", "source": "cascade", "catalog_code": None}]
    ml = [{"api_code": "Y", "direction": -1, "tag": "High conf",
           "justification": "m", "source": "ml-opus", "catalog_code": None}]
    merged, conflicts = mod.merge_with_conflict_resolution(cascade, ml)
    assert len(merged) == 2
    assert [r["api_code"] for r in merged] == ["X", "Y"]
    assert len(conflicts) == 0


# ===========================================================================
# parse_draft end-to-end
# ===========================================================================

def test_parse_draft_returns_empty_on_missing_file(tmp_path):
    """Missing draft → empty list, no crash."""
    out = mod.parse_draft(tmp_path / "nope.md", source_label="test")
    assert out == []


def test_parse_draft_extracts_multiple_rows(tmp_path):
    """Multi-row markdown parses cleanly."""
    md = tmp_path / "draft.md"
    md.write_text(
        "# Header\n"
        "| **VD-01 v2x_polyarchy** (Electoral Democracy, 0-1) | **+1** | "
        "Justification 1. | `[lit-only]` |\n"
        "| **GC.DOD.TOTL.GD.ZS** (Govt debt, % GDP) | **-1** | "
        "Justification 2. | `[lit-only]` |\n"
        "| **WB-03 SM.POP.REFG.OR** (Refugees) | **+1** | Justification 3. | "
        "High confidence (UCDP). |\n",
        encoding="utf-8",
    )
    rows = mod.parse_draft(md, source_label="test")
    assert len(rows) == 3
    assert rows[0]["api_code"] == "v2x_polyarchy"
    assert rows[0]["direction"] == 1
    assert rows[1]["api_code"] == "GC.DOD.TOTL.GD.ZS"
    assert rows[1]["direction"] == -1
    assert rows[2]["api_code"] == "SM.POP.REFG.OR"
    # ML free-text tag preserved
    assert "High confidence" in rows[2]["tag"]


# ===========================================================================
# emit_json shape
# ===========================================================================

def test_emit_json_schema_matches_loader_contract():
    """Output JSON must have: schema_version, generated, directions list
    with {api_code, direction, tag, justification, source} per row.
    Matches load_direction_annotations() expected schema."""
    rows = [{"api_code": "X", "direction": 1, "tag": "[lit-only]",
             "justification": "j", "source": "cascade", "catalog_code": None}]
    payload = mod.emit_json(rows, conflicts=[], cascade_n=1, ml_n=0)
    assert payload["schema_version"] == 1
    assert "generated" in payload
    assert "directions" in payload
    assert len(payload["directions"]) == 1
    d = payload["directions"][0]
    assert d["api_code"] == "X"
    assert d["direction"] == 1
    assert d["tag"] == "[lit-only]"
    assert d["source"] == "cascade"
    # catalog_code is provenance — not in the emitted row
    assert "catalog_code" not in d


def test_emit_json_includes_conflicts_audit_trail():
    """Conflicts list surfaces in the output for audit visibility."""
    conflicts = [{"api_code": "X", "cascade_direction": 1, "ml_direction": -1,
                  "resolved_to": 1, "resolved_source": "cascade",
                  "reason": "R2 fallback"}]
    payload = mod.emit_json([], conflicts, cascade_n=0, ml_n=1)
    assert payload["conflicts"] == conflicts
    assert payload["row_counts"]["conflicts_resolved"] == 1


def test_emit_json_row_counts():
    """row_counts shows parsed-input + merged-output sizes for sanity."""
    rows = [{"api_code": f"X{i}", "direction": 1, "tag": "[lit-only]",
             "justification": "j", "source": "cascade", "catalog_code": None}
            for i in range(3)]
    payload = mod.emit_json(rows, conflicts=[], cascade_n=2, ml_n=1)
    assert payload["row_counts"]["cascade_rows_parsed"] == 2
    assert payload["row_counts"]["ml_rows_parsed"] == 1
    assert payload["row_counts"]["merged_rows"] == 3


# ===========================================================================
# Output loads cleanly via the validate_weight_matrix.py loader
# ===========================================================================

def test_generator_output_is_loadable_by_validate_weight_matrix(tmp_path):
    """End-to-end: generator output must be parsable by
    load_direction_annotations() — the consumer's loader contract."""
    # Build a fixture output via the generator
    rows = [{"api_code": "v2x_libdem", "direction": 1, "tag": "[lit-only]",
             "justification": "j", "source": "cascade", "catalog_code": None},
            {"api_code": "GC.DOD.TOTL.GD.ZS", "direction": -1, "tag": "[lit-only]",
             "justification": "j", "source": "cascade", "catalog_code": None}]
    payload = mod.emit_json(rows, conflicts=[], cascade_n=2, ml_n=0)
    out_path = tmp_path / "indicator-directions.json"
    out_path.write_text(json.dumps(payload), encoding="utf-8")

    # Load the consumer-side loader and verify it parses correctly
    _vwm_path = Path(__file__).resolve().parent.parent / "scripts" / "validate_weight_matrix.py"
    _spec = importlib.util.spec_from_file_location("vwm", _vwm_path)
    vwm = importlib.util.module_from_spec(_spec)
    sys.modules["vwm"] = vwm
    _spec.loader.exec_module(vwm)

    result = vwm.load_direction_annotations(path=out_path)
    assert result == {"v2x_libdem": 1, "GC.DOD.TOTL.GD.ZS": -1}


# ===========================================================================
# T3 fix (PR #47): determinism — frozen-timestamp + byte-equal output
# ===========================================================================

def test_emit_json_frozen_timestamp_pinned():
    """T3: When `frozen_timestamp` is set, the output JSON's `generated`
    field uses it verbatim (no wall-clock contamination)."""
    rows = [{"api_code": "X", "direction": 1, "tag": "[lit-only]",
             "justification": "j", "source": "cascade", "catalog_code": None}]
    fixed = "2026-05-11T00:00:00+00:00"
    payload = mod.emit_json(rows, conflicts=[], cascade_n=1, ml_n=0,
                             frozen_timestamp=fixed)
    assert payload["generated"] == fixed


def test_emit_json_byte_equal_with_frozen_timestamp():
    """T3: Two consecutive runs with the same frozen_timestamp and same
    inputs produce byte-identical JSON output. This is the reproducible-
    builds contract."""
    rows = [{"api_code": f"X{i}", "direction": 1, "tag": "[lit-only]",
             "justification": "j", "source": "cascade", "catalog_code": None}
            for i in range(5)]
    fixed = "2026-05-11T00:00:00+00:00"
    p1 = mod.emit_json(rows, conflicts=[], cascade_n=5, ml_n=0,
                        frozen_timestamp=fixed)
    p2 = mod.emit_json(rows, conflicts=[], cascade_n=5, ml_n=0,
                        frozen_timestamp=fixed)
    # Compare JSON-serialized bytes (sorted keys for stability not strictly
    # required since both runs share insertion order, but defensive).
    import json as _json
    assert _json.dumps(p1, sort_keys=True) == _json.dumps(p2, sort_keys=True)


def test_resolve_generated_timestamp_source_date_epoch(monkeypatch):
    """T3: SOURCE_DATE_EPOCH env var sets the timestamp (reproducible-
    builds convention from reproducible-builds.org)."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1747008000")  # 2025-05-12T00:00:00Z
    result = mod._resolve_generated_timestamp(frozen=None)
    assert result.startswith("2025-05-12T00:00:00")


def test_resolve_generated_timestamp_explicit_overrides_env(monkeypatch):
    """T3: Explicit `--frozen-timestamp` takes precedence over SOURCE_DATE_EPOCH."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1747008000")
    fixed = "2026-05-11T12:34:56+00:00"
    result = mod._resolve_generated_timestamp(frozen=fixed)
    assert result == fixed


def test_resolve_generated_timestamp_falls_back_to_now(monkeypatch):
    """T3: With neither --frozen-timestamp nor SOURCE_DATE_EPOCH,
    wall-clock UTC now is used. Just verify it's a non-empty ISO string."""
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    result = mod._resolve_generated_timestamp(frozen=None)
    # Wall-clock — should at least contain T and timezone info
    assert "T" in result
    assert "+" in result or "Z" in result


# ===========================================================================
# T6 fix (PR #47): _normalize_tag strips standalone backticks
# ===========================================================================

def test_normalize_tag_strips_standalone_backticks():
    """T6: `something` (backtick-only, no brackets) should now return
    `something` (stripped). Previously the function silently returned
    the input with backticks preserved, contradicting the docstring."""
    assert mod._normalize_tag("`something`") == "something"
    assert mod._normalize_tag("`Free text in backticks`") == "Free text in backticks"


# ===========================================================================
# T7 fix (PR #47): coverage delta vs audit set
# ===========================================================================

def test_print_coverage_delta_smoke():
    """T7: _print_coverage_delta prints the delta to stdout without
    crashing. Uses the real audit JSON path (which exists in the repo);
    if absent, prints a 'skipped' message rather than crashing."""
    import io
    import contextlib
    merged = [
        {"api_code": "X1", "direction": 1, "tag": "[lit-only]",
         "justification": "j", "source": "cascade", "catalog_code": None},
    ]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mod._print_coverage_delta(merged)
    out = buf.getvalue()
    # Either prints coverage data OR prints 'skipped' message — both are valid
    assert "[coverage]" in out


def test_print_coverage_delta_with_fixture_audit(tmp_path, monkeypatch):
    """T7: With a synthetic audit JSON pointing at known codes, the
    coverage delta numbers should match exactly."""
    import io
    import contextlib
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps({
        "results": {"A": {"classification": "I(1)"},
                    "B": {"classification": "I(1)"},
                    "C": {"classification": "I(1)"}}
    }), encoding="utf-8")
    # monkeypatch the module-level constant
    monkeypatch.setattr(mod, "AUDIT_JSON_PATH", audit_path)
    merged = [
        {"api_code": "A", "direction": 1, "tag": "[lit-only]",
         "justification": "j", "source": "cascade", "catalog_code": None},
        {"api_code": "B", "direction": -1, "tag": "[lit-only]",
         "justification": "j", "source": "cascade", "catalog_code": None},
        {"api_code": "D",  # not in audit set
         "direction": 0, "tag": "[no lit]",
         "justification": "j", "source": "cascade", "catalog_code": None},
    ]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mod._print_coverage_delta(merged)
    out = buf.getvalue()
    # audit=3 (A,B,C); merged=3 (A,B,D); covered=2 (A,B); missing=1 (C); extra=1 (D)
    assert "audited=3" in out
    assert "in_directions=3" in out
    assert "covered=2" in out
    assert "audited_but_missing=1" in out
    assert "in_directions_but_not_audited=1" in out


# ===========================================================================
# T1 + T5 + T7 fix verifications via the existing parse_draft path
# ===========================================================================

def test_split_table_row_normal():
    """_split_table_row strips leading + trailing empties."""
    parts = mod._split_table_row("| a | b | c | d |")
    assert parts == [" a ", " b ", " c ", " d "]


def test_split_table_row_with_escaped_pipe():
    """`\\|` should NOT split the cell."""
    parts = mod._split_table_row(r"| a | b \| c | d | e |")
    assert parts == [" a ", " b | c ", " d ", " e "]


def test_split_table_row_returns_none_for_non_table_line():
    """Lines without `|` return None."""
    assert mod._split_table_row("plain text line") is None
