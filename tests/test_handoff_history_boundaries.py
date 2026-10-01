"""Archived bodies with legacy-looking headings stay archivable, queryable and mutable."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/handoff/scripts/handoff.py"


class HandoffHistoryBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)

    def call(self, *args, payload=None, expected=0):
        result = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--project", str(self.project), "--exact-root", *args],
            input=json.dumps(payload) if payload is not None else None, capture_output=True,
            text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def complete(self, name, details):
        return self.call("create", "--work", name, payload={
            "title": name.removesuffix(".md"), "details": details,
            "fields": {"status": "完成", "goal": "g", "progress": "p", "next": "無"}})

    def test_completed_bodies_with_legacy_looking_lines_archive_and_mutate(self):
        for name, details in (("first.md", "完成：拆分 A、B 兩項"),
                              ("second.md", "## 附註\n狀態：完成\n其餘說明")):
            with self.subTest(work=name):
                result = self.complete(name, details)
                self.assertEqual((result["status"], result["archived"]), ("ok", True), result)
        history = self.call("history")
        self.assertEqual(history["status"], "ok", history)
        self.assertEqual([entry["title"] for entry in history["entries"]], ["first", "second"])
        self.assertIn("完成：拆分 A、B 兩項", history["entries"][0]["body"])

        ids = {entry["title"]: entry["id"] for entry in history["entries"]}
        sealed = self.call("seal", payload={"version": history["documents"][0]["version"],
                                             "ids": [ids["second"]], "destination": "batch.md"})
        self.assertEqual(sealed["status"], "ok", sealed)
        both = self.call("history", "--include-sealed")
        archive = next(d for d in both["documents"] if d["source"] == "archive/batch.md")
        sealed_ids = [e["id"] for e in both["entries"] if e["source"] == "archive/batch.md"]
        self.assertEqual(sealed_ids, [ids["second"]])
        cleared = self.call("clear", payload={"source": "archive/batch.md",
                                               "version": archive["version"], "ids": sealed_ids})
        self.assertEqual((cleared["status"], cleared["removed"]), ("ok", sealed_ids), cleared)
        self.assertEqual([e["title"] for e in self.call("history", "--include-sealed")["entries"]], ["first"])


if __name__ == "__main__":
    unittest.main()
