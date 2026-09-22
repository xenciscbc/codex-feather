"""Source drift, bounded I/O and preservation through the public handoff CLI."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_handoff_tool as handoff_tests
RECORD = handoff_tests.RECORD

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/feather-handoff/scripts"))
from feather_handoff import baseline, observations
from feather_handoff.storage import HandoffError, Store


class HandoffSnapshotsTest(unittest.TestCase):
    setUp = handoff_tests.HandoffToolTest.setUp
    run_tool = handoff_tests.HandoffToolTest.run_tool
    write_work = handoff_tests.HandoffToolTest.write_work
    tree = handoff_tests.HandoffToolTest.snapshot

    def source(self, name="a.py", data=b"original\r\n"):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def capture(self, paths=None, expected=0):
        return self.run_tool("snapshot", payload={"paths": paths or ["a.py"]}, expected=expected)["snapshot"]

    def create(self, value=None, **extra):
        return self.run_tool("create", "--work", "w.md", payload={
            "fields": {"goal": "check", "progress": "observed", "next": "verify"},
            **({"snapshot": value} if value is not None else {}), **extra})

    def test_capture_compare_and_progress_update_keep_original_evidence(self):
        source = self.source()
        before = self.tree()
        value = self.capture(["a.py", "missing.json"])
        self.assertEqual(before, self.tree())
        self.assertEqual(value["files"][0]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        saved = self.create(value)
        before = self.tree()
        compared = self.run_tool("compare", "--work", "w.md")
        self.assertEqual([item["comparison"] for item in compared["files"]], ["unchanged", "unchanged"])
        self.assertEqual(before, self.tree())
        source.write_bytes(b"changed")
        self.source("missing.json", b"created")
        compared = self.run_tool("compare", "--work", "w.md")
        self.assertEqual([item["comparison"] for item in compared["files"]], ["changed", "created"])
        updated = self.run_tool("update", "--work", "w.md", payload={"version": saved["version"], "fields": {"progress": "need review"}})
        self.assertEqual(baseline.parse(updated["content"]), value)
        source.unlink()
        self.assertEqual(self.run_tool("compare", "--work", "w.md")["files"][0]["comparison"], "missing")

    def test_stale_or_invalid_snapshot_never_writes(self):
        source = self.source()
        value = self.capture()
        source.write_bytes(b"later")
        before = self.tree()
        payload = {"fields": {"goal": "a", "progress": "b", "next": "c"}, "snapshot": value}
        result = self.run_tool("create", "--work", "w.md", payload=payload, expected=2)
        self.assertEqual(result["code"], "snapshot-conflict")
        self.assertEqual(before, self.tree())
        payload["snapshot"] = None
        self.run_tool("create", "--work", "w.md", payload=payload, expected=2)
        self.assertEqual(before, self.tree())

    def test_explicit_refresh_checks_version_and_preserves_manual_sections(self):
        source = self.source()
        saved = self.create(self.capture())
        path = self.directory / "w.md"
        path.write_bytes(b"\xef\xbb\xbf" + (saved["content"] + "\n## Manual\nkeep\n").replace("\n", "\r\n").encode())
        current = self.run_tool("read", "--work", "w.md")
        source.write_bytes(b"later")
        value = self.capture()
        before = path.read_bytes()
        self.run_tool("update", "--work", "w.md", payload={"version": saved["version"], "snapshot": value}, expected=2)
        self.assertEqual(path.read_bytes(), before)
        updated = self.run_tool("update", "--work", "w.md", payload={"version": current["version"], "snapshot": value,
                               "details": "```text\n## 檔案基準\nexample\n```"})
        self.assertEqual(baseline.parse(updated["content"]), value)
        self.assertIn("## Manual\r\nkeep\r\n", updated["content"])
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.run_tool("update", "--work", "w.md", payload={"version": updated["version"], "details": "new evidence"})
        self.assertEqual(baseline.parse(path.read_text(encoding="utf-8-sig")), value)

    def test_unclosed_details_fence_rejects_snapshot_without_writes(self):
        self.source()
        value = self.capture()
        fields = {"goal": "check", "progress": "observed", "next": "verify"}
        for fence in ["```python", "~~~~text", "   ````"]:
            with self.subTest(fence=fence):
                before = self.tree()
                result = self.run_tool("create", "--work", "w.md", expected=2,
                                       payload={"fields": fields, "details": fence + "\nexample", "snapshot": value})
                self.assertEqual(result["code"], "snapshot-format")
                self.assertEqual(self.tree(), before)
        saved = self.create(details="```python\nexample")
        before = self.tree()
        result = self.run_tool("update", "--work", "w.md", expected=2,
                               payload={"version": saved["version"], "snapshot": value})
        self.assertEqual(result["code"], "snapshot-format")
        self.assertEqual(self.tree(), before)
        repaired = self.run_tool("update", "--work", "w.md",
                                 payload={"version": saved["version"], "details": "```python\nexample\n```", "snapshot": value})
        self.assertEqual(baseline.parse(repaired["content"]), value)
        self.assertTrue(self.run_tool("compare", "--work", "w.md")["complete"])

    def test_absent_invalid_and_archived_work_are_distinct(self):
        path = self.write_work("w.md")
        self.assertEqual(self.run_tool("compare", "--work", "w.md")["baseline_state"], "absent")
        path.write_text(RECORD + "\n## 檔案基準\n```json\n{bad}\n```\n", encoding="utf-8")
        before = self.tree()
        self.assertEqual(self.run_tool("compare", "--work", "w.md", expected=2)["baseline_state"], "invalid")
        self.assertEqual(self.run_tool("list", expected=2)["items"][0]["snapshot_state"], "invalid")
        self.assertEqual(before, self.tree())
        self.assertEqual(self.run_tool("compare", "--work", "absent.md", expected=2)["status"], "missing")

    def test_completion_retry_and_seal_preserve_baseline(self):
        self.source()
        value = self.capture()
        saved = self.create(value)
        self.run_tool("update", "--work", "w.md", payload={"version": saved["version"], "fields": {"status": "完成"},
                      "defer_history": True}, expected=2)
        current = self.run_tool("read", "--work", "w.md")
        self.assertTrue(self.run_tool("compare", "--work", "w.md")["complete"])
        self.run_tool("archive", "--work", "w.md", payload={"version": current["version"]})
        self.assertEqual(self.run_tool("compare", "--work", "w.md", expected=2)["status"], "missing")
        history = self.run_tool("history")
        source = (self.directory / "history.md").read_text(encoding="utf-8")
        self.assertEqual(baseline.parse(source), value)
        doc = history["documents"][0]
        self.run_tool("seal", payload={"version": doc["version"], "ids": [history["entries"][0]["id"]], "destination": "batch.md"})
        self.assertEqual(baseline.parse((self.directory / "archive/batch.md").read_text(encoding="utf-8")), value)

    def test_partial_unknown_is_retained_and_cannot_become_unchanged(self):
        self.source()
        value = self.capture()
        value["files"][0] = {"path": "a.py", "state": "unknown", "reason": "unreadable"}
        self.create(value)
        result = self.run_tool("compare", "--work", "w.md", expected=2)
        self.assertEqual(result["files"][0]["comparison"], "unknown")
        self.assertFalse(result["complete"])

    def test_invalid_section_cannot_be_overwritten_by_partial_update(self):
        self.source()
        saved = self.create(self.capture())
        path = self.directory / "w.md"
        invalid = saved["content"].replace('"schema_version": 1', '"schema_version": 42')
        path.write_text(invalid, encoding="utf-8")
        current = self.run_tool("read", "--work", "w.md", expected=2)
        before = path.read_bytes()
        self.run_tool("update", "--work", "w.md", payload={"version": current["version"], "fields": {"progress": "new"}}, expected=2)
        self.assertEqual(path.read_bytes(), before)
        repaired = self.run_tool("update", "--work", "w.md", payload={"version": current["version"], "replacement": saved["content"]})
        self.assertEqual(repaired["snapshot_state"], "available")

    def test_replacement_cannot_smuggle_a_stale_baseline(self):
        self.source()
        value = self.capture()
        saved = self.create()
        self.source(data=b"changed")
        before = self.tree()
        replacement = baseline.put(saved["content"], value)
        self.run_tool("update", "--work", "w.md", payload={"version": saved["version"], "replacement": replacement}, expected=2)
        self.assertEqual(self.tree(), before)

    def test_details_and_snapshot_cannot_silently_replace_user_content(self):
        self.source()
        saved = self.create()
        before = self.tree()
        self.run_tool("update", "--work", "w.md", expected=2, payload={"version": saved["version"],
                      "snapshot": self.capture(), "details": "notes\n## 檔案基準\nkeep this evidence"})
        self.assertEqual(self.tree(), before)

    def test_links_directories_and_limits_are_partial_without_reads(self):
        self.source()
        os.link(self.project / "a.py", self.project / "hard.py")
        (self.project / "directory").mkdir()
        result = self.run_tool("snapshot", payload={"paths": ["hard.py", "directory", "missing"]}, expected=2)
        states = {item["path"]: item["state"] for item in result["snapshot"]["files"]}
        self.assertEqual(states, {"hard.py": "unknown", "directory": "unknown", "missing": "missing"})
        for paths in [["../outside"], ["a.py", "a.py"], [".git/config"], [".feather/handoffs/w.md"], []]:
            self.run_tool("snapshot", payload={"paths": paths}, expected=2)

    def test_symlink_is_never_followed(self):
        outside = self.source("target")
        try:
            (self.project / "alias").symlink_to(outside)
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        result = self.run_tool("snapshot", payload={"paths": ["alias"]}, expected=2)
        self.assertEqual(result["snapshot"]["files"][0]["reason"], "unsafe-path")

    def test_git_unborn_detached_branch_and_uncommitted_changes(self):
        def git(*args):
            result = subprocess.run(["git", "-C", str(self.project), *args], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()
        git("init", "--initial-branch=main")
        value = self.run_tool("snapshot", payload={"paths": ["a.py"]})["snapshot"]
        self.assertIsNone(value["git"]["head"])
        self.assertEqual(value["git"]["branch"], "main")
        self.source()
        git("add", "a.py")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture")
        value = self.capture()
        self.create(value)
        self.source(data=b"uncommitted")
        index = (self.project / ".git/index").read_bytes()
        result = self.run_tool("compare", "--work", "w.md")
        self.assertEqual(result["git"]["comparison"], "unchanged")
        self.assertEqual(result["files"][0]["comparison"], "changed")
        self.assertEqual((self.project / ".git/index").read_bytes(), index)
        git("checkout", "--detach")
        result = self.run_tool("compare", "--work", "w.md")
        self.assertEqual(result["git"]["comparison"], "changed")
        self.assertIsNone(result["git"]["current_observation"]["branch"])


class ObservationUnitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.store = SimpleNamespace(project=self.project)

    def test_full_observation_matrix(self):
        examples = {"present": {"state": "present", "sha256": "a"}, "missing": {"state": "missing"},
                    "unknown": {"state": "unknown", "reason": "unreadable"}}
        expected = [["unchanged", "missing", "unknown"], ["created", "unchanged", "unknown"],
                    ["unknown", "unknown", "unknown"]]
        for i, before in enumerate(examples.values()):
            for j, after in enumerate(examples.values()):
                self.assertEqual(observations.difference(before, after), expected[i][j])

    def test_bounded_read_and_total_budget(self):
        (self.project / "a").write_bytes(b"1234")
        (self.project / "b").write_bytes(b"1234")
        with patch.object(baseline, "MAX_FILE_BYTES", 3):
            item, _ = observations.observe(self.project, "a", [100])
            self.assertEqual(item["reason"], "file-limit")
        with patch.object(baseline, "MAX_TOTAL_BYTES", 5), patch.object(observations, "git_observation", return_value={"state": "not-repository"}):
            result = observations.capture(self.store, {"paths": ["a", "b"]})
        self.assertEqual(result["snapshot"]["files"][0]["state"], "present")
        self.assertEqual(result["snapshot"]["files"][1]["reason"], "total-limit")

    def test_unreadable_is_unknown_and_retry_is_bounded(self):
        with patch.object(observations, "source_info", side_effect=PermissionError()):
            self.assertEqual(observations.observe(self.project, "a", [1])[0]["reason"], "unreadable")
        with patch.object(observations, "source_info", side_effect=HandoffError("changed", "race")) as probe:
            self.assertEqual(observations.observe(self.project, "a", [1])[0]["reason"], "changed")
            self.assertEqual(probe.call_count, 2)

    def test_batch_and_git_changes_are_partial(self):
        (self.project / "a").write_bytes(b"a")
        original = observations.source_info
        calls = 0
        def changed(project, name):
            nonlocal calls
            calls += 1
            if calls == 3:
                (project / name).write_bytes(b"later")
            return original(project, name)
        with patch.object(observations, "source_info", side_effect=changed), patch.object(observations, "git_observation", side_effect=[
                {"state": "not-repository"}, {"state": "unknown", "reason": "git-error"}]):
            result = observations.capture(self.store, {"paths": ["a"]})
        self.assertEqual(result["snapshot"]["files"][0]["reason"], "changed")
        self.assertEqual(result["snapshot"]["git"]["reason"], "changed")
        self.assertFalse(result["complete"])

    def test_comparison_detects_handoff_version_change(self):
        store = Store(str(self.project))
        path = store.directory / "w.md"
        path.parent.mkdir(parents=True)
        (self.project / "a").write_bytes(b"a")
        with patch.object(observations, "git_observation", return_value={"state": "not-repository"}):
            value = observations.capture(store, {"paths": ["a"]})["snapshot"]
        path.write_text(baseline.put(RECORD, value), encoding="utf-8")
        capture = observations.capture
        def race(*args, **kwargs):
            result = capture(*args, **kwargs)
            path.write_text(path.read_text(encoding="utf-8") + "\n## Manual\nchanged\n", encoding="utf-8")
            return result
        with patch.object(observations, "capture", side_effect=race), patch.object(observations, "git_observation", return_value={"state": "not-repository"}):
            result = observations.compare(store, "w.md")
        self.assertFalse(result["complete"])
        self.assertEqual(result["issues"][-1]["code"], "changed")

    def test_unknown_git_does_not_hide_file_results(self):
        (self.project / "a").write_bytes(b"a")
        with patch.object(observations, "git_observation", return_value={"state": "unknown", "reason": "git-unavailable"}):
            result = observations.capture(self.store, {"paths": ["a"]})
        self.assertFalse(result["complete"])
        self.assertEqual(result["snapshot"]["files"][0]["state"], "present")

    def test_git_trust_failure_is_not_overridden_during_root_discovery_or_capture(self):
        (self.project / "a").write_bytes(b"a")
        denied = subprocess.CompletedProcess([], 128, "", "fatal: detected dubious ownership in repository")
        with patch.object(subprocess, "run", return_value=denied) as git:
            store = Store(str(self.project))
            result = observations.capture(store, {"paths": ["a"]})
        self.assertEqual(git.call_count, 3)
        for call in git.call_args_list:
            self.assertFalse(any("safe.directory" in arg for arg in call.args[0]))
        self.assertEqual(result["snapshot"]["git"], {"state": "unknown", "reason": "git-error"})
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["complete"])
        self.assertEqual(result["snapshot"]["files"][0]["sha256"], hashlib.sha256(b"a").hexdigest())

    def test_tracking_failure_reports_saved_baseline_and_version(self):
        from feather_handoff.writing import create_work
        store = Store(str(self.project))
        (self.project / "a").write_bytes(b"a")
        with patch.object(observations, "git_observation", return_value={"state": "not-repository"}):
            value = observations.capture(store, {"paths": ["a"]})["snapshot"]
            with patch("feather_handoff.writing.ensure_tracking", side_effect=PermissionError("denied")):
                result = create_work(store, "w.md", {"fields": {"goal": "a", "progress": "b", "next": "c"}, "snapshot": value})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["code"], "tracking-failed")
        self.assertEqual(result["version"], result["saved_version"])
        self.assertEqual(baseline.parse(result["content"]), value)

    def test_unknown_sources_do_not_consume_save_verification_budget(self):
        (self.project / "a-unknown").write_bytes(b"12")
        (self.project / "z-known").write_bytes(b"z")
        with patch.object(observations, "git_observation", return_value={"state": "not-repository"}):
            value = observations.capture(self.store, {"paths": ["z-known"]})["snapshot"]
            value["files"].insert(0, {"path": "a-unknown", "state": "unknown", "reason": "unreadable"})
            with patch.object(baseline, "MAX_TOTAL_BYTES", 2):
                self.assertEqual(observations.verify_for_save(self.store, value), value)
            value["files"] = [value["files"][0]]
            with patch.object(observations, "capture", side_effect=AssertionError("Unknown sources must not be read")):
                self.assertEqual(observations.verify_for_save(self.store, value), value)


if __name__ == "__main__":
    unittest.main()
