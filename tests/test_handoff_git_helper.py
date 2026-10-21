"""Repository safety C4: the handoff tool runs every Git command through one hardened helper.

Trust boundary: a project repository's tracked content and local Git metadata against the handoff tool's process. The
repository's own configuration must not choose a program the tool's Git commands run, and reading must not write the
index; the user's global and system configuration and environment stay trusted."""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/handoff/scripts"
TOOL = SCRIPTS / "handoff.py"
sys.path.insert(0, str(SCRIPTS))

from feather_handoff import cli, observations, storage  # noqa: E402

# The helper's options after the resolved Git executable; PREFIX_LENGTH counts the executable too.
OPTIONS = ["--no-pager", "--no-optional-locks", "-c", "core.fsmonitor="]
PREFIX_LENGTH = 1 + len(OPTIONS)
FIELDS = {"goal": "g", "progress": "p", "next": "n", "updated": "2026-10-11T10:00:00+08:00"}
UPDATED = "2026-10-11T11:00:00+08:00"
CAPTURED = "2026-10-11T10:00:00+08:00"
# Fixed identity and dates make the plain and the configured repository's commits identical.
COMMIT_ENV = {"GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
              "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
              "GIT_AUTHOR_DATE": "2026-10-11T10:00:00+08:00", "GIT_COMMITTER_DATE": "2026-10-11T10:00:00+08:00"}


def stand_in_git(test: unittest.TestCase) -> str:
    """For tests that replace the Git process: PATH names only a scratch directory holding a file the resolver
    accepts, so the helper's first argument is that file's absolute path whether or not Git is installed. Returns it."""
    temporary = tempfile.TemporaryDirectory()
    test.addCleanup(temporary.cleanup)
    tools = os.path.realpath(temporary.name)
    executable = os.path.join(tools, storage.GIT_NAME)
    Path(executable).write_bytes(b"")
    os.chmod(executable, 0o755)
    test.enterContext(mock.patch.dict(os.environ, {"PATH": tools}))
    return executable


class GitProcessStartTest(unittest.TestCase):
    """C4 item 2: no place in the handoff tool's package other than the helper starts a Git process."""

    SUBPROCESS = {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"}
    OS = {"system", "popen", "startfile", "fork", "forkpty"}
    OS_PREFIXES = ("exec", "spawn", "posix_spawn")
    # Standard modules that can start a process without naming subprocess or os, or import one by a computed name.
    FORBIDDEN_MODULES = {"asyncio", "multiprocessing", "concurrent", "pty", "ctypes", "importlib", "runpy",
                         "_posixsubprocess", "_winapi"}

    def starts(self, module: str, name: str) -> bool:
        if module == "subprocess":
            return name in self.SUBPROCESS
        return module == "os" and (name in self.OS or name.startswith(self.OS_PREFIXES))

    def scan(self, path: Path) -> list[tuple[str, str]]:
        """(enclosing function, reference) for every process start; also fails on imports that would hide one."""
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found, scope = [], {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    scope.setdefault(id(child), node.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    self.assertNotIn(top, self.FORBIDDEN_MODULES, f"{path.name} imports {alias.name}")
                    if top in {"subprocess", "os"}:
                        self.assertIn(alias.asname, {None, top}, f"{path.name} renames {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                self.assertNotIn(top, self.FORBIDDEN_MODULES, f"{path.name} imports from {node.module}")
                for alias in node.names:
                    self.assertFalse(alias.name == "*" and top in {"subprocess", "os"}, f"{path.name}: star import")
                    self.assertFalse(self.starts(top, alias.name), f"{path.name} imports {top}.{alias.name}")
            elif isinstance(node, ast.Name) and node.id in {"__import__", "exec", "eval", "compile"}:
                self.fail(f"{path.name} uses {node.id}")
            elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                  and self.starts(node.value.id, node.attr)):
                found.append((scope.get(id(node), "<module>"), f"{node.value.id}.{node.attr}"))
        return found

    def test_only_the_helper_starts_a_process(self):
        sources = sorted(SCRIPTS.rglob("*.py"))
        self.assertIn(SCRIPTS / "feather_handoff" / "storage.py", sources)
        starts = {(path.relative_to(SCRIPTS).as_posix(), *start) for path in sources for start in self.scan(path)}
        self.assertEqual(starts, {("feather_handoff/storage.py", "run_git", "subprocess.run")})

    def test_the_scan_finds_a_process_start(self):
        # Abuse check for the scan itself: a second Git start, written several ways, would be caught.
        with tempfile.TemporaryDirectory() as temp:
            for source in ("import subprocess\ndef f():\n    subprocess.check_output(['git'])\n",
                           "import os\ndef f():\n    os.system('git status')\n",
                           "from subprocess import Popen\n",
                           "import subprocess as s\n",
                           "import asyncio\n"):
                with self.subTest(source=source):
                    path = Path(temp, "probe.py")
                    path.write_text(source, encoding="utf-8")
                    try:
                        found = self.scan(path)
                    except AssertionError:
                        continue  # refused at the import
                    self.assertTrue(found, "the scan missed a process start")


class GitHelperCallTest(unittest.TestCase):
    """C4 item 1: the helper's argument list, environment and error handling, with and without a Store."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(os.path.realpath(temporary.name))
        self.addCleanup(storage.reset_roots)

    def test_helper_prefixes_every_command_and_keeps_the_environment_protections(self):
        executable = stand_in_git(self)
        completed = subprocess.CompletedProcess([], 0, "out\n", "")
        with mock.patch.object(storage.subprocess, "run", return_value=completed) as run, \
                mock.patch.dict(os.environ, {"GIT_DIR": "elsewhere", "GIT_INDEX_FILE": "elsewhere"}):
            # No Store exists yet: discovery calls the helper with a plain path.
            self.assertIs(storage.run_git(self.project, "rev-parse", "--show-toplevel", errors="replace"), completed)
            storage.run_git(self.project, "ls-files", "--", ".feather/handoffs/")
        first, second = run.call_args_list
        self.assertEqual(first.args[0], [executable, *OPTIONS, "-C", str(self.project), "rev-parse", "--show-toplevel"])
        self.assertEqual(second.args[0], [executable, *OPTIONS, "-C", str(self.project), "ls-files", "--",
                                          ".feather/handoffs/"])
        self.assertEqual({key: first.kwargs[key] for key in ("capture_output", "text", "encoding", "errors", "timeout")},
                         {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace", "timeout": 5})
        self.assertEqual(second.kwargs["errors"], "strict")
        for call in (first, second):
            self.assertEqual(call.kwargs["cwd"], os.path.dirname(executable))
            environment = call.kwargs["env"]
            self.assertEqual(environment["PATH"], os.path.dirname(executable))
            self.assertNotIn("GIT_DIR", environment)
            self.assertNotIn("GIT_INDEX_FILE", environment)
            self.assertEqual((environment["GIT_OPTIONAL_LOCKS"], environment["LC_ALL"]), ("0", "C"))

    def test_helper_raises_what_the_process_start_raises(self):
        # Each caller keeps its own handling of a missing Git and a timeout.
        stand_in_git(self)
        for error in (FileNotFoundError("git"), subprocess.TimeoutExpired(["git"], 5)):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(storage.subprocess, "run", side_effect=error), self.assertRaises(type(error)):
                storage.run_git(self.project, "rev-parse", "--is-inside-work-tree")

    def test_discovery_tracking_and_observations_all_use_the_helper(self):
        try:
            subprocess.run(["git", "init", "--quiet", str(self.project)], check=True, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as error:
            self.skipTest(f"Git cannot set up the repository: {error}")
        (self.project / "a.txt").write_bytes(b"a\n")
        real, calls = subprocess.run, []

        def recorded(args, **kwargs):
            calls.append(list(args))
            return real(args, **kwargs)

        def invoke(*args, payload=None):
            out = io.StringIO()
            with mock.patch.object(sys, "argv", ["handoff", "--project", str(self.project), *args]), \
                    mock.patch.object(cli, "input_payload", return_value=payload), contextlib.redirect_stdout(out):
                cli.main()
            return json.loads(out.getvalue())
        with mock.patch.object(storage.subprocess, "run", side_effect=recorded):
            snapshot = invoke("snapshot", payload={"paths": ["a.txt"]})["snapshot"]
            created = invoke("create", "--work", "w.md", payload={"fields": FIELDS, "snapshot": snapshot})
            invoke("update", "--work", "w.md", payload={"version": created["version"], "tracking": "track"})
            invoke("compare", "--work", "w.md")
        self.assertEqual(created["status"], "ok", created)
        commands = {tuple(call[PREFIX_LENGTH + 2:]) for call in calls}
        # Discovery, the tracking probe and rules, and the observation each ran through the helper.
        for expected in (("rev-parse", "--show-toplevel"), ("rev-parse", "--is-inside-work-tree"),
                         ("ls-files", "--", ".feather/handoffs/"), ("check-ignore", "-v", "--", ".feather/handoffs/w.md"),
                         ("check-ignore", "-q", "--", ".feather/handoffs/w.md"), ("symbolic-ref", "--quiet", "HEAD"),
                         ("rev-parse", "--verify", "--quiet", "HEAD")):
            self.assertIn(expected, commands)
        # Every call starts the resolver's absolute path, never a bare name.
        executable = storage.resolve_git(os.environ.get("PATH"))
        self.assertTrue(os.path.isabs(executable), executable)
        for call in calls:
            self.assertEqual(call[:PREFIX_LENGTH + 2], [executable, *OPTIONS, "-C", str(self.project)], call)


class RepositoryChosenProgramTest(unittest.TestCase):
    """C4 item 3 (B6), regression and abuse check: a repository whose local configuration names an fsmonitor program
    and a clean filter, each leaving a marker outside the repository when run. The tool's list, read, create, update,
    snapshot and compare operations, through its command line, run neither, write no index, and return what they
    return in the same repository without that configuration."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temporary.cleanup)
        self.root = Path(os.path.realpath(temporary.name))
        self.marker = self.root / "marker"
        (self.root / "home").mkdir()
        empty = self.root / "gitconfig"
        empty.write_bytes(b"")
        # Isolated from the user's global and system Git configuration; no inherited GIT_* variable reaches Git.
        self.env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
        self.env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty), "HOME": str(self.root / "home"),
                         "XDG_CONFIG_HOME": str(self.root / "home")})
        self.scripts = {}
        for name, body in (("monitor", "exit 1"), ("filter", "cat")):
            script = self.root / f"{name}.sh"
            script.write_text(f'#!/bin/sh\necho {name} >> "{self.marker.as_posix()}"\n{body}\n', encoding="utf-8",
                              newline="\n")
            script.chmod(0o755)
            self.scripts[name] = script.as_posix()

    def git(self, repo: Path, *args, check=True) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(["git", *args], cwd=repo, env={**self.env, **COMMIT_ENV}, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            self.skipTest(f"Git cannot be run: {error}")
        if check:
            self.assertEqual(result.returncode, 0, (args, result.stderr))
        return result

    def repository(self, name: str) -> Path:
        repo = self.root / name
        repo.mkdir()
        # Setup runs with fsmonitor disabled and before the marker configuration exists.
        self.git(repo, "-c", "core.fsmonitor=", "init", "--quiet", "--initial-branch=main", ".")
        self.git(repo, "config", "core.autocrlf", "false")
        (repo / ".gitattributes").write_bytes(b"tracked.txt filter=marker\n")
        (repo / "tracked.txt").write_bytes(b"tracked\n")
        (repo / "other.txt").write_bytes(b"other\n")
        self.git(repo, "-c", "core.fsmonitor=", "add", "--", ".gitattributes", "tracked.txt", "other.txt")
        self.git(repo, "-c", "core.fsmonitor=", "-c", "commit.gpgSign=false", "commit", "--quiet", "--no-verify",
                 "-m", "fixture")
        return repo

    def ran(self) -> set[str]:
        found = set(self.marker.read_text(encoding="utf-8").split()) if self.marker.exists() else set()
        self.marker.unlink(missing_ok=True)
        return found

    def run_tool(self, repo: Path, *args, payload=None) -> dict:
        result = subprocess.run([sys.executable, "-B", str(TOOL), "--project", str(repo), *args],
                                input=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else b"",
                                capture_output=True, timeout=60, env=self.env)
        stdout = result.stdout.decode("utf-8")
        self.assertEqual(result.returncode, 0, stdout + result.stderr.decode("utf-8", "replace"))
        return json.loads(stdout)

    def normalized(self, repo: Path, value):
        """The result with the repository's own path and the capture time made comparable across repositories."""
        if isinstance(value, dict):
            return {key: CAPTURED if key == "captured_at" else self.normalized(repo, item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.normalized(repo, item) for item in value]
        if isinstance(value, str):
            return value.replace(str(repo), "<repo>")
        return value

    def test_no_repository_chosen_program_runs_and_results_are_unchanged(self):
        plain, configured = self.repository("plain"), self.repository("configured")
        self.git(configured, "config", "core.fsmonitor", self.scripts["monitor"])
        self.git(configured, "config", "filter.marker.clean", self.scripts["filter"])
        self.assertEqual(self.ran(), set())
        # Positive control: an index-reading command the tool runs, without the helper's prefix, runs the monitor.
        self.git(configured, "ls-files", "--", ".feather/handoffs/", check=False)
        controls = self.ran()
        if "monitor" not in controls:
            self.skipTest("this Git ran no configured fsmonitor program for an index read")
        # The clean filter is a regression guard: none of the tool's current commands runs filters. Its control shows
        # that the configured filter does run when Git applies it, so its absence below means something.
        self.git(configured, "-c", "core.fsmonitor=", "hash-object", "--", "tracked.txt")
        self.assertEqual(self.ran(), {"filter"}, "the configured clean filter did not run in its control")
        indexes = {repo: (repo / ".git/index").read_bytes() for repo in (plain, configured)}

        results = {plain: {}, configured: {}}

        def step(label: str, *args, payload=None, status="ok") -> dict:
            """One operation in both repositories; returns the plain repository's result."""
            outcome = {}
            for repo in (plain, configured):
                result = self.run_tool(repo, *args, payload=payload(results[repo]) if callable(payload) else payload)
                results[repo][label] = result
                outcome[repo] = self.normalized(repo, result)
                self.assertEqual(self.ran(), set(), f"{label} ran a program the repository configured")
            self.assertEqual(outcome[configured], outcome[plain], label)
            self.assertEqual(outcome[plain]["status"], status, outcome[plain])
            return results[plain][label]

        # Before any work exists, list reports the handoff directory as missing.
        step("list-empty", "list", status="missing")
        snapshot = step("snapshot", "snapshot", payload={"paths": ["tracked.txt", "other.txt", "missing.txt"]})
        self.assertEqual(snapshot["snapshot"]["git"]["state"], "available")
        # One baseline for both repositories, so the saved records and their versions are comparable.
        value = {**snapshot["snapshot"], "captured_at": CAPTURED}
        created = step("create", "create", "--work", "w.md", payload={"title": "w", "fields": FIELDS, "snapshot": value})
        self.assertEqual(created["tracking"], "ignored")
        step("read", "read", "--work", "w.md")
        updated = step("update", "update", "--work", "w.md", payload=lambda previous: {
            "version": previous["create"]["version"], "tracking": "track", "fields": {"next": "m", "updated": UPDATED}})
        self.assertEqual(updated["tracking"], "track")
        compared = step("compare", "compare", "--work", "w.md")
        self.assertEqual(compared["git"]["comparison"], "unchanged")
        self.assertEqual([item["comparison"] for item in compared["files"]], ["unchanged"] * 3)
        step("list", "list")
        for repo, index in indexes.items():
            self.assertEqual((repo / ".git/index").read_bytes(), index, f"{repo.name}: the tool wrote Git's index")


CONFIG_READ = ["config", "--list", "--includes", "-z"]
OBJECT_READS = {"ls-files", "check-ignore"}
COMPLETED_AT = "2026-10-11T12:00:00+08:00"


MARKER = "# cc-feather: track /.feather/handoffs/"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_version(text: str) -> tuple[int, int, int] | None:
    match = re.match(r"git version (\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(map(int, match.groups())) if match else None


class FakeGit:
    """A recorded stand-in for the Git process: answers the tool's tracking commands for a chosen version and
    configuration, and fails when a version older than 2.45.0 receives --no-lazy-fetch, as a real one would."""

    def __init__(self, project: Path, version="git version 2.45.0", config="remote.origin.promisor\ntrue\0",
                 config_code=0, version_code=0):
        self.project, self.version, self.config = project, version, config
        self.config_code, self.version_code = config_code, version_code
        self.calls: list[list[str]] = []
        # The test's PATH names only stand_in_git's directory, so the helper must start that file from there.
        self.directory = os.environ["PATH"]
        self.prefix = [os.path.join(self.directory, storage.GIT_NAME), *OPTIONS]

    def split(self, args: list[str]) -> tuple[bool, list[str]]:
        """Whether the command carries --no-lazy-fetch, and its Git arguments after the -C directory."""
        flagged = args[PREFIX_LENGTH] == "--no-lazy-fetch"
        start = PREFIX_LENGTH + (1 if flagged else 0)
        assert args[:PREFIX_LENGTH] == self.prefix and args[start:start + 2] == ["-C", str(self.project)], args
        return flagged, args[start + 2:]

    def __call__(self, args, **kwargs):
        assert (kwargs["cwd"], kwargs["env"]["PATH"]) == (self.directory, self.directory), kwargs
        args = list(args)
        self.calls.append(args)
        flagged, rest = self.split(args)
        parsed = git_version(self.version)
        if flagged and (parsed is None or parsed < (2, 45, 0)):
            return subprocess.CompletedProcess(args, 129, "", "unknown option: --no-lazy-fetch\n")
        if rest == ["rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(args, 0, "true\n", "")
        if rest == CONFIG_READ:
            return subprocess.CompletedProcess(args, self.config_code, self.config, "")
        if rest == ["version"]:
            return subprocess.CompletedProcess(args, self.version_code, self.version + "\n", "")
        if rest[:1] == ["ls-files"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if rest[:1] == ["check-ignore"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        raise AssertionError(f"unexpected Git command {args}")

    def commands(self) -> list[tuple[bool, list[str]]]:
        return [self.split(call) for call in self.calls]

    def reset(self):
        self.calls.clear()


class PromisorDetectionTest(unittest.TestCase):
    """C4 item 7 (D-1): the effective configuration, includes followed, decides whether the checkout declares a
    promisor remote; only then is the Git version read, and only Git 2.45.0 or later may read objects there."""

    DECLARING = ("extensions.partialclone\norigin\0", "remote.origin.promisor\0", "remote.origin.promisor\ntrue\0",
                 "core.bare\nfalse\0remote.Up.Stream.promisor\nyes\0", "remote.origin.partialclonefilter\nblob:none\0",
                 "remote.origin.promisor\nfalse\0remote.other.promisor\n1\0")
    NOT_DECLARING = ("", "core.bare\nfalse\0", "remote.origin.promisor\nfalse\0", "remote.origin.promisor\n\0",
                     "remote.origin.promisor\noff\0remote.origin.url\nfile:///elsewhere\0")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(os.path.realpath(temporary.name))
        stand_in_git(self)

    def guard(self, fake: FakeGit):
        with mock.patch.object(storage.subprocess, "run", side_effect=fake):
            return storage.lazy_fetch_guard(self.project)

    def test_a_declared_promisor_remote_needs_git_2_45_0(self):
        for config in self.DECLARING:
            for version, allowed in (("git version 2.45.0", True), ("git version 2.47.1.windows.1", True),
                                     ("git version 3.0.0", True), ("git version 2.44.9", False),
                                     ("git version 2.43.0.windows.1", False)):
                with self.subTest(config=config, version=version):
                    fake = FakeGit(self.project, version=version, config=config)
                    if allowed:
                        self.assertIs(self.guard(fake), True)
                    else:
                        with self.assertRaises(storage.HandoffError) as raised:
                            self.guard(fake)
                        self.assertEqual(raised.exception.code, "promisor-remote")
                        self.assertIn("2.45.0", str(raised.exception))
                    # The configuration is read with includes followed, then the version; neither carries the flag.
                    self.assertEqual(fake.commands(), [(False, CONFIG_READ), (False, ["version"])])

    def test_no_promisor_remote_needs_no_version_and_no_flag(self):
        for config in self.NOT_DECLARING:
            with self.subTest(config=config):
                fake = FakeGit(self.project, version="git version 2.43.0", config=config)
                self.assertIs(self.guard(fake), False)
                self.assertEqual(fake.commands(), [(False, CONFIG_READ)])

    def test_an_unreadable_configuration_or_unknown_version_is_not_established(self):
        for label, fake in (("config fails", FakeGit(self.project, config_code=1)),
                            ("version fails", FakeGit(self.project, version_code=1)),
                            ("version unparsable", FakeGit(self.project, version="git version unknown")),
                            ("version incomplete", FakeGit(self.project, version="git version 2.45"))):
            with self.subTest(label), self.assertRaises(storage.HandoffError) as raised:
                self.guard(fake)
            self.assertEqual(raised.exception.code, "promisor-unknown")

    def test_a_process_failure_propagates(self):
        # The caller maps these to git-unavailable, as for the first probe.
        for error in (FileNotFoundError("git"), subprocess.TimeoutExpired(["git"], 5)):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(storage.subprocess, "run", side_effect=error), self.assertRaises(type(error)):
                storage.lazy_fetch_guard(self.project)

    def test_the_helper_places_the_flag_among_its_global_options(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(storage.subprocess, "run", return_value=completed) as run:
            storage.run_git(self.project, "ls-files", "--", "x", no_lazy_fetch=True)
            storage.run_git(self.project, "ls-files", "--", "x")
        flagged, plain = (call.args[0] for call in run.call_args_list)
        executable = os.path.join(os.environ["PATH"], storage.GIT_NAME)
        self.assertEqual(flagged, [executable, *OPTIONS, "--no-lazy-fetch", "-C", str(self.project), "ls-files", "--",
                                   "x"])
        self.assertEqual(plain, [executable, *OPTIONS, "-C", str(self.project), "ls-files", "--", "x"])


class SimulatedPromisorTest(unittest.TestCase):
    """C4 item 7 through the tool's command line with a simulated Git: on 2.45.0 or later every command after the
    detection carries --no-lazy-fetch; on an older or unknown Git no command that can read objects runs, nothing
    is written to the Git rules, and the work is saved as a tracking failure whose recovery is not a retry."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(os.path.realpath(temporary.name))
        stand_in_git(self)
        self.directory = self.project / ".feather/handoffs"
        self.ignore = self.project / ".gitignore"
        self.addCleanup(storage.reset_roots)

    def invoke(self, fake: FakeGit, *args, payload=None) -> tuple[int, dict]:
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["handoff", "--project", str(self.project), "--exact-root", *args]), \
                mock.patch.object(cli, "input_payload", return_value=payload), \
                mock.patch.object(storage.subprocess, "run", side_effect=fake), contextlib.redirect_stdout(out):
            code = cli.main()
        return code, json.loads(out.getvalue())

    def assert_flagged_after_detection(self, fake: FakeGit):
        commands = fake.commands()
        self.assertEqual(commands[:3], [(False, ["rev-parse", "--is-inside-work-tree"]), (False, CONFIG_READ),
                                        (False, ["version"])])
        later = commands[3:]
        self.assertTrue(later, "tracking ran no command after the detection")
        self.assertTrue(OBJECT_READS & {rest[0] for _, rest in later}, later)
        for flagged, rest in later:
            self.assertTrue(flagged, f"{rest} ran without --no-lazy-fetch")

    def test_new_git_adds_the_flag_to_every_command_after_detection(self):
        for index, version in enumerate(("git version 2.45.0", "git version 2.47.1.windows.1", "git version 3.0.0")):
            with self.subTest(version=version):
                self.ignore.unlink(missing_ok=True)
                fake, name = FakeGit(self.project, version=version), f"w{index}.md"
                code, created = self.invoke(fake, "create", "--work", name, payload={"title": "w", "fields": FIELDS})
                self.assertEqual((code, created["status"], created["tracking"]), (0, "ok", "ignored"), created)
                self.assert_flagged_after_detection(fake)
                fake.reset()
                code, updated = self.invoke(fake, "update", "--work", name,
                                            payload={"version": created["version"], "tracking": "track"})
                self.assertEqual((code, updated["status"], updated["tracking"]), (0, "ok", "track"), updated)
                self.assert_flagged_after_detection(fake)
                fake.reset()
                code, done = self.invoke(fake, "update", "--work", name, payload={
                    "version": updated["version"], "tracking": "track",
                    "fields": {"status": "完成", "updated": COMPLETED_AT}})
                self.assertEqual((code, done["status"], done["archived"]), (0, "ok", True), done)
                self.assert_flagged_after_detection(fake)

    def assert_not_established(self, code: int, result: dict, cause: str, name: str, choice: str, completed: bool):
        self.assertEqual(code, 2, result)
        self.assertEqual((result["status"], result["code"], result["cause_code"], result["tracking"], result["state"]),
                         ("partial", "tracking-failed", cause, "error", "saved"))
        path = self.directory / name
        self.assertTrue(path.is_file(), "the saved work must stay in place")
        self.assertEqual(result["saved_version"], sha256(path.read_bytes()))
        recovery = result["recovery"]
        self.assertIn("2.45.0", recovery)
        self.assertIn("remove the promisor configuration", recovery)
        self.assertIn("Do not retry", recovery)
        if completed:
            self.assertIn("not archived", recovery)
            self.assertIn(f'archive using {{"version": "<current version>", "tracking": "{choice}"}}', recovery)
        else:
            self.assertIn(f'update using the current version and {{"tracking": "{choice}"}}', recovery)
            self.assertNotIn("archive", recovery)

    def check_not_established(self, make_fake, cause: str):
        for completed in (False, True):
            for choice in ("default", "track"):
                with self.subTest(completed=completed, choice=choice):
                    self.saves = getattr(self, "saves", 0) + 1
                    fake, name = make_fake(), f"{cause}-{choice}-{int(completed)}-{self.saves}.md"
                    fields = {**FIELDS, "updated": COMPLETED_AT, **({"status": "完成"} if completed else {})}
                    code, result = self.invoke(fake, "create", "--work", name,
                                               payload={"title": "w", "fields": fields, "tracking": choice})
                    self.assert_not_established(code, result, cause, name, choice, completed)
                    self.assertFalse(self.ignore.exists(), "tracking must write nothing")
                    self.assertFalse((self.directory / "history.md").exists())
                    for flagged, rest in fake.commands():
                        self.assertFalse(flagged, rest)
                        self.assertNotIn(rest[0], OBJECT_READS, f"{rest} can read objects")
                    if completed:
                        fake.reset()
                        code, archived = self.invoke(fake, "archive", "--work", name,
                                                     payload={"version": result["version"], "tracking": choice})
                        self.assertEqual((code, archived["status"], archived["code"], archived["cause_code"]),
                                         (2, "partial", "tracking-failed", cause), archived)
                        self.assertTrue(archived["archived"])
                        self.assertIn("do not retry archive", archived["recovery"])
                        self.assertIn("2.45.0", archived["recovery"])
                        self.assertIn("remove the promisor configuration", archived["recovery"])
                        self.assertFalse((self.directory / name).exists())
                        self.assertFalse(self.ignore.exists())
                        self.assertFalse(any(rest[0] in OBJECT_READS for _, rest in fake.commands()))
                        (self.directory / "history.md").unlink()

    def test_old_git_with_a_promisor_remote_reads_no_object(self):
        for version in ("git version 2.44.9", "git version 2.43.0.windows.1"):
            with self.subTest(version=version):
                self.check_not_established(lambda: FakeGit(self.project, version=version), "promisor-remote")

    def test_unknown_configuration_or_version_reads_no_object(self):
        for label, make in (("config", lambda: FakeGit(self.project, config_code=1)),
                            ("version", lambda: FakeGit(self.project, version="git version ?"))):
            with self.subTest(label):
                self.check_not_established(make, "promisor-unknown")

    def test_without_a_promisor_remote_commands_carry_no_flag(self):
        fake = FakeGit(self.project, version="git version 2.43.0", config="remote.origin.url\nfile:///x\0")
        code, created = self.invoke(fake, "create", "--work", "w.md", payload={"title": "w", "fields": FIELDS})
        self.assertEqual((code, created["tracking"]), (0, "ignored"), created)
        self.assertNotIn((False, ["version"]), fake.commands())
        self.assertTrue(all(not flagged for flagged, _ in fake.commands()))

    def test_a_default_save_under_the_track_marker_needs_no_detection(self):
        # It reads no object and writes nothing, so it keeps reporting existing-rule even on an older Git.
        self.ignore.write_bytes(f"{MARKER}\n".encode("utf-8"))
        fake = FakeGit(self.project, version="git version 2.43.0")
        code, created = self.invoke(fake, "create", "--work", "w.md", payload={"title": "w", "fields": FIELDS})
        self.assertEqual((code, created["tracking"]), (0, "existing-rule"), created)
        self.assertEqual(fake.commands(), [(False, ["rev-parse", "--is-inside-work-tree"])])


SHOW_REF = ["show-ref", "--verify", "--quiet", "refs/heads/main"]
OBSERVATION_START = [(False, ["rev-parse", "--is-inside-work-tree"]), (False, ["symbolic-ref", "--quiet", "HEAD"]),
                     (False, ["rev-parse", "--verify", "--quiet", "HEAD"])]


class ObservationGit(FakeGit):
    """FakeGit that also answers the snapshot and compare observation: HEAD names refs/heads/main, which does not
    resolve (an unborn branch) unless head_code is 0, so the observation reaches its show-ref check."""

    def __init__(self, project: Path, head_code=1, **kwargs):
        super().__init__(project, **kwargs)
        self.head_code = head_code

    def __call__(self, args, **kwargs):
        flagged, rest = self.split(list(args))
        if flagged and (git_version(self.version) or (0, 0, 0)) < (2, 45, 0):
            return super().__call__(args, **kwargs)  # refuses the flag, as an older Git would
        if rest == ["symbolic-ref", "--quiet", "HEAD"]:
            self.calls.append(list(args))
            return subprocess.CompletedProcess(args, 0, "refs/heads/main\n", "")
        if rest == ["rev-parse", "--verify", "--quiet", "HEAD"]:
            self.calls.append(list(args))
            return subprocess.CompletedProcess(args, self.head_code, "1" * 40 + "\n" if not self.head_code else "", "")
        if rest == SHOW_REF:
            self.calls.append(list(args))
            return subprocess.CompletedProcess(args, 1, "", "")
        return super().__call__(args, **kwargs)


class SimulatedObservationPromisorTest(unittest.TestCase):
    """C4 item 7: the snapshot and compare observation runs show-ref --verify, which checks that the ref's object
    exists and so can fetch it, only after the promisor-remote detection. On Git 2.45.0 or later it carries
    --no-lazy-fetch; on an older Git, or when the configuration or version cannot be established, it does not run
    and the Git observation is unknown with the cause as its reason. Detection runs only before show-ref."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(os.path.realpath(temporary.name))
        stand_in_git(self)
        self.addCleanup(storage.reset_roots)

    def observe(self, fake: FakeGit) -> dict:
        with mock.patch.object(storage.subprocess, "run", side_effect=fake):
            return observations.git_observation(self.project)

    def test_new_git_runs_show_ref_with_the_flag_after_detection(self):
        for version in ("git version 2.45.0", "git version 2.47.1.windows.1", "git version 3.0.0"):
            with self.subTest(version=version):
                fake = ObservationGit(self.project, version=version)
                self.assertEqual(self.observe(fake), {"state": "available", "head": None, "branch": "main"})
                self.assertEqual(fake.commands(), [*OBSERVATION_START, (False, CONFIG_READ), (False, ["version"]),
                                                   (True, SHOW_REF)])

    def test_old_git_with_a_promisor_remote_does_not_run_show_ref(self):
        for version in ("git version 2.44.9", "git version 2.43.0.windows.1"):
            with self.subTest(version=version):
                fake = ObservationGit(self.project, version=version)
                self.assertEqual(self.observe(fake), {"state": "unknown", "reason": "promisor-remote"})
                self.assertEqual(fake.commands(), [*OBSERVATION_START, (False, CONFIG_READ), (False, ["version"])])

    def test_unknown_configuration_or_version_does_not_run_show_ref(self):
        for label, fake in (("config", ObservationGit(self.project, config_code=1)),
                            ("version", ObservationGit(self.project, version="git version ?"))):
            with self.subTest(label):
                self.assertEqual(self.observe(fake), {"state": "unknown", "reason": "promisor-unknown"})
                self.assertNotIn(SHOW_REF, [rest for _, rest in fake.commands()])

    def test_without_a_promisor_remote_show_ref_carries_no_flag(self):
        fake = ObservationGit(self.project, version="git version 2.43.0", config="remote.origin.url\nfile:///x\0")
        self.assertEqual(self.observe(fake), {"state": "available", "head": None, "branch": "main"})
        self.assertEqual(fake.commands(), [*OBSERVATION_START, (False, CONFIG_READ), (False, SHOW_REF)])

    def test_a_resolved_head_needs_no_detection(self):
        # rev-parse and symbolic-ref read no object, so an observation that never reaches show-ref reads no
        # configuration, even on an older Git in a promisor checkout.
        fake = ObservationGit(self.project, head_code=0, version="git version 2.43.0")
        self.assertEqual(self.observe(fake), {"state": "available", "head": "1" * 40, "branch": "main"})
        self.assertEqual(fake.commands(), OBSERVATION_START)

    def test_git_failing_during_detection_is_git_unavailable(self):
        for error in (FileNotFoundError("git"), subprocess.TimeoutExpired(["git"], 5)):
            fake = ObservationGit(self.project)

            def failing(args, **kwargs):
                if args[PREFIX_LENGTH + 2:] == CONFIG_READ:
                    raise error
                return fake(args, **kwargs)
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(storage.subprocess, "run", side_effect=failing):
                self.assertEqual(observations.git_observation(self.project),
                                 {"state": "unknown", "reason": "git-unavailable"})
            self.assertNotIn(SHOW_REF, [rest for _, rest in fake.commands()])

    def invoke(self, fake: FakeGit, *args, payload=None) -> tuple[int, dict]:
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["handoff", "--project", str(self.project), "--exact-root", *args]), \
                mock.patch.object(cli, "input_payload", return_value=payload), \
                mock.patch.object(storage.subprocess, "run", side_effect=fake), contextlib.redirect_stdout(out):
            code = cli.main()
        return code, json.loads(out.getvalue())

    def test_snapshot_and_compare_report_the_unknown_git_observation(self):
        (self.project / "a.txt").write_bytes(b"a\n")
        plain = lambda: ObservationGit(self.project, config="remote.origin.url\nfile:///x\0")  # noqa: E731
        code, snapshot = self.invoke(plain(), "snapshot", payload={"paths": ["a.txt"]})
        self.assertEqual((code, snapshot["snapshot"]["git"]), (0, {"state": "available", "head": None,
                                                                    "branch": "main"}), snapshot)
        code, created = self.invoke(plain(), "create", "--work", "w.md",
                                    payload={"title": "w", "fields": FIELDS, "snapshot": snapshot["snapshot"]})
        self.assertEqual((code, created["status"]), (0, "ok"), created)
        old = lambda: ObservationGit(self.project, version="git version 2.43.0")  # noqa: E731
        code, partial = self.invoke(old(), "snapshot", payload={"paths": ["a.txt"]})
        self.assertEqual((code, partial["status"], partial["complete"]), (2, "partial", False), partial)
        self.assertEqual(partial["snapshot"]["git"], {"state": "unknown", "reason": "promisor-remote"})
        self.assertEqual(partial["issues"], [{"path": "", "code": "promisor-remote"}])
        self.assertEqual(partial["snapshot"]["files"], snapshot["snapshot"]["files"])
        code, compared = self.invoke(old(), "compare", "--work", "w.md")
        self.assertEqual((code, compared["status"], compared["git"]["comparison"]), (2, "partial", "unknown"),
                         compared)
        self.assertEqual(compared["git"]["current_observation"], {"state": "unknown", "reason": "promisor-remote"})
        self.assertEqual(compared["issues"], [{"path": "", "code": "git-unknown"}])
        self.assertEqual([item["comparison"] for item in compared["files"]], ["unchanged"])


class PromisorReferenceTest(unittest.TestCase):
    """C4 item 7: the handoff tool reference's Create section describes the cause codes the tool returns."""

    def test_create_section_describes_the_promisor_cause_codes(self):
        text = (ROOT / "skills/handoff/references/tool.md").read_text(encoding="utf-8")
        create = text[text.index("\n## Create\n"):text.index("\n## Update and completion\n")]
        for phrase in ("`cause_code: promisor-remote`", "`cause_code: promisor-unknown`", "`--no-lazy-fetch`",
                       "2.45.0", "`extensions.partialClone`", "`remote.<name>.promisor`",
                       "`remote.<name>.partialclonefilter`", "the user removes the promisor configuration", "not to retry"):
            self.assertIn(phrase, create)


class PartialCloneTest(unittest.TestCase):
    """C4 item 7, the refuted case as a regression and abuse check: a blob-less partial clone through a local file://
    URL, sparse so the root .gitignore blob is missing, whose local configuration names a marker program as the
    remote's upload program. A plain check-ignore runs it (positive control); none of the tool's operations does."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temporary.cleanup)
        self.root = Path(os.path.realpath(temporary.name))
        self.marker = self.root / "marker"
        (self.root / "home").mkdir()
        empty = self.root / "gitconfig"
        empty.write_bytes(b"")
        # Isolated from the user's global and system Git configuration; no inherited GIT_* variable reaches Git.
        self.env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
        self.env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty), "HOME": str(self.root / "home"),
                         "XDG_CONFIG_HOME": str(self.root / "home")})
        self.upload = self.root / "upload.sh"
        self.upload.write_text(f'#!/bin/sh\necho upload >> "{self.marker.as_posix()}"\nexit 1\n', encoding="utf-8",
                               newline="\n")
        self.upload.chmod(0o755)

    def git(self, cwd: Path, *args, check=True) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(["git", *args], cwd=cwd, env={**self.env, **COMMIT_ENV}, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            self.skipTest(f"Git cannot be run: {error}")
        if check and result.returncode:
            self.skipTest(f"this Git cannot set up the partial clone: {args}: {result.stderr.strip()}")
        return result

    def partial_clone(self) -> Path:
        source = self.root / "source"
        source.mkdir()
        self.git(source, "-c", "core.fsmonitor=", "init", "--quiet", "--initial-branch=main", ".")
        self.git(source, "config", "uploadpack.allowFilter", "true")
        self.git(source, "config", "uploadpack.allowAnySHA1InWant", "true")
        (source / ".gitignore").write_bytes(b"*.log\n")
        (source / "keep").mkdir()
        (source / "keep/a.txt").write_bytes(b"a\n")
        self.git(source, "-c", "core.fsmonitor=", "add", "--", ".gitignore", "keep/a.txt")
        self.git(source, "-c", "core.fsmonitor=", "-c", "commit.gpgSign=false", "commit", "--quiet", "--no-verify",
                 "-m", "fixture")
        clone = self.root / "clone"
        posix = source.as_posix()
        url = "file://" + (posix if posix.startswith("/") else "/" + posix)
        self.git(self.root, "-c", "core.fsmonitor=", "clone", "--quiet", "--filter=blob:none", "--no-checkout", url,
                 str(clone))
        self.git(clone, "-c", "core.fsmonitor=", "sparse-checkout", "set", "--no-cone", "/keep/")
        self.git(clone, "-c", "core.fsmonitor=", "checkout", "--quiet", "main")
        if (clone / ".gitignore").exists():
            self.skipTest("the sparse checkout kept the root .gitignore")
        self.git(clone, "config", "remote.origin.uploadpack", self.upload.as_posix())
        return clone

    def ran(self) -> bool:
        found = self.marker.exists()
        self.marker.unlink(missing_ok=True)
        return found

    def run_tool(self, repo: Path, *args, payload=None) -> tuple[int, dict]:
        result = subprocess.run([sys.executable, "-B", str(TOOL), "--project", str(repo), *args],
                                input=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else b"",
                                capture_output=True, timeout=60, env=self.env)
        stdout = result.stdout.decode("utf-8")
        self.assertIn(result.returncode, {0, 2}, stdout + result.stderr.decode("utf-8", "replace"))
        return result.returncode, json.loads(stdout)

    def installed_version(self) -> tuple[int, int, int] | None:
        return git_version(self.git(self.root, "version").stdout)

    def test_no_operation_fetches_lazily_from_the_promisor_remote(self):
        clone = self.partial_clone()
        self.assertFalse(self.ran())
        # Positive control: the plain tracking command, without the tool, lazily fetches and runs the upload program.
        self.git(clone, "-c", "core.fsmonitor=", "check-ignore", "-q", "--", ".feather/handoffs/w.md", check=False)
        if not self.ran():
            self.skipTest("this Git ran no configured upload program for a lazy fetch")
        version = self.installed_version()
        if version is None:
            self.skipTest("the installed Git version cannot be read")
        old = version < (2, 45, 0)

        def step(label: str, *args, payload=None) -> tuple[int, dict]:
            outcome = self.run_tool(clone, *args, payload=payload)
            self.assertFalse(self.ran(), f"{label} ran the remote's upload program")
            return outcome

        code, listed = step("list", "list")
        self.assertEqual(listed["status"], "missing")
        code, snapshot = step("snapshot", "snapshot", payload={"paths": ["keep/a.txt"]})
        self.assertEqual(snapshot["snapshot"]["git"]["state"], "available")
        for choice in ("default", "track"):
            name = f"{choice}.md"
            code, created = step(f"create {choice}", "create", "--work", name,
                                 payload={"title": "w", "fields": FIELDS, "tracking": choice,
                                          "snapshot": snapshot["snapshot"]})
            self.assertTrue((clone / ".feather/handoffs" / name).is_file(), created)
            if old:
                self.assertEqual((code, created["status"], created["code"], created["cause_code"]),
                                 (2, "partial", "tracking-failed", "promisor-remote"), created)
                self.assertIn("Do not retry", created["recovery"])
                self.assertFalse((clone / ".gitignore").exists(), "tracking must write nothing")
            else:
                self.assertNotIn(created.get("cause_code"), {"promisor-remote", "promisor-unknown"}, created)
                # Follow-ups C4 item 8: on Git 2.45.0 or later the save itself succeeds, not only without the cause.
                self.assertEqual((code, created["status"]), (0, "ok"), created)
            code, updated = step(f"update {choice}", "update", "--work", name,
                                 payload={"version": created["version"], "tracking": choice,
                                          "fields": {"next": "m", "updated": UPDATED}})
            if old:
                self.assertEqual((code, updated["cause_code"]), (2, "promisor-remote"), updated)
            else:
                self.assertEqual((code, updated["status"]), (0, "ok"), updated)
            code, compared = step(f"compare {choice}", "compare", "--work", name)
            self.assertEqual(compared["git"]["comparison"], "unchanged", compared)
        code, done = step("complete", "create", "--work", "done.md", payload={
            "title": "done", "fields": {**FIELDS, "updated": COMPLETED_AT, "status": "完成"}})
        if old:
            self.assertEqual((code, done["cause_code"]), (2, "promisor-remote"), done)
            code, archived = step("archive", "archive", "--work", "done.md", payload={"version": done["version"]})
            self.assertEqual((code, archived["archived"], archived["cause_code"]), (2, True, "promisor-remote"))
        else:
            # A completed save archives itself when nothing fails: the work is removed and history holds its entry.
            self.assertEqual((code, done["status"], done["archived"]), (0, "ok", True), done)
            self.assertFalse((clone / ".feather/handoffs/done.md").exists(), done)
            history = (clone / ".feather/handoffs/history.md").read_text(encoding="utf-8")
            self.assertIn(f"## done · 完成：{COMPLETED_AT}", history)
        step("read", "read", "--work", "default.md")

    def test_the_observation_show_ref_does_not_fetch_lazily(self):
        # The observation reaches show-ref --verify only when HEAD names a branch that rev-parse cannot resolve; in
        # a probe of on-disk states, every such state made show-ref read no object. The fixture therefore stands in
        # for a concurrent writer: once the observation's rev-parse has found the branch unborn, the branch is
        # created pointing to a blob the partial clone lacks, so show-ref would have to fetch it.
        clone = self.partial_clone()
        listed = self.git(clone, "-c", "core.fsmonitor=", "ls-tree", "HEAD", "--", ".gitignore").stdout.split()
        self.assertFalse(self.ran(), "reading the tree fetched an object")
        if len(listed) < 3:
            self.skipTest("the fixture's root .gitignore is not in the tree")
        blob, ref = listed[2], clone / ".git/refs/heads/side"
        self.git(clone, "-c", "core.fsmonitor=", "symbolic-ref", "HEAD", "refs/heads/side")
        # Positive control: the plain show-ref of a branch at the missing blob runs the remote's upload program.
        ref.write_text(blob + "\n", encoding="utf-8", newline="\n")
        self.git(clone, "-c", "core.fsmonitor=", "show-ref", "--verify", "--quiet", "refs/heads/side", check=False)
        if not self.ran():
            self.skipTest("this Git ran no configured upload program for a lazy fetch")
        version = self.installed_version()
        if version is None:
            self.skipTest("the installed Git version cannot be read")
        real = subprocess.run

        def observe(**patches) -> tuple[dict, list[list[str]]]:
            ref.unlink(missing_ok=True)
            calls = []

            def concurrent(args, **kwargs):
                calls.append(list(args))
                result = real(args, **kwargs)
                if list(args[-4:]) == ["rev-parse", "--verify", "--quiet", "HEAD"] and result.returncode == 1:
                    ref.write_text(blob + "\n", encoding="utf-8", newline="\n")
                return result
            with mock.patch.dict(os.environ, self.env, clear=True), \
                    mock.patch.object(storage.subprocess, "run", side_effect=concurrent), \
                    contextlib.ExitStack() as stack:
                for name, value in patches.items():
                    stack.enter_context(mock.patch.object(observations, name, value))
                return observations.git_observation(clone), calls

        # Second positive control: without the detection, the observation's own show-ref runs the upload program,
        # so the interleaving reaches the command under test.
        _, calls = observe(lazy_fetch_guard=lambda directory: False)
        self.assertIn("show-ref", [call[-4] for call in calls])
        self.assertTrue(self.ran(), "the fixture did not reach a show-ref that fetches")
        observed, calls = observe()
        self.assertFalse(self.ran(), "the observation ran the remote's upload program")
        self.assertEqual(observed["state"], "unknown", observed)
        show_refs = [call for call in calls if call[-4:] == ["show-ref", "--verify", "--quiet", "refs/heads/side"]]
        if version < (2, 45, 0):
            self.assertEqual(observed, {"state": "unknown", "reason": "promisor-remote"})
            self.assertEqual(show_refs, [])
        else:
            self.assertEqual([call[PREFIX_LENGTH] for call in show_refs], ["--no-lazy-fetch"])

    def test_an_included_promisor_declaration_counts(self):
        # A repository with every object present whose local configuration includes a file declaring a promisor
        # remote: the detection follows the include. Git 2.45.0 or later reads with the flag and succeeds.
        repo = self.root / "repo"
        repo.mkdir()
        self.git(repo, "-c", "core.fsmonitor=", "init", "--quiet", "--initial-branch=main", ".")
        included = self.root / "included.gitconfig"
        included.write_text('[remote "origin"]\n\tpromisor = true\n', encoding="utf-8", newline="\n")
        self.git(repo, "config", "include.path", included.as_posix())
        version = self.installed_version()
        code, created = self.run_tool(repo, "create", "--work", "w.md", payload={"title": "w", "fields": FIELDS})
        self.assertTrue((repo / ".feather/handoffs/w.md").is_file())
        if version is None or version < (2, 45, 0):
            self.assertEqual((code, created["cause_code"]), (2, "promisor-remote"), created)
            self.assertFalse((repo / ".gitignore").exists())
        else:
            self.assertEqual((code, created["status"], created["tracking"]), (0, "ok", "ignored"), created)


if __name__ == "__main__":
    unittest.main()
