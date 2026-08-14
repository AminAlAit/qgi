"""Unit tests for build_recipe_manifest #962 sizing (size_tier, count_countries,
build_runnable_jobs, build_manifest)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_recipe_manifest as m  # noqa: E402


def test_size_tier_boundaries():
    assert m.size_tier(59) == {"tier": "small", "vcpu": 4, "batch_size": 5}
    assert m.size_tier(60) == {"tier": "medium", "vcpu": 8, "batch_size": 3}
    assert m.size_tier(99) == {"tier": "medium", "vcpu": 8, "batch_size": 3}
    assert m.size_tier(100) == {"tier": "fat", "vcpu": 16, "batch_size": 1}
    assert m.size_tier(141)["tier"] == "fat"


def _csv(tmp, recipe, countries):
    d = tmp / recipe
    d.mkdir(parents=True, exist_ok=True)
    rows = ["country_id,event_year"] + [f"{c},20{i:02d}" for i, c in enumerate(countries)]
    (d / "positives.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return d


def test_count_countries_distinct(tmp_path):
    _csv(tmp_path, "r", ["a", "b", "a", "c", "b"])  # 5 rows, 3 distinct
    assert m.count_countries(tmp_path / "r" / "positives.csv") == 3
    assert m.count_positives(tmp_path / "r" / "positives.csv") == 5


def test_build_runnable_jobs_groups_by_tier_and_batch():
    runnable = [
        {"recipe_id": "fat1", "n_pos": 800, "n_countries": 140, "size": m.size_tier(140)},
        {"recipe_id": "fat2", "n_pos": 500, "n_countries": 130, "size": m.size_tier(130)},
        {"recipe_id": "med1", "n_pos": 200, "n_countries": 80, "size": m.size_tier(80)},
        {"recipe_id": "sm1", "n_pos": 70, "n_countries": 30, "size": m.size_tier(30)},
        {"recipe_id": "sm2", "n_pos": 65, "n_countries": 25, "size": m.size_tier(25)},
    ]
    jobs = m.build_runnable_jobs(runnable)
    fat = [j for j in jobs if j["tier"] == "fat"]
    small = [j for j in jobs if j["tier"] == "small"]
    assert len(fat) == 2 and all(j["vcpu"] == 16 and j["n_recipes"] == 1 for j in fat)  # batch=1
    assert len(small) == 1 and small[0]["vcpu"] == 4  # 2 small recipes ≤ batch 5 → one job
    assert set(small[0]["recipe_ids"].split(",")) == {"sm1", "sm2"}
    assert all("max_countries" in j for j in jobs)


def test_build_manifest_derives_consistent_recipes_and_jobs(tmp_path):
    _csv(tmp_path, "fat", [f"c{i}" for i in range(120)])   # 120 ctry → fat, n_pos 120
    _csv(tmp_path, "small", [f"c{i}" for i in range(40)])  # 40 ctry → small, n_pos 40 (thin!)
    _csv(tmp_path, "smallrun", [f"c{i}" for i in range(80)] * 1)  # 80 rows... build below
    # Make smallrun runnable (>=60 pos) but small (<60 countries): 70 rows over 30 countries
    _csv(tmp_path, "smallrun", [f"c{i % 30}" for i in range(70)])
    man = m.build_manifest(tmp_path)
    # runnable = fat (120 pos) + smallrun (70 pos); small (40 pos) is THIN (<60), not runnable
    ids = {j["recipe_ids"] for j in man["runnable_jobs"]}
    assert "fat" in ",".join(ids) and "smallrun" in ",".join(ids)
    # runnable_recipes must be derived from the same jobs (consistent)
    assert man["runnable_recipes"] == [j["recipe_ids"] for j in man["runnable_jobs"]]
    # fat recipe → its own 16-vCPU job
    fatjob = [j for j in man["runnable_jobs"] if "fat" in j["recipe_ids"]][0]
    assert fatjob["vcpu"] == 16 and fatjob["tier"] == "fat"
    # no recipe dropped or duplicated across jobs (fan-out coverage guarantee)
    assert sum(j["n_recipes"] for j in man["runnable_jobs"]) == man["counts"]["runnable"]
    all_ids = [rid for j in man["runnable_jobs"] for rid in j["recipe_ids"].split(",")]
    assert len(all_ids) == len(set(all_ids)) == man["counts"]["runnable"]


def test_count_countries_empty_and_header_only(tmp_path):
    (tmp_path / "empty.csv").write_text("", encoding="utf-8")
    assert m.count_countries(tmp_path / "empty.csv") == 0
    (tmp_path / "hdr.csv").write_text("country_id,event_year\n", encoding="utf-8")
    assert m.count_countries(tmp_path / "hdr.csv") == 0
