"""Public handoff commands against real, isolated project files."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/feather-handoff/scripts/handoff.py"
RECORD = ("# config-audit\n更新：2026-09-11T10:00:00+08:00\n狀態：進行中\n\n"
          "目標：核對設定\n進度：port=7319；readiness 待確認。\n下一步：核對 readiness\n"
          "注意：timeout 等待使用者決定。\n\n## 詳細紀錄\n人工證據保留。\n")


class HandoffToolTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.directory = self.project / ".feather/handoffs"

    def run_tool(self, *args, payload=None, expected=0):
        result = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--project", str(self.project), *args],
            input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def write_work(self, name="config-audit.md", content=RECORD):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / name
        path.write_bytes(content.encode("utf-8"))
        return path

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes()
                for p in self.project.rglob("*") if p.is_file()}

    def test_list_and_read_show_current_summary_without_writes(self):
        self.write_work()
        self.write_work("done.md", RECORD.replace("狀態：進行中", "狀態：完成"))
        self.write_work("history.md", "# 交接歷史\n")
        (self.directory / "archive").mkdir()
        (self.directory / "archive/old.md").write_text(RECORD, encoding="utf-8")
        before = self.snapshot()
        listed = self.run_tool("list")
        self.assertTrue(listed["complete"])
        self.assertEqual([item["work"] for item in listed["items"]], ["config-audit.md", "done.md"])
        self.assertEqual(listed["items"][0]["progress"], "port=7319；readiness 待確認。")
        self.assertEqual(listed["items"][1]["record_status"], "完成待歸檔")
        read = self.run_tool("read", "--work", "config-audit.md")
        self.assertEqual(read["content"], RECORD)
        self.assertEqual(len(read["version"]), 64)
        self.assertEqual(before, self.snapshot())

    def test_missing_empty_and_unsafe_work_names_are_distinct(self):
        self.assertEqual(self.run_tool("list")["status"], "missing")
        self.directory.mkdir(parents=True)
        empty = self.run_tool("list")
        self.assertEqual(empty["status"], "ok")
        self.assertEqual(empty["items"], [])
        self.write_work()
        for name in ["../outside.md", "history.md", "HISTORY.MD", "file.txt", "CON.md"]:
            with self.subTest(name=name):
                self.assertEqual(self.run_tool("read", "--work", name, expected=2)["code"], "unsafe-name")

    def test_ambiguous_record_is_not_reported_as_complete(self):
        self.write_work(content=RECORD.replace("目標：", "狀態：受阻\n目標："))
        result = self.run_tool("list", expected=2)
        self.assertFalse(result["complete"])
        self.assertEqual(result["issues"][0]["work"], "config-audit.md")

    def test_preamble_is_visible_as_format_problem_without_repair(self):
        path = self.write_work(content="manual preamble\n" + RECORD)
        before = path.read_bytes()
        result = self.run_tool("list", expected=2)
        self.assertEqual(result["items"][0]["record_status"], "格式待確認")
        self.assertEqual(path.read_bytes(), before)

    def test_partial_listing_keeps_legacy_and_readable_items_without_repair(self):
        self.write_work()
        self.write_work("old.md", "# old\n狀態：受阻\n進度：" + "等待資料。" * 100 + "\n")
        self.write_work("broken.md").write_bytes(b"\xff\xfe\xfa")
        before = self.snapshot()
        result = self.run_tool("list", expected=2)
        self.assertFalse(result["complete"])
        self.assertEqual([i["work"] for i in result["items"]], ["config-audit.md", "old.md"])
        old = result["items"][1]
        self.assertTrue(old["progress_truncated"])
        self.assertLessEqual(len(old["progress"]), 240)
        self.assertEqual(old["record_status"], "格式待確認")
        read = self.run_tool("read", "--work", "old.md", expected=2)
        self.assertIn("等待資料。" * 100, read["content"])
        self.assertEqual(before, self.snapshot())

    def test_create_summary_and_details_then_read_preserving_existing_work(self):
        self.write_work()
        payload = {"title": "new audit", "fields": {"goal": "Check TLS", "progress": "TLS pending.",
                   "next": "Read config", "notes": "Do not change timeout."},
                   "details": "Manual evidence\n\n### Config\nport=7319\n"}
        created = self.run_tool("create", "--work", "new.md", payload=payload)
        self.assertEqual(created["work"], "new.md")
        read = self.run_tool("read", "--work", "new.md")
        self.assertEqual(read["progress"], "TLS pending.")
        self.assertIn("## 詳細紀錄\nManual evidence", read["content"])
        self.assertIn("Do not change timeout.", read["content"])
        before = self.snapshot()
        error = self.run_tool("create", "--work", "new.md", payload=payload, expected=2)
        self.assertEqual(error["code"], "exists")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.run_tool("read", "--work", "config-audit.md")["content"], RECORD)

    def test_create_validates_before_writing_and_respects_git_tracking(self):
        payload = {"fields": {"goal": "Audit", "progress": "Port checked", "next": "Read readiness"}}
        invalid = {"fields": {**payload["fields"], "status": "done"}}
        self.run_tool("create", "--work", "bad.md", payload=invalid, expected=2)
        self.assertEqual(self.snapshot(), {})
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True, capture_output=True)
        ignore = self.project / ".gitignore"
        ignore.write_bytes(b"# Existing\n*.log\n")
        self.run_tool("create", "--work", "audit.md", payload=payload)
        self.assertEqual(ignore.read_text(), "# Existing\n*.log\n/.feather/handoffs/\n")
        self.run_tool("create", "--work", "tracked.md", payload={**payload, "tracking": "track"})
        self.assertEqual(ignore.read_text(), "# Existing\n*.log\n")
        index = subprocess.run(["git", "-c", f"safe.directory={self.project.as_posix()}", "-C",
                                str(self.project), "ls-files"], capture_output=True, check=True)
        self.assertEqual(index.stdout, b"")

    def test_legacy_update_requires_reviewed_replacement_for_multiline_field(self):
        legacy = RECORD.replace("進度：port=7319；readiness 待確認。", "進度：\n- port=7319\n- readiness 待確認")
        path = self.write_work(content=legacy)
        read = self.run_tool("read", "--work", path.name, expected=2)
        self.run_tool("update", "--work", path.name, payload={"version": read["version"],
                      "fields": {"progress": "Port checked."}}, expected=2)
        self.assertEqual(path.read_bytes(), legacy.encode())
        replacement = RECORD.replace("人工證據保留。", "人工證據保留。\n- port=7319\n- readiness 待確認")
        saved = self.run_tool("update", "--work", path.name, payload={"version": read["version"],
                              "replacement": replacement})
        self.assertEqual(saved["content"], replacement)

    def test_update_preserves_manual_text_and_rejects_stale_version(self):
        self.write_work()
        original = self.run_tool("read", "--work", "config-audit.md")
        updated = self.run_tool("update", "--work", "config-audit.md", payload={
            "version": original["version"], "fields": {"progress": "Readiness verified; tests not run."}})
        self.assertNotEqual(updated["version"], original["version"])
        self.assertIn("人工證據保留。", updated["content"])
        self.assertIn("timeout 等待使用者決定。", updated["content"])
        current = self.snapshot()
        conflict = self.run_tool("update", "--work", "config-audit.md", payload={
            "version": original["version"], "fields": {"next": "Discard new evidence"}}, expected=2)
        self.assertEqual(conflict["code"], "conflict")
        self.assertEqual(current, self.snapshot())
        final = self.run_tool("update", "--work", "config-audit.md", payload={
            "version": updated["version"], "fields": {"next": "Await timeout decision"}})
        self.assertEqual(final["next"], "Await timeout decision")


if __name__ == "__main__":
    unittest.main()
