"""C5: a failed first Git probe is the partial tracking failure with cause_code git-unavailable."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from test_handoff_local_fixes import COMPLETED, FIELDS, MARKER, TOOL, LocalFixesBase, record, sha

from feather_handoff import cli, storage, tracking  # noqa: E402  (path set by the local-fixes module)

WAIT = "tracking was not applied because Git could not be run or did not respond"
NOW = "Do not repeat create or update now. Once Git runs, apply tracking with "
CHOICES = ("default", "track")


def path_without_git() -> str | None:
    """The current PATH minus every directory that holds a Git executable, or None when Git is still found."""
    kept = [entry for entry in os.environ.get("PATH", "").split(os.pathsep)
            if entry and not shutil.which("git", path=entry)]
    path = os.pathsep.join(kept)
    return None if shutil.which("git", path=path) else path


class ProbeFailureBase(LocalFixesBase):
    """Saves of active and completed work, by create and update, with both tracking choices."""

    def setUp(self):
        super().setUp()
        self.ignore = self.project / ".gitignore"

    def git_init(self):
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True, capture_output=True)
        self.ignore.write_bytes(b"*.log\n")

    def save(self, operation: str, name: str, choice: str, completed: bool, payload: dict) -> tuple[int, dict]:
        """Run one save through the failing seam of the subclass; returns its exit status and result."""
        raise NotImplementedError

    def cases(self):
        for operation in ("create", "update"):
            for completed in (False, True):
                for choice in CHOICES:
                    yield operation, completed, choice, f"{operation}-{'done' if completed else 'open'}-{choice}.md"

    def prepare(self, operation: str, name: str) -> dict:
        if operation == "create":
            return {}
        data = self.put(name, record(title=name.removesuffix(".md"), status="進行中", updated=COMPLETED)).read_bytes()
        return {"version": sha(data)}

    def payload(self, operation: str, name: str, choice: str, completed: bool, prepared: dict) -> dict:
        fields = {"status": "完成"} if completed else {"next": "m"}
        if operation == "create":
            return {"title": name.removesuffix(".md"), "tracking": choice,
                    "fields": {**FIELDS, "updated": COMPLETED, **fields}}
        return {**prepared, "tracking": choice, "fields": fields}

    def assert_waiting_partial(self, code: int, result: dict, name: str, choice: str, completed: bool):
        path = self.directory / name
        self.assertEqual(code, 2, result)
        self.assertEqual((result["status"], result["code"], result["cause_code"], result["tracking"], result["state"]),
                         ("partial", "tracking-failed", "git-unavailable", "error", "saved"))
        self.assertFalse(result["complete"])
        self.assertTrue(path.is_file(), "the saved work must stay in place")
        self.assertEqual(result["saved_version"], sha(path.read_bytes()))
        self.assertEqual(result["version"], result["saved_version"])
        self.assertEqual(Path(result["work_path"]), path)
        self.assertEqual("狀態：完成" in path.read_text(encoding="utf-8"), completed)
        self.assertFalse(self.history.exists(), "completed work must not be archived automatically")
        recovery = result["recovery"]
        self.assertIn(WAIT, recovery)
        self.assertIn(NOW, recovery)
        self.assertNotIn("retry", recovery.lower())
        if completed:
            self.assertIn(f'archive using {{"version": "<current version>", "tracking": "{choice}"}}', recovery)
            self.assertIn("not archived", recovery)
        else:
            self.assertIn(f'update using the current version and {{"tracking": "{choice}"}}', recovery)
            self.assertNotIn("archive", recovery)

    def check_all_saves(self):
        rules = self.ignore.read_bytes() if self.ignore.exists() else None
        for operation, completed, choice, name in self.cases():
            with self.subTest(operation=operation, completed=completed, choice=choice):
                prepared = self.prepare(operation, name)
                code, result = self.save(operation, name, choice, completed,
                                         self.payload(operation, name, choice, completed, prepared))
                self.assert_waiting_partial(code, result, name, choice, completed)
                self.assertEqual(self.ignore.read_bytes() if self.ignore.exists() else None, rules,
                                 "Git rules must not change")


@unittest.skipUnless(shutil.which("git"), "Git is required to set up the repository")
class MissingGitExecutableTest(ProbeFailureBase):
    """A PATH without Git and an explicitly selected root: the handoff command runs as a subprocess."""

    def setUp(self):
        super().setUp()
        self.path = path_without_git()
        if self.path is None:
            self.skipTest("Git cannot be removed from PATH on this host")

    def run_without_git(self, *args, payload, expected=None) -> tuple[int, dict]:
        environment = {**os.environ, "PATH": self.path}
        completed = subprocess.run([sys.executable, "-B", str(TOOL), "--project", str(self.project), "--exact-root",
                                    *args], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                   capture_output=True, timeout=30, env=environment)
        stdout = completed.stdout.decode("utf-8")
        result = json.loads(stdout)
        if expected is not None:
            self.assertEqual(completed.returncode, expected, stdout + completed.stderr.decode("utf-8", "replace"))
        return completed.returncode, result

    def save(self, operation, name, choice, completed, payload):
        return self.run_without_git(operation, "--work", name, payload=payload)

    def test_real_repository_as_explicit_root_saves_partially_for_every_case(self):
        self.git_init()
        self.check_all_saves()

    def test_non_git_explicit_root_without_git_saves_partially(self):
        self.check_all_saves()
        self.assertFalse(self.ignore.exists())

    def test_explicit_archive_after_the_failure_keeps_its_contract(self):
        self.git_init()
        for choice in CHOICES:
            with self.subTest(choice=choice):
                name = f"archive-{choice}.md"
                code, saved = self.save("create", name, choice, True,
                                        self.payload("create", name, choice, True, {}))
                self.assert_waiting_partial(code, saved, name, choice, True)
                _, archived = self.run_without_git("archive", "--work", name, expected=2,
                                                   payload={"version": saved["version"], "tracking": choice})
                self.assertEqual((archived["status"], archived["code"], archived["cause_code"], archived["tracking"]),
                                 ("partial", "tracking-failed", "git-unavailable", "error"))
                self.assertTrue(archived["archived"])
                self.assertFalse(archived["complete"])
                self.assertIn("do not retry archive", archived["recovery"])
                self.assertFalse((self.directory / name).exists())
                self.assertIn(f"## {name.removesuffix('.md')} · 完成：{COMPLETED}\n".encode("utf-8"),
                              self.history.read_bytes())
                self.assertEqual(archived["history_version"], sha(self.history.read_bytes()))
                self.assertEqual(self.ignore.read_bytes(), b"*.log\n")
                self.history.unlink()

    def test_once_git_runs_the_recovery_applies_tracking(self):
        self.git_init()
        for choice, line, reported in (("default", "/.feather/handoffs/", "ignored"), ("track", MARKER, "track")):
            with self.subTest(choice=choice):
                self.ignore.write_bytes(b"*.log\n")
                active, done = f"active-{choice}.md", f"done-{choice}.md"
                _, saved = self.save("create", active, choice, False, self.payload("create", active, choice, False, {}))
                self.assertEqual(saved["cause_code"], "git-unavailable")
                updated = self.run_tool("--exact-root", "update", "--work", active,
                                        payload={"version": saved["version"], "tracking": choice})
                self.assertEqual((updated["status"], updated["tracking"]), ("ok", reported))
                self.assertEqual(self.ignore.read_bytes(), f"*.log\n{line}\n".encode("utf-8"))
                _, saved = self.save("create", done, choice, True, self.payload("create", done, choice, True, {}))
                self.assertEqual(saved["cause_code"], "git-unavailable")
                archived = self.run_tool("--exact-root", "archive", "--work", done,
                                         payload={"version": saved["version"], "tracking": choice})
                self.assertEqual((archived["status"], archived["archived"]), ("ok", True))
                self.assertIn(archived["tracking"], {reported, "existing-rule"})
                self.assertFalse((self.directory / done).exists())
                self.history.unlink()


class InjectedProbeFailureTest(ProbeFailureBase):
    """Timeouts and other OS errors at the first probe, injected through the same command entry point."""

    FAILURES = (subprocess.TimeoutExpired(["git"], 5), PermissionError(13, "Access is denied"),
                OSError(5, "Input/output error"))

    def failing_probe(self, failure: BaseException):
        real = tracking.git

        def git(store, *arguments):
            if arguments == ("rev-parse", "--is-inside-work-tree"):
                raise failure
            return real(store, *arguments)
        return mock.patch.object(tracking, "git", side_effect=git)

    def run_cli(self, *args, payload, exact=False) -> tuple[int, dict]:
        self.addCleanup(storage.reset_roots)
        out = io.StringIO()
        argv = ["handoff", "--project", str(self.project), *(["--exact-root"] if exact else []), *args]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(cli, "input_payload", return_value=payload), \
                contextlib.redirect_stdout(out):
            code = cli.main()
        return code, json.loads(out.getvalue())

    def save(self, operation, name, choice, completed, payload):
        with self.failing_probe(self.failure):
            return self.run_cli(operation, "--work", name, payload=payload, exact=self.exact)

    def check(self, exact: bool):
        self.exact = exact
        for failure in self.FAILURES:
            with self.subTest(failure=type(failure).__name__):
                self.failure = failure
                self.check_all_saves()
                for name in os.listdir(self.directory):
                    (self.directory / name).unlink()

    @unittest.skipUnless(shutil.which("git"), "Git is required to set up the repository")
    def test_discovered_repository_saves_partially(self):
        self.git_init()
        self.check(exact=False)

    @unittest.skipUnless(shutil.which("git"), "Git is required to set up the repository")
    def test_real_repository_as_explicit_root_saves_partially(self):
        self.git_init()
        self.check(exact=True)

    def test_non_git_explicit_root_saves_partially(self):
        self.check(exact=True)
        self.assertFalse(self.ignore.exists())

    @unittest.skipUnless(shutil.which("git"), "Git is required to set up the repository")
    def test_explicit_archive_after_a_timeout_keeps_its_contract(self):
        self.git_init()
        self.exact, self.failure = False, subprocess.TimeoutExpired(["git"], 5)
        code, saved = self.save("create", "a.md", "track", True, self.payload("create", "a.md", "track", True, {}))
        self.assert_waiting_partial(code, saved, "a.md", "track", True)
        with self.failing_probe(self.failure):
            code, archived = self.run_cli("archive", "--work", "a.md",
                                          payload={"version": saved["version"], "tracking": "track"})
        self.assertEqual(code, 2)
        self.assertEqual((archived["status"], archived["code"], archived["cause_code"]),
                         ("partial", "tracking-failed", "git-unavailable"))
        self.assertTrue(archived["archived"])
        self.assertIn("do not retry archive", archived["recovery"])
        self.assertFalse((self.directory / "a.md").exists())
        self.assertEqual(archived["history_version"], sha(self.history.read_bytes()))
        self.assertEqual(self.ignore.read_bytes(), b"*.log\n")


@unittest.skipUnless(shutil.which("git"), "Git is required to report a directory as not a repository")
class GenuineNonGitTest(LocalFixesBase):
    """A directory Git reports as not a repository still saves successfully as non-Git."""

    def setUp(self):
        super().setUp()
        probe = subprocess.run(["git", "-C", str(self.project), "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, text=True)
        if probe.returncode == 0:
            self.skipTest("the temporary directory is inside a Git repository")

    def test_create_update_and_completion_stay_successful(self):
        for exact in ((), ("--exact-root",)):
            with self.subTest(exact=bool(exact)):
                for choice in CHOICES:
                    name = f"{choice}{len(exact)}.md"
                    created = self.run_tool(*exact, "create", "--work", name,
                                            payload={"title": name, "fields": FIELDS, "tracking": choice})
                    self.assertEqual((created["status"], created["tracking"]), ("ok", "non-git"))
                    updated = self.run_tool(*exact, "update", "--work", name, payload={
                        "version": created["version"], "tracking": choice,
                        "fields": {"status": "完成", "updated": COMPLETED}})
                    self.assertEqual((updated["status"], updated["archived"], updated["tracking"]),
                                     ("ok", True, "non-git"))
                    self.assertFalse((self.directory / name).exists())
        self.assertFalse((self.project / ".gitignore").exists())


if __name__ == "__main__":
    unittest.main()
