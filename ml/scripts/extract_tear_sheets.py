"""Extract Stage 5 buyer-disclosure paper Section 4 tear-sheets to structured JSON.

Per qgi-aws-tf ticket #644 + 2026-05-11 Majles Topic 5 action item AI-5.2.

Parses `docs/specs/methodology/stage-5-buyer-disclosure-methodology-paper.md`
Section 4 prose for each of the 13 LOCKed recipes (post-KI-2 amendment) and
emits structured JSON for the frontend bake script (#643) to consume.

Output schema (per LOCKed recipe):
- recipe_id (slug)
- tier (STRONG | MODERATE | MARGINAL)
- architecture (D2 | D5)
- loco_auc (float)
- n_pos_loco (int)
- assignment_confidence (HIGH | MODERATE | LOW)
- in_sample_f1_ece (float)
- in_sample_f2_auc (float)
- in_sample_f2_ci_lower (float)
- in_sample_f2_ci_upper (float)
- top_1_training_country (str)
- top_1_training_country_share (float in [0, 1])
- cohort_ece: {high, mid, low} (floats)
- zero_positive_cohort_flag (str or null)
- per_recipe_anchor_ahi (float or null)
- per_recipe_anchor_ahi_reason (str or null — "Not measured" rationale or other)
- f_h_3_advisory_only (bool)
- f_rule_anomaly (bool — True iff in-sample F2 fails under assigned arch)
- mechanism_narrative (str)
- buyer_disclosure_recommendation (str)
- open_followups (list[str])

Per Nasrin's binding rule ("Per-recipe AHI: 'Not measured' must be explicit
text, not a blank field"), recipes without measurable AHI carry
`per_recipe_anchor_ahi = null` AND `per_recipe_anchor_ahi_reason` set.

Usage:
    python scripts/extract_tear_sheets.py \
        --paper ../docs/specs/methodology/stage-5-buyer-disclosure-methodology-paper.md \
        --output ../qgi-data/reference/tear-sheets-2026-05.json

Falsified recipes (post-KI-2: territorial_disputes) are SKIPPED by the parser
even though their tear-sheet remains in Section 5 for historical replication.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

# Expected post-KI-2 LOCKED recipe set (13). Sentinel against silent paper edits.
EXPECTED_LOCKED_RECIPES: frozenset[str] = frozenset({
    "civil_war_and_insurgency",
    "multilateral_agreement",
    "terrorist_attack",
    "energy_policy",
    "epidemic_and_pandemic",
    "human_rights_violation",
    "bilateral_treaty",
    "elections_and_voting",
    "foreign_intervention",
    "humanitarian_crisis",
    "peacekeeping_and_peace_process",
    "government_formation",
    "mass_protest",
})

# Header pattern. Captures recipe_id + architecture + tier (+ optional parenthetical).
# Examples this matches:
#   #### `civil_war_and_insurgency` — D2 STRONG
#   #### `multilateral_agreement` — D5 STRONG (architecture-rescued)
#   #### `epidemic_and_pandemic` — D5 STRONG (ADVISORY-ONLY + in-sample F2 caveat)
# Does NOT match (struck-through FALSIFIED):
#   #### ~~`territorial_disputes`~~ — FALSIFIED under hybrid 2026-05-11
RECIPE_HEADER_RE = re.compile(
    r"^####\s+`(?P<recipe_id>[a-z_]+)`\s+—\s+"
    r"(?P<architecture>D[25])\s+"
    r"(?P<tier>STRONG|MODERATE|MARGINAL)"
    r"(?P<parenthetical>\s+\([^)]+\))?\s*$",
    re.MULTILINE,
)


def _strip_bold(s: str) -> str:
    """Drop markdown bold markers from a string."""
    return s.replace("**", "")


def _float_or_none(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _split_into_blocks(paper_text: str) -> dict[str, str]:
    """Split the paper into recipe-keyed blocks.

    Returns ``{recipe_id: block_text}`` for every LOCKED recipe found in
    Section 4. Block text spans from the recipe header line through the
    next `---` divider (exclusive) OR the next `####` header (exclusive),
    whichever comes first.

    Struck-through FALSIFIED recipes (e.g. territorial_disputes) are
    skipped by the header regex.
    """
    blocks: dict[str, str] = {}
    headers = list(RECIPE_HEADER_RE.finditer(paper_text))
    for idx, match in enumerate(headers):
        recipe_id = match.group("recipe_id")
        start = match.end()
        # Block ends at the next `---` divider OR next #### header
        end_divider = paper_text.find("\n---\n", start)
        end_next_header = (
            headers[idx + 1].start() if idx + 1 < len(headers) else len(paper_text)
        )
        if end_divider == -1:
            end = end_next_header
        else:
            end = min(end_divider, end_next_header)
        blocks[recipe_id] = paper_text[start:end]
    return blocks


def _extract_loco_line(block: str) -> tuple[float, int, str]:
    """Parse `**LOCO-AUC:** ... (n_pos_LOCO = ...; Assignment confidence = ...)`.

    Handles bold-wrapped numerics + extra phrase qualifiers like "under D5
    partition" or "within hysteresis" or even an embedded parenthetical
    (`**0.5847 (rescued from D2 LEAK 0.4449)**` on mass_protest line 393).

    Returns (loco_auc, n_pos_loco, assignment_confidence).
    """
    line_m = re.search(r"\*\*LOCO-AUC:\*\*\s+(?P<rest>[^\n]+)", block)
    if line_m is None:
        raise ValueError("LOCO-AUC line not found")
    rest = _strip_bold(line_m.group("rest"))
    # First float on the line is LOCO
    loco_m = re.search(r"([\d.]+)", rest)
    if loco_m is None:
        raise ValueError("LOCO-AUC numeric value not found")
    loco_auc = float(loco_m.group(1))
    # n_pos_LOCO = N (anywhere on the line)
    n_pos_m = re.search(r"n_pos_LOCO\s*=\s*(\d+)", rest)
    if n_pos_m is None:
        raise ValueError("n_pos_LOCO not found on LOCO-AUC line")
    n_pos_loco = int(n_pos_m.group(1))
    # Assignment confidence = X (anywhere after n_pos_LOCO)
    conf_m = re.search(
        r"Assignment\s+confidence\s*=\s*(HIGH|MODERATE|LOW)",
        rest,
        re.IGNORECASE,
    )
    if conf_m is None:
        raise ValueError("Assignment confidence not found on LOCO-AUC line")
    return loco_auc, n_pos_loco, conf_m.group(1).upper()


def _extract_f1_ece(block: str) -> float:
    m = re.search(r"\*\*In-sample F1 ECE:\*\*\s+([\d.]+)", block)
    if m is None:
        raise ValueError("In-sample F1 ECE line not found")
    return float(m.group(1))


def _extract_f2(block: str) -> tuple[float, float, float, bool]:
    """Parse `**In-sample F2 AUC:** point [ci_lower, ci_upper] ...`.

    Returns (auc, ci_lower, ci_upper, f_rule_anomaly).
    f_rule_anomaly is True iff the F2 line contains "FAILS F2 in-sample".
    """
    # Numbers may be wrapped in **bold** when the F2 fails
    line_re = re.compile(
        r"\*\*In-sample F2 AUC:\*\*\s+\*?\*?(?P<auc>[\d.]+)\*?\*?\s+"
        r"\[(?P<lo>[\d.]+),\s*(?P<hi>[\d.]+)\]"
        r"(?P<rest>[^\n]*)"
    )
    m = line_re.search(block)
    if m is None:
        raise ValueError("In-sample F2 AUC line not found")
    f_rule_anomaly = "FAILS" in m.group("rest").upper()
    return (
        float(m.group("auc")),
        float(m.group("lo")),
        float(m.group("hi")),
        f_rule_anomaly,
    )


def _extract_top_1_country(block: str) -> tuple[str | None, float | None]:
    """Parse `**Top-1 training country:** name PCT% (...)`.

    Returns (country_name, share_as_float_in_0_1).

    Handles three real variants observed in the paper:
    1. Standard: `**Top-1 training country:** syria 22.2% (caution-level)`
    2. Fully-bold-wrapped: `**Top-1 training country:** **venezuela 71.4% (HIGH ...)**`
    3. Not audited: `**Top-1 training country:** not in concentration audit (...)`
       → returns (None, None); concentration audit didn't cover this recipe.
    """
    # Find the line, strip surrounding bold markers
    line_m = re.search(
        r"\*\*Top-1 training country:\*\*\s+(?P<rest>[^\n]+)",
        block,
    )
    if line_m is None:
        raise ValueError("Top-1 training country line not found")
    rest = _strip_bold(line_m.group("rest")).strip()
    # Variant 3: not audited
    if rest.lower().startswith("not in concentration audit"):
        return None, None
    # Variants 1 + 2: name PCT%
    m = re.match(r"(?P<name>[A-Za-z_][\w\s\-]+?)\s+(?P<pct>[\d.]+)%", rest)
    if m is None:
        raise ValueError(f"Top-1 training country line not parseable: {rest!r}")
    # Round to 4 decimals to avoid IEEE 754 representation tails like
    # 0.7140000000000001 (= 71.4 / 100). Three decimals would be enough for
    # current display needs but 4 leaves headroom for sub-percent precision.
    return m.group("name").strip(), round(float(m.group("pct")) / 100.0, 4)


def _extract_cohort_ece(block: str) -> tuple[dict[str, float], str | None]:
    """Parse `**Cohort-stratified ECE:** ... — high X; mid Y; low Z (...)`
    AND the following bullet `- Zero-positive cohort flag: ...`.

    Returns ({high, mid, low}, zero_positive_cohort_flag).
    flag is None when "none"; otherwise the verbatim phrase.
    """
    # Some entries carry per-cohort parentheticals before the semicolon, e.g.
    # `high 0.0000 (n_pos=0 confirmed); mid 0.0035 (n_pos=1); low 0.0000 (...)`.
    # Allow any non-semicolon content between the number and the next delimiter.
    cohort_line_re = re.compile(
        r"\*\*Cohort-stratified ECE:\*\*[^\n]*?—\s*"
        r"high\s+\*?\*?(?P<high>[\d.]+)\*?\*?[^;]*;\s*"
        r"mid\s+\*?\*?(?P<mid>[\d.]+)\*?\*?[^;]*;\s*"
        r"low\s+\*?\*?(?P<low>[\d.]+)\*?\*?",
        re.IGNORECASE,
    )
    m = cohort_line_re.search(block)
    if m is None:
        raise ValueError("Cohort-stratified ECE line not found")
    cohort = {
        "high": float(m.group("high")),
        "mid": float(m.group("mid")),
        "low": float(m.group("low")),
    }
    flag_re = re.compile(r"-\s+Zero-positive cohort flag:\s*(?P<flag>[^\n]+)")
    flag_m = flag_re.search(block)
    flag_text = flag_m.group("flag").strip() if flag_m else None
    # Normalize "none" (case-insensitive, optionally bold-wrapped) → None
    if flag_text and _strip_bold(flag_text).strip().lower() == "none":
        flag_text = None
    return cohort, flag_text


def _extract_anchor_ahi(block: str) -> tuple[float | None, str | None]:
    """Parse `**Per-recipe anchor AHI:** ...`.

    Two cases:
    1. Measured: `**Per-recipe anchor AHI:** **0.1052** (n_evaluable = 26; ...)`
       → (0.1052, None)
    2. Not measured: `**Per-recipe anchor AHI:** **Not measured** — reason text`
       → (None, "Not measured — reason text")

    Per Nasrin's binding rule, "Not measured" stays as explicit reason text.
    """
    line_re = re.compile(
        r"\*\*Per-recipe anchor AHI:\*\*\s+\*?\*?(?P<head>[^*\n]+?)\*?\*?\s*"
        r"(?:\((?P<paren>[^)]+)\)|—\s+(?P<dash_reason>[^\n]+))"
    )
    m = line_re.search(block)
    if m is None:
        raise ValueError("Per-recipe anchor AHI line not found")
    head = m.group("head").strip()
    # Case 1: head is a float-looking value
    try:
        value = float(head)
        return value, None
    except ValueError:
        pass
    # Case 2: head is "Not measured" or similar; reason is in the dash-clause
    reason = m.group("dash_reason")
    if reason is None:
        reason = m.group("paren") or ""
    return None, f"{head} — {reason.strip()}"


def _extract_advisory_only(block: str) -> bool:
    """Parse `**F-H-3 ADVISORY-ONLY:** yes | no (...)`."""
    m = re.search(
        r"\*\*F-H-3 ADVISORY-ONLY:\*\*\s+\*?\*?(?P<val>yes|no)\*?\*?",
        block,
        re.IGNORECASE,
    )
    if m is None:
        raise ValueError("F-H-3 ADVISORY-ONLY line not found")
    return m.group("val").lower() == "yes"


def _extract_mechanism(block: str) -> str:
    """Parse `**Mechanism:** ...` — multi-line until next `**Field:**` marker.

    Returns the narrative as a single string with internal newlines collapsed
    to spaces (so the consumer can render at their preferred width).
    """
    # Capture text after `**Mechanism:**` up to (but not including) the
    # next bolded label at line start.
    m = re.search(
        r"\*\*Mechanism:\*\*\s+(?P<text>.*?)(?=\n\*\*[A-Z]|\Z)",
        block,
        re.DOTALL,
    )
    if m is None:
        raise ValueError("Mechanism line not found")
    return re.sub(r"\s+", " ", m.group("text")).strip()


def _extract_buyer_disclosure(block: str) -> str:
    """Parse `**Buyer-disclosure recommendation:** ...`."""
    m = re.search(
        r"\*\*Buyer-disclosure recommendation:\*\*\s+(?P<text>.*?)(?=\n\*\*[A-Z]|\Z)",
        block,
        re.DOTALL,
    )
    if m is None:
        raise ValueError("Buyer-disclosure recommendation line not found")
    return re.sub(r"\s+", " ", m.group("text")).strip()


def _extract_open_followups(block: str) -> list[str]:
    """Parse `**Open follow-ups:** ...`.

    "none" (case-insensitive) → []. Otherwise return the followup text as a
    single-element list; the prose may carry multiple followups joined by
    "; " or sentence breaks but we preserve the verbatim string for the
    consumer to display.

    Limitation: the regex stops at the next `**Field:**` marker, `\n---`, or
    end-of-block. If a future paper edit wraps a followup across multiple
    lines with no bold label on the continuation, only the first line will
    be captured. Followups in the current paper (post-KI-2) are all single-
    line; revisit if multi-line followups become common.
    """
    m = re.search(
        r"\*\*Open follow-ups:\*\*\s+(?P<text>.*?)(?=\n\*\*[A-Z]|\n---|\Z)",
        block,
        re.DOTALL,
    )
    if m is None:
        return []
    text = re.sub(r"\s+", " ", m.group("text")).strip()
    if text.lower() == "none":
        return []
    return [text]


def parse_recipe_block(recipe_id: str, header_match: re.Match[str], block: str) -> dict[str, Any]:
    """Parse a single recipe block into the structured tear-sheet schema."""
    architecture = header_match.group("architecture")
    tier = header_match.group("tier")
    loco_auc, n_pos_loco, assignment_confidence = _extract_loco_line(block)
    in_sample_f1_ece = _extract_f1_ece(block)
    in_sample_f2_auc, f2_ci_lower, f2_ci_upper, f_rule_anomaly = _extract_f2(block)
    top_1_country, top_1_share = _extract_top_1_country(block)
    cohort_ece, zero_positive_cohort_flag = _extract_cohort_ece(block)
    per_recipe_ahi, per_recipe_ahi_reason = _extract_anchor_ahi(block)
    f_h_3_advisory_only = _extract_advisory_only(block)
    mechanism = _extract_mechanism(block)
    buyer_disclosure = _extract_buyer_disclosure(block)
    open_followups = _extract_open_followups(block)
    return {
        "recipe_id": recipe_id,
        "tier": tier,
        "architecture": architecture,
        "loco_auc": loco_auc,
        "n_pos_loco": n_pos_loco,
        "assignment_confidence": assignment_confidence,
        "in_sample_f1_ece": in_sample_f1_ece,
        "in_sample_f2_auc": in_sample_f2_auc,
        "in_sample_f2_ci_lower": f2_ci_lower,
        "in_sample_f2_ci_upper": f2_ci_upper,
        "top_1_training_country": top_1_country,
        "top_1_training_country_share": top_1_share,
        "cohort_ece": cohort_ece,
        "zero_positive_cohort_flag": zero_positive_cohort_flag,
        "per_recipe_anchor_ahi": per_recipe_ahi,
        "per_recipe_anchor_ahi_reason": per_recipe_ahi_reason,
        "f_h_3_advisory_only": f_h_3_advisory_only,
        "f_rule_anomaly": f_rule_anomaly,
        "mechanism_narrative": mechanism,
        "buyer_disclosure_recommendation": buyer_disclosure,
        "open_followups": open_followups,
    }


def extract_tear_sheets(paper_text: str) -> list[dict[str, Any]]:
    """Parse all 13 LOCKed recipe tear-sheets from the Stage 5 paper.

    Raises ValueError if the set of recipe IDs found does not exactly equal
    EXPECTED_LOCKED_RECIPES — this protects against silent paper edits that
    add or remove recipes without going through F-H-4 amendment discipline.
    """
    headers = list(RECIPE_HEADER_RE.finditer(paper_text))
    found_ids = {m.group("recipe_id") for m in headers}
    missing = EXPECTED_LOCKED_RECIPES - found_ids
    extra = found_ids - EXPECTED_LOCKED_RECIPES
    if missing or extra:
        raise ValueError(
            f"Recipe set mismatch vs EXPECTED_LOCKED_RECIPES post-KI-2.\n"
            f"  Missing (in expected, not in paper): {sorted(missing)}\n"
            f"  Extra   (in paper, not in expected): {sorted(extra)}\n"
            f"If the paper has been amended (e.g. new LOCK or FALSIFY), "
            f"EXPECTED_LOCKED_RECIPES in extract_tear_sheets.py must rotate "
            f"in the same PR as the amendment per F-H-4 discipline."
        )
    blocks = _split_into_blocks(paper_text)
    out: list[dict[str, Any]] = []
    for match in headers:
        rid = match.group("recipe_id")
        out.append(parse_recipe_block(rid, match, blocks[rid]))
    # Sort by recipe_id for deterministic output
    out.sort(key=lambda r: r["recipe_id"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paper",
        type=Path,
        required=True,
        help="Path to Stage 5 buyer-disclosure paper markdown",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write the structured tear-sheet JSON",
    )
    args = parser.parse_args()
    paper_text = args.paper.read_text(encoding="utf-8")
    recipes = extract_tear_sheets(paper_text)
    payload = {
        "schema_version": "1.0",
        "source_paper": args.paper.as_posix(),
        "n_recipes": len(recipes),
        "recipes": recipes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(recipes)} tear-sheets to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
