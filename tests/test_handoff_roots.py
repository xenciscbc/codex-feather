"""Root diagnostics preserve readable evidence and stop ambiguous writes."""
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_handoff_tool as handoff_tests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/handoff/scripts"))
from feather_handoff import cli, storage
from feather_handoff.writing import create_work


class HandoffRootTest(unittest.TestCase):
    setUp = handoff_tests.HandoffToolTest.setUp
    write_work = handoff_tests.HandoffToolTest.write_work
    tree = handoff_tests.HandoffToolTest.snapshot

    def invoke(self, command, *args, payload=None, exact=False):
        argv = ["handoff", "--project", str(self.project)]
        if exact:
            argv.append("--exact-root")
        argv.extend([command, *args])
        output = io.StringIO()
        with patch.object(sys, "argv", argv), patch.object(sys, "stdout", output), \
                patch.object(cli, "input_payload", return_value=payload or {}):
            code = cli.main()
        return code, json.loads(output.getvalue())

    def denied(self):
        return subprocess.CompletedProcess([], 128, "", "fatal: detected dubious ownership in repository")

    def test_trust_failure_returns_readable_partial_scope(self):
        self.write_work()
        before = self.tree()
        with patch.object(storage.subprocess, "run", return_value=self.denied()):
            code, result = self.invoke("list")
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["operation_status"], "ok")
        self.assertFalse(result["complete"])
        self.assertEqual(result["items"][0]["work"], "config-audit.md")
        self.assertEqual(result["root"]["path"], str(self.project.resolve()))
        self.assertIn("dubious ownership", result["root"]["reason"])
        self.assertEqual(before, self.tree())

    def test_missing_git_and_timeout_are_not_empty_project_evidence(self):
        for error in [FileNotFoundError("git unavailable"), subprocess.TimeoutExpired("git", 5)]:
            with self.subTest(error=error), patch.object(storage.subprocess, "run", side_effect=error):
                code, result = self.invoke("list")
            self.assertEqual(code, 2)
            self.assertEqual(result["root"]["state"], "uncertain")
            self.assertEqual(result["operation_status"], "missing")
            self.assertFalse(result["complete"])

    def test_all_mutations_refuse_uncertain_root_before_writing(self):
        self.write_work()
        before = self.tree()
        for command in ["create", "update", "archive", "clear", "seal"]:
            args = ["--work", "w.md"] if command in {"create", "update", "archive"} else []
            with self.subTest(command=command), patch.object(storage.subprocess, "run", return_value=self.denied()):
                code, result = self.invoke(command, *args)
            self.assertEqual(code, 2)
            self.assertEqual(result["code"], "project-root-uncertain")
            self.assertIn("--exact-root", result["message"])
            self.assertEqual(before, self.tree())

    def test_direct_mutation_cannot_bypass_root_guard(self):
        with patch.object(storage.subprocess, "run", return_value=self.denied()):
            store = storage.Store(str(self.project))
        with self.assertRaises(storage.HandoffError) as caught:
            create_work(store, "w.md", {})
        self.assertEqual(caught.exception.code, "project-root-uncertain")
        self.assertFalse(store.directory.exists())

    def test_broken_git_marker_is_uncertain_not_non_git(self):
        (self.project / ".git").write_text("gitdir: missing-metadata\n", encoding="utf-8")
        code, result = self.invoke("list")
        self.assertEqual(code, 2)
        self.assertEqual(result["root"]["state"], "uncertain")
        before = self.tree()
        code, result = self.invoke("create", "--work", "w.md")
        self.assertEqual(result["code"], "project-root-uncertain")
        self.assertEqual(before, self.tree())

    def test_exact_root_read_needs_no_git_and_write_keeps_trust_failure_visible(self):
        self.write_work()
        with patch.object(storage.subprocess, "run", side_effect=AssertionError("Discovery not needed")):
            code, result = self.invoke("read", "--work", "config-audit.md", exact=True)
        self.assertEqual(code, 0)
        self.assertEqual(result["root"]["state"], "explicit")
        with patch.object(storage.subprocess, "run", return_value=self.denied()) as git:
            code, result = self.invoke("create", "--work", "w.md", exact=True,
                                       payload={"fields": {"goal": "g", "progress": "p", "next": "n"}})
        self.assertEqual(code, 2)
        self.assertEqual(result["code"], "tracking-failed")
        self.assertEqual(result["state"], "saved")
        self.assertTrue((self.directory / "w.md").is_file())
        self.assertFalse((self.project / ".gitignore").exists())
        self.assertFalse(any("safe.directory" in arg for arg in git.call_args.args[0]))

    def test_git_subdirectory_resolves_root_and_non_git_is_complete(self):
        code, result = self.invoke("list")
        self.assertEqual(code, 0)
        self.assertEqual(result["root"]["state"], "non-git")
        subprocess.run(["git", "-C", str(self.project), "init", "--quiet"], check=True, capture_output=True)
        self.write_work()
        nested = self.project / "nested"
        nested.mkdir()
        parent = self.project
        self.project = nested
        code, result = self.invoke("list")
        self.assertEqual(code, 0)
        self.assertEqual(result["root"]["state"], "git")
        self.assertEqual(result["root"]["path"], str(parent.resolve()))
        self.assertEqual(result["items"][0]["work"], "config-audit.md")
        code, result = self.invoke("list", exact=True)
        self.assertEqual(code, 0)
        self.assertEqual(result["root"]["path"], str(nested.resolve()))
        self.assertEqual(result["status"], "missing")


if __name__ == "__main__":
    unittest.main()
