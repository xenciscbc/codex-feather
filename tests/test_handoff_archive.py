"""Archive completed handoffs through the public command."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/feather-handoff/scripts/handoff.py"
TITLE = "config-audit"
COMPLETED = "2026-09-11T10:00:00+08:00"
BODY = (f"更新：{COMPLETED}\r\n狀態：完成\r\n目標：核對設定\r\n"
        "進度：readiness 已核對。\r\n下一步：無\r\n\r\n## 詳細紀錄\r\n完整證據。\r\n").encode("utf-8")
WORK = b"\xef\xbb\xbf" + f"# {TITLE}\r\n".encode("utf-8") + BODY


class HandoffArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.directory = self.project / ".feather/handoffs"
        self.directory.mkdir(parents=True)
        self.work = self.directory / "config-audit.md"

    def run_archive(self, version: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--project", str(self.project),
             "archive", "--work", self.work.name],
            input=json.dumps({"version": version}), capture_output=True, text=True,
            encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def write_work(self, data: bytes = WORK) -> str:
        self.work.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def test_create_completed_work_archives_in_the_same_public_operation(self):
        payload = {"title": TITLE, "fields": {"updated": COMPLETED, "status": "完成",
                   "goal": "核對設定", "progress": "readiness 已核對。", "next": "無"},
                   "details": "完整證據。"}
        result = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--project", str(self.project),
             "create", "--work", self.work.name], input=json.dumps(payload, ensure_ascii=False),
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["archived"])
        self.assertTrue(report["history_appended"])
        self.assertFalse(self.work.exists())
        self.assertIn(f"## {TITLE} · 完成：{COMPLETED}\n".encode("utf-8"),
                      (self.directory / "history.md").read_bytes())

    def test_completion_identity_supports_a_delimiter_in_the_title(self):
        title = "release · 完成：candidate"
        version = self.write_work(WORK.replace(f"# {TITLE}".encode(), f"# {title}".encode(), 1))
        result = self.run_archive(version)
        self.assertEqual(result["title"], title)
        self.assertFalse(self.work.exists())

    def test_first_archive_preserves_history_and_exact_work_body_then_retry_is_idempotent(self):
        version = self.write_work()
        history = self.directory / "history.md"
        previous = (b"\xef\xbb\xbf# \xe4\xba\xa4\xe6\x8e\xa5\xe6\xad\xb7\xe5\x8f\xb2\n\n"
                    b"## config-audit \xc2\xb7 \xe5\xae\x8c\xe6\x88\x90\xef\xbc\x9a2026-09-10T00:00:00+00:00\nold\n")
        history.write_bytes(previous)
        archived = self.run_archive(version)
        marker = f"## {TITLE} · 完成：{COMPLETED}\n".encode("utf-8")
        expected = previous + marker + BODY
        self.assertEqual(history.read_bytes(), expected)
        self.assertFalse(self.work.exists())
        self.assertEqual(archived["status"], "ok")
        self.assertTrue(archived["history_appended"])
        self.assertEqual(archived["history_version"], hashlib.sha256(expected).hexdigest())

        retry_version = self.write_work()
        retried = self.run_archive(retry_version)
        self.assertFalse(self.work.exists())
        self.assertEqual(history.read_bytes(), expected)
        self.assertFalse(retried["history_appended"])
        self.assertEqual(retried["id"], archived["id"])

    def test_stale_version_and_same_identity_body_conflict_preserve_both_sources(self):
        version = self.write_work()
        before_work = self.work.read_bytes()
        stale = self.run_archive("0" * 64, expected=2)
        self.assertEqual(stale["code"], "conflict")
        self.assertEqual(self.work.read_bytes(), before_work)
        self.assertFalse((self.directory / "history.md").exists())

        history = self.directory / "history.md"
        history_data = (f"# 交接歷史\n\n## {TITLE} · 完成：{COMPLETED}\n"
                        "狀態：完成\ndifferent body\n").encode("utf-8")
        history.write_bytes(history_data)
        conflict = self.run_archive(version, expected=2)
        self.assertEqual(conflict["code"], "conflict")
        self.assertEqual(self.work.read_bytes(), before_work)
        self.assertEqual(history.read_bytes(), history_data)

    def test_same_identity_with_an_extra_newline_at_eof_is_a_body_conflict(self):
        body = (f"更新：{COMPLETED}\n狀態：完成\n目標：核對設定\n"
                "進度：完成\n下一步：無").encode("utf-8")
        work = f"# {TITLE}\n".encode("utf-8") + body
        version = self.write_work(work)
        history = self.directory / "history.md"
        history_data = (f"# 交接歷史\n\n## {TITLE} · 完成：{COMPLETED}\n".encode("utf-8")
                        + body + b"\n")
        history.write_bytes(history_data)
        result = self.run_archive(version, expected=2)
        self.assertEqual(result["code"], "conflict")
        self.assertEqual(self.work.read_bytes(), work)
        self.assertEqual(history.read_bytes(), history_data)

    def test_retry_accepts_only_the_separator_needed_for_a_following_entry(self):
        body = (f"更新：{COMPLETED}\n狀態：完成\n目標：核對設定\n"
                "進度：完成\n下一步：無").encode("utf-8")
        work = f"# {TITLE}\n".encode("utf-8") + body
        version = self.write_work(work)
        history = self.directory / "history.md"
        history_data = (f"# 交接歷史\n\n## {TITLE} · 完成：{COMPLETED}\n".encode("utf-8")
                        + body
                        + b"\n## later \xc2\xb7 \xe5\xae\x8c\xe6\x88\x90\xef\xbc\x9a2026-09-12T00:00:00+00:00\n"
                          b"later body\n")
        history.write_bytes(history_data)
        result = self.run_archive(version)
        self.assertFalse(result["history_appended"])
        self.assertFalse(self.work.exists())
        self.assertEqual(history.read_bytes(), history_data)

    def test_noncompleted_work_and_unrecognizable_history_are_preserved(self):
        active = WORK.replace("狀態：完成".encode(), "狀態：進行中".encode())
        version = self.write_work(active)
        result = self.run_archive(version, expected=2)
        self.assertEqual(result["code"], "completed")
        self.assertEqual(self.work.read_bytes(), active)

        self.work.write_bytes(WORK)
        malformed = b"# history\nunknown entry boundaries\n"
        (self.directory / "history.md").write_bytes(malformed)
        result = self.run_archive(hashlib.sha256(WORK).hexdigest(), expected=2)
        self.assertEqual(result["code"], "history-format")
        self.assertEqual(self.work.read_bytes(), WORK)
        self.assertEqual((self.directory / "history.md").read_bytes(), malformed)

    @unittest.skipUnless(os.name == "nt", "Windows sharing denial is platform-specific")
    def test_history_sharing_failure_preserves_work_and_reports_recovery_paths(self):
        version = self.write_work()
        history = self.directory / "history.md"
        original = b"# history\n"
        history.write_bytes(original)
        with history.open("rb") as held:
            result = self.run_archive(version, expected=2)
            self.assertFalse(held.closed)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["code"], "history-save-failed")
        self.assertEqual(result["recovery"], "retry-archive")
        self.assertEqual(Path(result["work_path"]), self.work)
        self.assertEqual(Path(result["history_path"]), history)
        self.assertEqual(self.work.read_bytes(), WORK)
        self.assertEqual(history.read_bytes(), original)
        retried = self.run_archive(version)
        self.assertTrue(retried["history_appended"])
        self.assertFalse(self.work.exists())

    @unittest.skipUnless(os.name == "nt", "Windows sharing denial is platform-specific")
    def test_delete_sharing_failure_leaves_a_retryable_single_history_entry(self):
        version = self.write_work()
        with self.work.open("rb") as held:
            result = self.run_archive(version, expected=2)
            self.assertFalse(held.closed)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["code"], "pending-removal")
        self.assertEqual(result["recovery"], "retry-archive")
        self.assertTrue(self.work.exists())
        saved = (self.directory / "history.md").read_bytes()
        retried = self.run_archive(version)
        self.assertFalse(retried["history_appended"])
        self.assertFalse(self.work.exists())
        self.assertEqual((self.directory / "history.md").read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
