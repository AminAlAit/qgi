"""Unit tests for append-cross-vintage-rank-history.py.

Runnable via: `python -m unittest scripts.test_append_cross_vintage_rank_history`
or `python scripts/test_append_cross_vintage_rank_history.py`.

Uses stdlib unittest only — qgi-frontend has no pytest configuration; this
keeps the test runnable in the GHA workflow's sync step as a smoke check
without adding a Python dev dependency to the frontend.
"""
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

# Module is named with hyphens (workflow-friendly) — load via importlib
_MODULE = pathlib.Path(__file__).parent / "append-cross-vintage-rank-history.py"
_spec = importlib.util.spec_from_file_location("appender", _MODULE)
appender = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(appender)


class TestAppendRankHistory(unittest.TestCase):

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_per_vintage(self, vintage: str, rows: list) -> pathlib.Path:
        p = self.tmp / "per-vintage.json"
        p.write_text(json.dumps({"vintage": vintage, "rows": rows}),
                     encoding="utf-8")
        return p

    def test_seed_new_cross_file(self):
        per = self._write_per_vintage("v1", [{"vintage": "v1", "country": "Iran"}])
        cross = self.tmp / "cross.json"
        rc = appender.append_rank_history("v1-slug", per, cross)
        self.assertEqual(rc, 0)
        doc = json.loads(cross.read_text(encoding="utf-8"))
        self.assertEqual(doc["n_rows"], 1)
        self.assertEqual(doc["n_vintages"], 1)
        self.assertEqual(doc["rows"][0]["country"], "Iran")

    def test_append_preserves_prior_vintage(self):
        per1 = self._write_per_vintage("v1", [{"vintage": "v1", "country": "Iran"}])
        cross = self.tmp / "cross.json"
        appender.append_rank_history("v1", per1, cross)

        per2 = self._write_per_vintage("v2", [{"vintage": "v2", "country": "Yemen"}])
        rc = appender.append_rank_history("v2", per2, cross)
        self.assertEqual(rc, 0)
        doc = json.loads(cross.read_text(encoding="utf-8"))
        self.assertEqual(doc["n_rows"], 2)
        self.assertEqual(doc["n_vintages"], 2)
        countries = sorted(r["country"] for r in doc["rows"])
        self.assertEqual(countries, ["Iran", "Yemen"])

    def test_rerun_same_vintage_is_idempotent(self):
        per1 = self._write_per_vintage("v1", [{"vintage": "v1", "country": "Iran"}])
        cross = self.tmp / "cross.json"
        appender.append_rank_history("v1", per1, cross)

        per1_rerun = self._write_per_vintage(
            "v1", [{"vintage": "v1", "country": "Iran"}, {"vintage": "v1", "country": "Egypt"}],
        )
        rc = appender.append_rank_history("v1", per1_rerun, cross)
        self.assertEqual(rc, 0)
        doc = json.loads(cross.read_text(encoding="utf-8"))
        # v1's old 1 row gone; replaced with 2 new v1 rows
        self.assertEqual(doc["n_rows"], 2)
        self.assertEqual(doc["n_vintages"], 1)

    def test_rerun_same_vintage_preserves_others(self):
        per1 = self._write_per_vintage("v1", [{"vintage": "v1", "country": "Iran"}])
        per2 = self._write_per_vintage("v2", [{"vintage": "v2", "country": "Yemen"}])
        cross = self.tmp / "cross.json"
        appender.append_rank_history("v1", per1, cross)
        appender.append_rank_history("v2", per2, cross)

        per1_rerun = self._write_per_vintage(
            "v1", [{"vintage": "v1", "country": "Egypt"}],
        )
        rc = appender.append_rank_history("v1", per1_rerun, cross)
        self.assertEqual(rc, 0)
        doc = json.loads(cross.read_text(encoding="utf-8"))
        self.assertEqual(doc["n_rows"], 2)  # v1 (1 row, replaced) + v2 (1 row, survived)
        self.assertEqual(doc["n_vintages"], 2)

    def test_missing_per_vintage_is_noop(self):
        missing = self.tmp / "doesnt-exist.json"
        cross = self.tmp / "cross.json"
        rc = appender.append_rank_history("v1", missing, cross)
        self.assertEqual(rc, 0)
        self.assertFalse(cross.exists())

    def test_missing_vintage_field_returns_2(self):
        per = self.tmp / "per.json"
        per.write_text(json.dumps({"rows": [{"country": "Iran"}]}),
                       encoding="utf-8")
        cross = self.tmp / "cross.json"
        rc = appender.append_rank_history("v1", per, cross)
        self.assertEqual(rc, 2)

    def test_utf8_roundtrip(self):
        per = self._write_per_vintage(
            "v1", [{"vintage": "v1", "country": "Côte d'Ivoire", "flag": "🇨🇮"}],
        )
        cross = self.tmp / "cross.json"
        appender.append_rank_history("v1", per, cross)
        doc = json.loads(cross.read_text(encoding="utf-8"))
        self.assertEqual(doc["rows"][0]["country"], "Côte d'Ivoire")
        self.assertEqual(doc["rows"][0]["flag"], "🇨🇮")

    def test_creates_cross_path_parent_dir(self):
        per = self._write_per_vintage("v1", [{"vintage": "v1"}])
        cross = self.tmp / "nested" / "dir" / "cross.json"
        rc = appender.append_rank_history("v1", per, cross)
        self.assertEqual(rc, 0)
        self.assertTrue(cross.exists())


class TestMainCli(unittest.TestCase):
    """QA round 2 N8 — cover the main() wrapper, not just the core."""

    def test_main_empty_slug_returns_2(self):
        """If neither --slug nor VINTAGE_SLUG is set, main() exits 2."""
        import os
        original_slug = os.environ.pop("VINTAGE_SLUG", None)
        original_argv = sys.argv
        try:
            sys.argv = ["append.py"]  # no --slug
            rc = appender.main()
            self.assertEqual(rc, 2)
        finally:
            if original_slug is not None:
                os.environ["VINTAGE_SLUG"] = original_slug
            sys.argv = original_argv

    def test_main_uses_env_var_for_slug(self):
        """VINTAGE_SLUG env var is the default for --slug."""
        import os
        original_slug = os.environ.get("VINTAGE_SLUG")
        original_argv = sys.argv
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            # Set env var; pass --per-vintage (missing file → noop, rc=0)
            os.environ["VINTAGE_SLUG"] = "test-slug"
            sys.argv = [
                "append.py",
                "--per-vintage", str(tmp / "missing.json"),
                "--cross", str(tmp / "cross.json"),
            ]
            rc = appender.main()
            self.assertEqual(rc, 0)  # missing file = noop
        finally:
            if original_slug is not None:
                os.environ["VINTAGE_SLUG"] = original_slug
            else:
                os.environ.pop("VINTAGE_SLUG", None)
            sys.argv = original_argv
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
