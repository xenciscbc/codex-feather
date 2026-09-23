"""Query shared and sealed history through the public handoff command."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/handoff/scripts/handoff.py"


class HandoffHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.directory = self.project / ".feather/handoffs"

    def write(self, relative: str, content: str) -> Path:
        path = self.directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        return path

    def snapshot(self) -> dict[str, bytes]:
        return {path.relative_to(self.project).as_posix(): path.read_bytes()
                for path in self.project.rglob("*") if path.is_file()}

    def run_history(self, *arguments: str, expected: int = 0) -> dict:
        before = self.snapshot()
        result = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--project", str(self.project),
             "history", *arguments], capture_output=True, text=True,
            encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before, "History queries must be read-only")
        return json.loads(result.stdout)

    def test_filters_modern_entries_in_the_requested_timezone_and_preserves_crlf(self):
        first = ("## deploy · 完成：2026-09-10T23:30:00+00:00\r\n"
                 "更新：2026-09-11T07:30:00+08:00\r\n狀態：完成\r\n"
                 "## 詳細紀錄\r\nreadiness needle\r\n\r\n")
        second = ("## deploy · 完成：2026-09-11T23:30:00+00:00\r\n"
                  "更新：2026-09-12T07:30:00+08:00\r\n狀態：完成\r\nother\r\n")
        source = self.write("history.md", "# 交接歷史\r\n\r\n" + first + second)
        result = self.run_history("--work", "deploy", "--from-date", "2026-09-11",
                                  "--to-date", "2026-09-11", "--keyword", "needle",
                                  "--timezone", "+08:00")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["complete"])
        self.assertEqual(result["timezone"], "+08:00")
        self.assertEqual(len(result["entries"]), 1)
        entry = result["entries"][0]
        self.assertEqual(entry["title"], "deploy")
        self.assertEqual(entry["completed"], "2026-09-10T23:30:00+00:00")
        self.assertEqual(entry["source"], "history.md")
        self.assertEqual(entry["content"], first)
        self.assertTrue(entry["body"].startswith("更新："))
        self.assertIn("## 詳細紀錄\r\nreadiness needle", entry["body"])
        self.assertEqual(len(entry["id"]), 64)
        self.assertEqual(entry["document_version"], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_sealed_history_is_included_only_when_explicitly_requested(self):
        shared = ("# 交接歷史\n\n## deploy · 完成：2026-09-08T10:00:00+00:00\n"
                  "狀態：完成\nshared record\n")
        sealed = ("# 交接歷史\n\n## deploy · 完成：2026-09-09T10:00:00+00:00\n"
                  "狀態：完成\nsealed record\n")
        self.write("history.md", shared)
        self.write("archive/september.md", sealed)
        default = self.run_history("--work", "deploy")
        self.assertEqual([entry["source"] for entry in default["entries"]], ["history.md"])
        included = self.run_history("--work", "deploy", "--include-sealed")
        self.assertEqual([entry["source"] for entry in included["entries"]],
                         ["history.md", "archive/september.md"])
        self.assertNotEqual(included["entries"][0]["id"], included["entries"][1]["id"])

    def test_existing_empty_sealed_directory_is_a_complete_empty_query(self):
        (self.directory / "archive").mkdir(parents=True)
        result = self.run_history("--include-sealed")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["entries"], [])

    def test_legacy_records_remain_readable_without_claiming_clear_boundaries(self):
        content = "# history\n\n## previous\n狀態：完成\n進度：legacy evidence\n"
        self.write("history.md", content)
        result = self.run_history("--keyword", "legacy evidence", expected=2)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["entries"]), 1)
        entry = result["entries"][0]
        self.assertEqual(entry["title"], "previous")
        self.assertIsNone(entry["completed"])
        self.assertFalse(entry["boundary_known"])
        self.assertEqual(entry["content"], "## previous\n狀態：完成\n進度：legacy evidence\n")
        self.assertIn("ambiguous boundaries", " ".join(entry["problems"]))

    def test_legacy_completion_date_is_returned_with_a_timezone_ambiguity(self):
        self.write("history.md", "# history\n\n## previous\n完成：2026-09-07\nlegacy body\n")
        result = self.run_history("--work", "previous", expected=2)
        self.assertEqual(result["status"], "partial")
        entry = result["entries"][0]
        self.assertEqual(entry["completed"], "2026-09-07")
        self.assertTrue(entry["boundary_known"])
        self.assertIn("no timezone", " ".join(entry["problems"]))

    def test_possible_legacy_boundary_inside_modern_history_is_reported(self):
        content = ("# history\n\n## current · 完成：2026-09-08T10:00:00+00:00\ncurrent body\n"
                   "## possible-old\n狀態：完成\n進度：unknown boundary\n"
                   "## later · 完成：2026-09-09T10:00:00+00:00\nlater body\n")
        self.write("history.md", content)
        result = self.run_history(expected=2)
        self.assertEqual(result["status"], "partial")
        self.assertIn("possible-old", " ".join(issue["message"] for issue in result["issues"]))
        self.assertEqual([entry["title"] for entry in result["entries"]],
                         ["current", "possible-old", "later"])
        self.assertFalse(result["entries"][0]["boundary_known"])
        self.assertFalse(result["entries"][1]["boundary_known"])

    def test_missing_invalid_query_and_partial_source_failure_are_distinct(self):
        missing = self.run_history()
        self.assertEqual(missing["status"], "missing")
        self.assertTrue(missing["complete"])
        invalid = self.run_history("--timezone", "Mars/Olympus", expected=2)
        self.assertEqual(invalid["status"], "error")
        self.assertEqual(invalid["code"], "query")
        self.write("history.md", "# history\n\n## kept · 完成：2026-09-08T10:00:00+00:00\nkept body\n")
        (self.directory / "archive/broken.md").mkdir(parents=True)
        partial = self.run_history("--include-sealed", expected=2)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual([entry["title"] for entry in partial["entries"]], ["kept"])
        self.assertEqual(partial["issues"][0]["source"], "archive/broken.md")


if __name__ == "__main__":
    unittest.main()
