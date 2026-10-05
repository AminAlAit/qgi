"""Inspect TE sample-10 data shapes for contract-type authoring."""
import json
import sys
from pathlib import Path

ROOT = Path("data/te-sample-10")


def keys_of(d, depth=0):
    if isinstance(d, dict):
        return list(d.keys())
    return f"<{type(d).__name__}>"


def main():
    print("=== v3 card ===")
    with open(ROOT / "cards-v3" / "economic_nationalization.card.json") as f:
        card = json.load(f)
    print("top-level keys:", list(card.keys()))
    print()
    print("contract_version:", card.get("contract_version"))
    print("engine:", card.get("engine"))
    print("per_country_scores_pointer:", card.get("per_country_scores_pointer"))
    print()
    print("stats:", card.get("stats"))
    print()
    print("greedy_walk keys:", list(card.get("greedy_walk", {}).keys()))
    gw = card.get("greedy_walk", {})
    if gw.get("history"):
        print("  history[0]:", gw["history"][0])
    print()
    print("score_distribution keys:", list(card.get("score_distribution", {}).keys()))
    sd = card.get("score_distribution", {})
    print("  computed:", sd.get("computed"), "bins:", len(sd.get("histogram", [])))
    if sd.get("histogram"):
        print("  bin[0]:", sd["histogram"][0])
    print()
    print("indicator_sensitivity keys:", list(card.get("indicator_sensitivity", {}).keys()))
    isen = card.get("indicator_sensitivity", {})
    print("  computed:", isen.get("computed"), "loo len:", len(isen.get("leave_one_out", [])))
    if isen.get("leave_one_out"):
        print("  loo[0]:", isen["leave_one_out"][0])
    print()
    print("per_cohort keys:", list(card.get("per_cohort", {}).keys()))
    if card.get("per_cohort"):
        first_cohort_key = next(iter(card["per_cohort"]))
        print("  ", first_cohort_key, ":", card["per_cohort"][first_cohort_key])
    print()
    print("coverage_audit:", card.get("coverage_audit"))
    print("calibration:", card.get("calibration"))
    print("reliability_multipass:", card.get("reliability_multipass"))
    print("architecture:", card.get("architecture"))
    print("architecture_provenance keys:", list((card.get("architecture_provenance") or {}).keys()))
    print()

    print("=== scores file ===")
    with open(ROOT / "scores" / "economic_nationalization.scores.json") as f:
        scores = json.load(f)
    print("top-level keys:", list(scores.keys()))
    print("n_countries_scored:", scores.get("n_countries_scored"))
    print("train_auc:", scores.get("train_auc"))
    print("cv_auc_full:", scores.get("cv_auc_full"))
    if scores.get("scores"):
        first = scores["scores"][0]
        print()
        print("score entry keys:", list(first.keys()))
        print("  iso:", first.get("iso"))
        print("  name:", first.get("name"))
        print("  score:", first.get("score"), "rank:", first.get("rank"), "eval_year:", first.get("eval_year"))
        print("  in_evidence_base:", first.get("in_evidence_base"))
        print("  delta_vs_prior_vintage:", first.get("delta_vs_prior_vintage"))
        if first.get("shap_attribution"):
            print("  shap[0]:", first["shap_attribution"][0])
        if first.get("indicator_movement"):
            mv = first["indicator_movement"][0]
            print("  movement[0] keys:", list(mv.keys()))
            print("  movement[0] code:", mv.get("code"), "trajectory_len:", len(mv.get("trajectory_12q", [])))
            print("  movement[0] z_score_change:", mv.get("z_score_change"))
        if first.get("nearest_analogs"):
            print("  nearest_analogs[0]:", first["nearest_analogs"][0])
    print()

    print("=== country-index ===")
    with open(ROOT / "countries" / "country-index.json") as f:
        idx = json.load(f)
    print("top-level keys:", list(idx.keys()))
    print("platform_roster_size:", idx.get("platform_roster_size"))
    print("n_countries_scored:", idx.get("n_countries_scored"))
    print("compound_score_formula:", idx.get("compound_score_formula"))
    if idx.get("countries"):
        ce = idx["countries"][0]
        print()
        print("country entry keys:", list(ce.keys()))
        print("  name:", ce.get("name"))
        print("  region:", ce.get("region"))
        print("  recipes_lit_count:", ce.get("recipes_lit_count"))
        print("  lit_families:", ce.get("lit_families"))
        print("  compound_score:", ce.get("compound_score"))
        if ce.get("top_recipes"):
            print("  top_recipes[0]:", ce["top_recipes"][0])
        if ce.get("rank_history"):
            print("  rank_history[0]:", ce["rank_history"][0])
            print("  rank_history_notes:", ce.get("rank_history_notes"))
    print()

    print("=== analogs ===")
    with open(ROOT / "analogs" / "current-state-analogs.json") as f:
        an = json.load(f)
    print("top-level keys:", list(an.keys()))
    print("vintage:", an.get("vintage"))
    print("entries len:", len(an.get("entries", [])))
    if an.get("entries"):
        ee = an["entries"][0]
        print()
        print("analog entry keys:", list(ee.keys()))
        print("  name:", ee.get("name"), "region:", ee.get("region"))
        if ee.get("analogs"):
            print("  analogs[0]:", ee["analogs"][0])
        if ee.get("contributions"):
            print("  contributions[0]:", ee["contributions"][0])
    print()

    print("=== activity feed ===")
    with open(ROOT / "activity" / "program-feed.json") as f:
        feed = json.load(f)
    print("top-level keys:", list(feed.keys()))
    print("events len:", len(feed.get("events", [])))
    if feed.get("events"):
        print("  event[0]:", feed["events"][0])
        kinds = sorted({e.get("kind") for e in feed["events"]})
        print("  kinds present:", kinds)
    print()

    print("=== MANIFEST ===")
    with open(ROOT / "MANIFEST.json") as f:
        man = json.load(f)
    print("top-level keys:", list(man.keys()))
    if "recipes" in man:
        print("recipes len:", len(man["recipes"]))
        print("first recipe keys:", list(man["recipes"][0].keys()))


if __name__ == "__main__":
    main()
