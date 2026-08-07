"""
summarize_gamma_sensitivity.py — aggregate the γ-stage sensitivity sweep
into a single decision-support table.

Phase 5 v0.2 charter §γ requires re-running validate_weight_matrix.py
once per (arm × strata_threshold) combination across:
    arms       = {A, B, C, D}
    thresholds = {3, 5, 7, 10, 15}
That produces 4 × 5 = 20 per-arm output JSONs. Each per-arm JSON's
`stratum_sensitivity` block already enumerates ALL 5 thresholds in one
pass (because the sweep is cheap once the scoring + AUC pipeline has
run), so the practical artifact this script needs is the 4 per-arm
JSONs each at its DEFAULT threshold — the sensitivity entries inside
each one carry the per-threshold rows.

Hard contract: the script does NOT make any decisions. The γ-stage
decision-gate is bound to Miriam's N=30 hard floor (Phase 5 v0.2 charter
§γ.gate, lines 192-199) — the sweep table is a TRANSPARENCY artifact for
the Majles convening, not a routing artifact. This script's job is to
make the artifact legible: read the 4 per-arm JSONs, pull the
`stratum_sensitivity` blocks, and emit a flat table.

# THROWAWAY in spirit (one-shot summarizer used during the γ Majles
# convening) but committed and re-runnable: rerun whenever the
# underlying per-arm γ JSONs change.

Determinism: pure-function aggregator over deterministic inputs.

Usage:
  python qgi-ml/scripts/summarize_gamma_sensitivity.py \\
      --arm-a qgi-data/reference/phase4-validation-armA.json \\
      --arm-b qgi-data/reference/phase4-validation-armB.json \\
      --arm-c qgi-data/reference/phase4-validation-armC.json \\
      --arm-d qgi-data/reference/phase4-validation-armD.json \\
      --out qgi-data/reference/gamma-sensitivity-summary.json

Output JSON schema:
  {
    "schema_version": 1,
    "generated": "<isoformat utc>",
    "input_arm_files": {"A": "...", "B": "...", "C": "...", "D": "..."},
    "thresholds_swept": [3, 5, 7, 10, 15],
    "table": [
      {
        "threshold": 3,
        "arm_A": {"n_cells": ..., "n_categories": ..., "mean_auc": ..., "median_auc": ...},
        "arm_B": {...}, "arm_C": {...}, "arm_D": {...},
        "a_minus_d_mean_auc": <float | null>,
      },
      ...
    ],
    "n30_floor_breach_by_threshold": {
      "3": {"any_arm_below_n30": bool, "arms_below": [...]},
      ...
    }
  }
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
N30_FLOOR = 30
THRESHOLDS = (3, 5, 7, 10, 15)


def _load_arm(path: Path) -> dict:
    """Read a per-arm validation JSON and extract its stratum_sensitivity
    block keyed by threshold. Fail loudly if the file is from a pre-v5
    run that lacks the block."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if "stratum_sensitivity" not in data:
        raise ValueError(
            f"{path} lacks 'stratum_sensitivity' — this script requires "
            f"per-arm JSONs produced by validate_weight_matrix.py v5 or "
            f"later (T2 / #666). Re-run the γ stage on the v5 script."
        )
    sens = data["stratum_sensitivity"]
    by_threshold = {entry["threshold"]: entry for entry in sens["entries"]}
    return {
        "ablation_arm": data.get("ablation_arm"),
        "by_threshold": by_threshold,
    }


def build_table(arms: dict[str, dict]) -> dict:
    """Build the cross-arm sensitivity table.

    Args:
      arms: {"A": <loaded arm dict>, "B": ..., "C": ..., "D": ...}

    Returns the full summary dict matching the module docstring schema,
    EXCEPT for `input_arm_files` which `main()` enriches afterwards
    (since this function does not know the input paths). Direct callers
    of `build_table` (e.g. unit tests) will not see `input_arm_files` in
    the result; the full documented schema is only guaranteed from
    `main()` output. PR #56 review fix 3 (NIT).
    """
    table = []
    n30_breach = {}
    for t in THRESHOLDS:
        row = {"threshold": t}
        # PR #56 review fix 2: keep "data missing" and "n<30 breach" as
        # SEPARATE conditions — conflating them in `arms_below` corrupts
        # the Majles artifact when a per-arm JSON happens to omit a row
        # (a configuration error, NOT an N=30 breach).
        arms_data_missing: list[str] = []
        arms_below_n30: list[str] = []
        for arm_label, arm in arms.items():
            entry = arm["by_threshold"].get(t)
            if entry is None:
                row[f"arm_{arm_label}"] = None
                arms_data_missing.append(arm_label)
                continue
            row[f"arm_{arm_label}"] = {
                "n_cells": entry["n_cells"],
                "n_categories": entry["n_categories"],
                "mean_auc": entry["mean_auc"],
                "median_auc": entry["median_auc"],
            }
            if entry["n_cells"] < N30_FLOOR:
                arms_below_n30.append(arm_label)

        # A - D mean-AUC swing per threshold — the v0.1a 0.0077 number's
        # γ-stage analogue. Computed only when both endpoints are real.
        arm_a = row.get("arm_A")
        arm_d = row.get("arm_D")
        if (arm_a is not None and arm_d is not None
                and arm_a["mean_auc"] is not None
                and arm_d["mean_auc"] is not None):
            try:
                row["a_minus_d_mean_auc"] = (
                    float(arm_a["mean_auc"]) - float(arm_d["mean_auc"])
                )
            except (TypeError, ValueError):
                row["a_minus_d_mean_auc"] = None
        else:
            row["a_minus_d_mean_auc"] = None

        table.append(row)
        n30_breach[str(t)] = {
            "any_arm_below_n30": len(arms_below_n30) > 0,
            "arms_below_n30": arms_below_n30,
            "any_arm_data_missing": len(arms_data_missing) > 0,
            "arms_data_missing": arms_data_missing,
            # Back-compat alias for any downstream caller that still reads
            # the pre-review key. Equals arms_below_n30 (NOT a union with
            # arms_data_missing — that conflation is exactly what PR #56
            # review fix 2 corrects).
            "arms_below": arms_below_n30,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated": datetime.now(timezone.utc).isoformat(),
        "thresholds_swept": list(THRESHOLDS),
        "table": table,
        "n30_floor_breach_by_threshold": n30_breach,
        "n30_floor_note": (
            "N=30 is Miriam's hard floor per Phase 5 v0.2 charter A4. "
            "This summary records WHICH thresholds × arms fall below it, "
            "but does NOT make a routing decision; γ-stage decision-gate "
            "logic is the Majles convening's responsibility (charter §γ.gate)."
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--arm-a", required=True, type=Path,
                   help="Path to phase4-validation-armA.json (signed × #591 filter)")
    p.add_argument("--arm-b", required=True, type=Path,
                   help="Path to phase4-validation-armB.json (signed × no filter)")
    p.add_argument("--arm-c", required=True, type=Path,
                   help="Path to phase4-validation-armC.json (unsigned × #591 filter)")
    p.add_argument("--arm-d", required=True, type=Path,
                   help="Path to phase4-validation-armD.json (unsigned × no filter)")
    p.add_argument("--out", required=True, type=Path,
                   help="Path to write the summary JSON")
    args = p.parse_args()

    arms = {
        "A": _load_arm(args.arm_a),
        "B": _load_arm(args.arm_b),
        "C": _load_arm(args.arm_c),
        "D": _load_arm(args.arm_d),
    }
    summary = build_table(arms)
    summary["input_arm_files"] = {
        "A": str(args.arm_a),
        "B": str(args.arm_b),
        "C": str(args.arm_c),
        "D": str(args.arm_d),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote γ sensitivity summary → {args.out}")

    # Stdout breadcrumb so the Majles convening reads the salient bits
    # without opening the JSON.
    print()
    print("=== γ sensitivity (mean AUC by threshold × arm) ===")
    print("  threshold | A         B         C         D         A-D")
    for row in summary["table"]:
        cells = []
        for label in ("A", "B", "C", "D"):
            arm = row.get(f"arm_{label}")
            if arm is None or arm["mean_auc"] is None:
                cells.append("      .  ")
            else:
                cells.append(f"  {arm['mean_auc']:7.4f}")
        delta = row["a_minus_d_mean_auc"]
        delta_str = "    .  " if delta is None else f"  {delta:+7.4f}"
        print(f"  {row['threshold']:>9d} |{''.join(cells)}{delta_str}")
    breaches = [
        f"t={t} (arms {','.join(info['arms_below_n30'])})"
        for t, info in summary["n30_floor_breach_by_threshold"].items()
        if info["any_arm_below_n30"]
    ]
    if breaches:
        print(f"  N=30 floor breaches: {'; '.join(breaches)}")
    else:
        print("  N=30 floor breaches: none")
    missing = [
        f"t={t} (arms {','.join(info['arms_data_missing'])})"
        for t, info in summary["n30_floor_breach_by_threshold"].items()
        if info["any_arm_data_missing"]
    ]
    if missing:
        print(f"  data-missing rows: {'; '.join(missing)}")


if __name__ == "__main__":
    main()
