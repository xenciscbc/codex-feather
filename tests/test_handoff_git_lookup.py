"""Repository safety follow-ups C4: the handoff tool finds Git only by an absolute path from fully qualified PATH
entries, never through the current directory, and starts it with a cleaned PATH from Git's own directory.

Trust boundary: the process's current directory, which may lie in a repository whose working tree is attacker-
controlled, against the programs the handoff tool starts. PATH is the user's environment and stays trusted (F1);
entries that depend on the current directory or drive, or were never expanded, are not. Every fixture lives in a
scratch directory under the system temporary directory and is removed afterwards."""
import ast
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import shutil
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

WINDOWS = os.name == "nt"
NAME = "git.exe" if WINDOWS else "git"
FIELDS = {"goal": "g", "progress": "p", "next": "n", "updated": "2026-10-11T10:00:00+08:00"}
UPDATED = "2026-10-11T11:00:00+08:00"
COMPLETED_AT = "2026-10-11T12:00:00+08:00"
COMMIT_ENV = {"GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
              "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
              "GIT_AUTHOR_DATE": "2026-10-11T10:00:00+08:00", "GIT_COMMITTER_DATE": "2026-10-11T10:00:00+08:00"}
# The variable that makes Windows leave the current directory out of a bare-name search; the host may set it.
NO_CURRENT_DIRECTORY = "NODEFAULTCURRENTDIRECTORYINEXEPATH"
WINDOWS_ONLY = "a Windows PATH shape; the POSIX rows cover POSIX"
POSIX_ONLY = "a POSIX PATH shape; the Windows rows cover Windows"


def scratch(test: unittest.TestCase) -> Path:
    temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    test.addCleanup(temporary.cleanup)
    return Path(os.path.realpath(temporary.name))


def plant(directory: Path, name: str = NAME, data: bytes = b"MZ", mode: int = 0o755) -> Path:
    """A file the resolver would accept by name; on POSIX `mode` decides whether it is executable."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    path.chmod(mode)
    return path


def qualified(entry: str) -> bool:
    """The test's own statement of a considered PATH entry, written independently of the resolver: on POSIX it
    starts with /, has no `..` component, whose target depends on links before it, and does not lie in /proc or
    /dev/fd, whose paths name something different in every process; on Windows it holds no `:` but its drive
    letter's, and a UNC entry none, since Git's MSYS layer splits a value at such a `:` for the programs it starts,
    and no character in U+F000-U+F0FF, which that layer maps back to `:` and the other characters Windows forbids."""
    if not WINDOWS:
        return (entry.startswith("/") and not re.search(r"(?:^|/)\.\.(?:/|$)", entry)
                and not re.match(r"^/+(?:\./+)*(?:proc|dev/+(?:\./+)*fd)(?:/|$)", entry))
    if any(0xF000 <= ord(character) <= 0xF0FF for character in entry):
        return False
    return bool(re.match(r"^[A-Za-z]:[\\/][^:]*$", entry)
                or re.match(r"^[\\/]{2}(?![?.][\\/])[^\\/:]+[\\/][^\\/:]+[^:]*$", entry))


def isolated_environment(root: Path) -> dict[str, str]:
    """The test's environment without inherited GIT_* variables or the current-directory switch, isolated from the
    user's global and system Git configuration."""
    empty = root / "gitconfig"
    empty.write_bytes(b"")
    (root / "home").mkdir(exist_ok=True)
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith("GIT_") and key.upper() != NO_CURRENT_DIRECTORY}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty), "HOME": str(root / "home"),
                        "XDG_CONFIG_HOME": str(root / "home")})
    return environment


@contextlib.contextmanager
def no_search():
    """Fails the resolver call if it starts a process or asks Python to search for a program."""
    refused = AssertionError("the resolver must not start a process or search for a program")
    with mock.patch.object(storage.subprocess, "run", side_effect=refused), \
            mock.patch.object(subprocess, "Popen", side_effect=refused), \
            mock.patch.object(shutil, "which", side_effect=refused), \
            mock.patch.object(os, "get_exec_path", side_effect=refused):
        yield


class FixedDatetime(datetime):
    """The same capture time in every run, so outputs compare byte for byte rather than normalised."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 11, 10, 0, tzinfo=timezone(timedelta(hours=8)))


class GitResolverSourceTest(unittest.TestCase):
    """C4 item 1: the resolver asks neither the operating system nor Python to search, and adds no default path."""

    def test_the_helper_module_uses_no_search_or_default_path(self):
        source = (SCRIPTS / "feather_handoff" / "storage.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names] + [getattr(node, "module", None) or ""]
                self.assertFalse(any(name.split(".")[0] in {"shutil", "ntpath"} for name in names), names)
            elif isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"which", "get_exec_path", "defpath", "isabs"}, ast.dump(node))


class GitResolverTableTest(unittest.TestCase):
    """C4 item 5: the resolver over PATH values built in a scratch directory, each with its expected result. The
    process's current directory holds a Git, and so does `bin` below it, so every entry that the current directory
    or drive could complete is a live trap rather than a missing directory."""

    def setUp(self):
        self.root = scratch(self)
        self.cwd = self.root / "cwd"
        plant(self.cwd)
        plant(self.cwd / "bin")
        self.good = self.root / "good"
        plant(self.good)
        previous = os.getcwd()
        os.chdir(self.cwd)
        self.addCleanup(os.chdir, previous)

    def resolve(self, value: str | None) -> str | None:
        with no_search():
            try:
                return storage.resolve_git(value)
            except FileNotFoundError as error:
                self.assertEqual(error.errno, 2)
                return None

    def check(self, rows):
        for label, value, expected in rows:
            with self.subTest(label, PATH=value):
                if isinstance(expected, unittest.SkipTest):
                    self.skipTest(str(expected))
                self.assertEqual(self.resolve(value), expected)

    @unittest.skipUnless(WINDOWS, WINDOWS_ONLY)
    def test_windows_entry_shapes(self):
        drive, rooted = os.path.splitdrive(str(self.cwd))
        self.assertTrue(drive and drive[1] == ":", "the scratch directory is not on a drive letter")
        zero = self.root / "zero"
        plant(zero, data=b"")
        (self.root / "dirgit" / NAME).mkdir(parents=True)
        plant(self.root / "cmdonly", "git.cmd", b"@echo off\r\n")
        plant(self.root / "cmdonly", "git.bat", b"@echo off\r\n")
        literal = self.root / "%FEATHER_LOOKUP_DIR%"
        plant(literal)
        good = str(self.good)
        unc = "\\\\localhost\\" + drive[0] + "$" + os.path.splitdrive(good)[1]
        unc_expected = (os.path.join(unc, NAME) if os.path.isfile(os.path.join(unc, NAME))
                        else unittest.SkipTest("the administrative share \\\\localhost\\" + drive[0] + "$ is not reachable"))
        with mock.patch.dict(os.environ, {"FEATHER_LOOKUP_DIR": good}):
            self.check([
                ("drive-relative C:foo, completed by the drive's current directory", drive + "bin", None),
                ("rooted without a drive, \\foo on the current drive", rooted, None),
                (".", ".", None),
                ("an empty entry", "", None),
                ("empty entries only", ";;", None),
                ("relative bin", "bin", None),
                ("quoted entry, one pair of quotes removed", f'"{good}"', os.path.join(good, NAME)),
                ("quoted entry with an empty inside", '""', None),
                ("C:/ with forward slashes", self.good.as_posix(), os.path.join(self.good.as_posix(), NAME)),
                ("trailing separator", good + "\\", good + "\\" + NAME),
                # Windows resolves `..` from the text before following links, so a `..` entry is still considered.
                ("a .. component, resolved from the text", good + "\\..\\good", good + "\\..\\good\\" + NAME),
                ("unexpanded %VAR%", "%FEATHER_LOOKUP_DIR%", None),
                ("fully qualified but unexpanded", str(literal), None),
                ("UNC path", unc, unc_expected),
            ])
            self.check([
                ("\\\\?\\ device path", "\\\\?\\" + good, None),
                ("//?/ device path", "//?/" + self.good.as_posix(), None),
                ("\\\\.\\ device path", "\\\\.\\" + good, None),
                ("a directory named git.exe", str(self.root / "dirgit"), None),
                ("only git.cmd and git.bat", str(self.root / "cmdonly"), None),
                ("a zero-byte git.exe is a regular file", str(zero), str(zero / NAME)),
                ("PATH absent", None, None),
                ("first match wins", f"{good};{zero}", os.path.join(good, NAME)),
                ("first match wins, reversed", f"{zero};{good}", str(zero / NAME)),
                ("every skipped shape before a good entry",
                 ";".join(["", ".", "bin", drive + "bin", rooted, "%FEATHER_LOOKUP_DIR%", str(literal),
                           "\\\\?\\" + good, "\\\\.\\" + good, str(self.root / "dirgit"), str(self.root / "cmdonly"),
                           good]), os.path.join(good, NAME)),
            ])

    @unittest.skipUnless(WINDOWS, WINDOWS_ONLY)
    def test_windows_links_are_followed_but_not_returned(self):
        linked = self.root / "linked"
        linked.mkdir()
        try:
            os.symlink(self.good / NAME, linked / NAME)
            (self.root / "linkdir").mkdir()
            os.symlink(self.root / "dirgit-target", self.root / "linkdir" / NAME, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symbolic links cannot be created here: {error}")
        (self.root / "dirgit-target").mkdir()
        self.check([("a link to a regular git.exe", str(linked), str(linked / NAME)),
                    ("a link to a directory", str(self.root / "linkdir"), None)])

    @unittest.skipUnless(WINDOWS, WINDOWS_ONLY)
    def test_windows_entries_holding_a_colon(self):
        """Regression for the C4 outcome verification finding at 3051676 (D-3): Git for Windows' MSYS layer splits a
        value at every `:` but a drive letter's for the programs it starts, so an entry such as <good>:. would hand
        them `.`. Every Windows entry with a `:` anywhere but right after its drive letter, and every UNC entry with
        a `:`, is skipped, although its first part holds a Git; one whose only `:` is its drive letter's is kept.
        The rows assert the classification itself, since Windows may refuse to open such a path anyway."""
        drive = os.path.splitdrive(str(self.good))[0]
        self.assertTrue(drive and drive[1] == ":", "the scratch directory is not on a drive letter")
        good = str(self.good)
        unc = "\\\\localhost\\" + drive[0] + "$" + os.path.splitdrive(good)[1]
        skipped = [
            ("<good>:., whose good holds git.exe", good + ":."),
            ("<good>: with a trailing colon", good + ":"),
            ("a colon inside the path", good + ":x\\good"),
            ("forward slashes, <good>:.", self.good.as_posix() + ":."),
            ("a lower-case drive letter, <good>:.", drive[0].lower() + good[1:] + ":."),
            ("a quoted <good>:., quotes removed first", f'"{good}:."'),
            ("a UNC entry ending in :.", unc + ":."),
            ("a UNC server name holding a colon", "\\\\localhost:445\\" + drive[0] + "$" + os.path.splitdrive(good)[1]),
            ("a UNC share name holding a colon", "\\\\localhost\\share:x\\good"),
        ]
        kept = [
            ("C:\\... with only its drive letter's colon", good),
            ("C:/... with only its drive letter's colon", self.good.as_posix()),
            ("a lower-case drive letter", drive[0].lower() + good[1:]),
        ]
        for label, entry in skipped:
            with self.subTest(label, PATH=entry):
                self.assertEqual(storage.git_search_path(entry), [])
                self.assertIsNone(self.resolve(entry))
        for label, entry in kept:
            with self.subTest(label, PATH=entry):
                self.assertEqual(storage.git_search_path(entry), [entry])
                self.assertEqual(self.resolve(entry), os.path.join(entry, NAME))
        with self.subTest("every colon entry before a kept one"):
            value = ";".join([entry for _, entry in skipped] + [good])
            self.assertEqual(storage.git_search_path(value), [good])
            self.assertEqual(self.resolve(value), os.path.join(good, NAME))

    @unittest.skipUnless(WINDOWS, WINDOWS_ONLY)
    def test_windows_entries_holding_msys_mapped_characters(self):
        """Regression for Adversarial review call 5 at ddfc2ef (D-3): Git for Windows' MSYS runtime maps the
        private-use characters U+F000-U+F0FF back to the ASCII characters Windows forbids in names, U+F03A to `:`,
        and then splits the value there for the programs it starts. Every Windows entry holding a character in that
        range is skipped; directories so named hold a Git here, so the resolver rows are live traps. An entry with a
        non-ASCII character outside that range is kept."""
        drive = os.path.splitdrive(str(self.good))[0]
        self.assertTrue(drive and drive[1] == ":", "the scratch directory is not on a drive letter")
        good = str(self.good)
        mapped = good + "."
        ends = str(self.root / "endsx")
        cjk = str(self.root / "工具")
        for directory in (mapped, ends, cjk):
            try:
                plant(Path(directory))
            except OSError as error:
                self.skipTest(f"a directory named with a non-ASCII character cannot be created here: {error}")
        skipped = [
            ("<good>U+F03A., a directory holding git.exe", mapped),
            ("<good>U+F03A, a trailing U+F03A", good + ""),
            ("a quoted <good>U+F03A., quotes removed first", f'"{mapped}"'),
            ("a UNC entry \\\\localhost\\share U+F03A.", "\\\\localhost\\share."),
            ("U+F000 and U+F0FF, a directory holding git.exe", ends),
            ("U+F000 alone", str(self.root / "a")),
            ("U+F0FF alone", str(self.root / "a")),
        ]
        for label, entry in skipped:
            with self.subTest(label, PATH=entry):
                self.assertEqual(storage.git_search_path(entry), [])
                self.assertIsNone(self.resolve(entry))
        with self.subTest("a CJK character outside U+F000-U+F0FF is kept", PATH=cjk):
            self.assertEqual(storage.git_search_path(cjk), [cjk])
            self.assertEqual(self.resolve(cjk), os.path.join(cjk, NAME))
        with self.subTest("every mapped entry before a kept one"):
            value = ";".join([entry for _, entry in skipped] + [good])
            self.assertEqual(storage.git_search_path(value), [good])
            self.assertEqual(self.resolve(value), os.path.join(good, NAME))

    @unittest.skipIf(WINDOWS, POSIX_ONLY)
    def test_posix_entry_shapes(self):
        plant(self.root / "noexec", mode=0o644)
        (self.root / "dirtarget").mkdir()
        (self.root / "linkdir").mkdir()
        os.symlink(self.root / "dirtarget", self.root / "linkdir" / NAME)
        (self.root / "linkexe").mkdir()
        os.symlink(self.good / NAME, self.root / "linkexe" / NAME)
        literal = self.root / "$FEATHER_LOOKUP_DIR"
        plant(literal)
        good = str(self.good)
        self.check([
            ("a non-executable git", str(self.root / "noexec"), None),
            ("a symbolic link to a directory", str(self.root / "linkdir"), None),
            ("a symbolic link to an executable, returned as found", str(self.root / "linkexe"),
             str(self.root / "linkexe" / NAME)),
            ("PATH absent", None, None),
            ("an empty entry", "", None),
            ("empty entries only", "::", None),
            (".", ".", None),
            ("relative bin", "bin", None),
            ("quotes are not removed on POSIX", f'"{good}"', None),
            ("fully qualified but unexpanded", str(literal), None),
            ("first match wins", f"{good}:{self.root / 'linkexe'}", str(self.good / NAME)),
            ("every skipped shape before a good entry",
             ":".join(["", ".", "bin", str(self.root / "noexec"), str(self.root / "linkdir"), str(literal), good]),
             str(self.good / NAME)),
        ])

    @unittest.skipIf(WINDOWS, POSIX_ONLY)
    def test_posix_process_namespaces(self):
        """Regression for the Adversarial review finding at 001d047: an entry in /proc or /dev/fd starts with / yet
        names the calling process's current directory (or a directory it has open), which holds a Git here. Every
        spelling of such an entry is skipped, judged from its text without resolving links; a directory merely
        named proc or dev/fd elsewhere is still considered."""
        descriptor = os.open(self.cwd, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        self.addCleanup(os.close, descriptor)
        to_root = "/.." * (len(self.root.parts) - 1)
        climb = "/proc/self/cwd" + "/.." * (len(self.cwd.parts) - 1) + str(self.cwd)
        traps = [
            ("/proc/self/cwd", "/proc/self/cwd"),
            ("/proc/thread-self/cwd", "/proc/thread-self/cwd"),
            ("/proc/<pid>/cwd", f"/proc/{os.getpid()}/cwd"),
            ("//proc//self/cwd, repeated separators", "//proc//self/cwd"),
            ("/proc/./self/cwd", "/proc/./self/cwd"),
            ("a trailing separator", "/proc/self/cwd/"),
            ("/dev/fd/<n> open on the current directory", f"/dev/fd/{descriptor}"),
            ("/dev/./fd//<n>", f"/dev/./fd//{descriptor}"),
            ("/dev/fd/3", "/dev/fd/3"),
            ("climbing from the scratch directory into /proc", str(self.root) + to_root + "/proc/self/cwd"),
            ("climbing out of /proc/self/cwd back to the current directory", climb),
        ]
        # The namespaces themselves are skipped too, though none of them names the current directory.
        inert = {"/dev/fd/3", "/proc", "/proc/", "/dev/fd"}
        traps += [("bare /proc", "/proc"), ("/proc/", "/proc/"), ("bare /dev/fd", "/dev/fd")]
        if sys.platform.startswith("linux") and os.path.isdir("/proc/self/cwd"):
            for label, entry in traps:
                # Each trap naming the current directory is live: a lookup that considered it would find a Git.
                if entry not in inert:
                    self.assertTrue(os.path.isfile(os.path.join(entry, NAME)), f"{label} is not a live trap: {entry}")
        plant(self.root / "proc" / "self" / "cwd")
        plant(self.root / "dev" / "fd")
        good = str(self.good)
        self.check([(label, entry, None) for label, entry in traps] + [
            ("every namespace entry before a good entry", ":".join([entry for _, entry in traps] + [good]),
             str(self.good / NAME)),
            ("a directory named proc elsewhere is considered", str(self.root / "proc" / "self" / "cwd"),
             str(self.root / "proc" / "self" / "cwd" / NAME)),
            ("a directory named dev/fd elsewhere is considered", str(self.root / "dev" / "fd"),
             str(self.root / "dev" / "fd" / NAME)),
        ])
        self.assertEqual(storage.git_search_path(":".join([entry for _, entry in traps] + [good])), [good])

    @unittest.skipIf(WINDOWS, POSIX_ONLY)
    def test_posix_dot_dot_entries(self):
        """Regression for code review call 2 at 79e7c01: the kernel follows a symbolic link before it applies the
        `..` after it, so with /var/run -> /run (Ubuntu, Debian, Fedora) /var/run/../proc/self/cwd is
        /proc/self/cwd, which holds a Git here, although its text walks to /var/proc. Every entry with a `..`
        component is skipped, wherever its text leads, including a directory that holds a Git."""
        climbing = "/var/run/../proc/self/cwd"
        if os.path.islink("/var/run") and os.path.isdir("/proc/self/cwd"):
            # The live trap: a lookup that considered the entry would find the Git planted in the current directory.
            self.assertTrue(os.path.samefile(climbing, self.cwd), f"{climbing} does not name the current directory")
            self.assertTrue(os.path.isfile(os.path.join(climbing, NAME)), f"{climbing} is not a live trap")
        good = str(self.good)
        through_good = good + "/../good"
        self.assertTrue(os.path.isfile(os.path.join(through_good, NAME)))
        plant(self.root / "..good")
        entries = [
            ("/var/run/../proc/self/cwd, through the /var/run link", climbing),
            ("/usr/../usr/bin", "/usr/../usr/bin"),
            ("/proc/self/cwd/../..", "/proc/self/cwd/../.."),
            ("/tmp/../tmp", "/tmp/../tmp"),
            ("a directory holding a Git, reached through ..", through_good),
            ("a trailing ..", good + "/.."),
            ("a .. after repeated separators", good + "//..//good/"),
        ]
        self.check([(label, entry, None) for label, entry in entries] + [
            ("every .. entry before a good entry", ":".join([entry for _, entry in entries] + [good]),
             str(self.good / NAME)),
            ("a component merely starting with .. is considered", str(self.root / "..good"),
             str(self.root / "..good" / NAME)),
        ])
        self.assertEqual(storage.git_search_path(":".join([entry for _, entry in entries] + [good])), [good])

    def test_no_result_is_kept_between_calls(self):
        other = self.root / "other"
        plant(other)
        self.assertEqual(self.resolve(str(self.good)), str(self.good / NAME))
        self.assertEqual(self.resolve(str(other)), str(other / NAME))
        self.assertIsNone(self.resolve(None))
        self.assertEqual(self.resolve(str(self.good)), str(self.good / NAME))

    def test_the_cleaned_path_keeps_exactly_the_considered_entries(self):
        separator = os.pathsep
        good = str(self.good)
        skipped = ["", ".", "bin"] + ([os.path.splitdrive(good)[0] + "bin", os.path.splitdrive(good)[1],
                                       "%FEATHER_LOOKUP_DIR%", "\\\\?\\" + good, "\\\\.\\" + good, good + ":.",
                                       "\\\\localhost\\share:x\\good", good + "."] if WINDOWS
                                      else ["/proc/self/cwd", "//proc//self/cwd/", "/proc/./thread-self/cwd",
                                            "/dev/fd/3", "/var/run/../proc/self/cwd", "/usr/../usr/bin",
                                            good + "/../good"])
        kept = [good, str(self.root / "missing")]
        value = separator.join(skipped[:2] + [f'"{kept[0]}"' if WINDOWS else kept[0]] + skipped[2:] + [kept[1]])
        self.assertEqual(storage.git_search_path(value), kept)
        self.assertEqual(storage.git_search_path(None), [])
        self.assertEqual(storage.git_search_path(""), [])


class InProcessBase(unittest.TestCase):
    """Runs the tool's command line in this process, with the process's working directory holding a planted Git
    that is never the directory passed to -C."""

    def setUp(self):
        self.root = scratch(self)
        self.project = self.root / "project"
        self.project.mkdir()
        self.cwd = self.root / "cwd"
        plant(self.cwd)
        plant(self.cwd / "bin")
        previous = os.getcwd()
        os.chdir(self.cwd)
        self.addCleanup(os.chdir, previous)
        self.addCleanup(storage.reset_roots)
        self.enterContext(mock.patch.object(observations, "datetime", FixedDatetime))

    def invoke(self, args, payload=None, run=None) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["handoff", "--project", str(self.project), *args]), \
                mock.patch.object(cli, "input_payload", return_value=payload), \
                mock.patch.object(storage.subprocess, "run", side_effect=run), contextlib.redirect_stdout(out):
            code = cli.main()
        return code, out.getvalue()

    def tree(self) -> dict[str, bytes]:
        return {path.relative_to(self.project).as_posix(): path.read_bytes()
                for path in sorted(self.project.rglob("*")) if path.is_file()}

    def restore(self, files: dict[str, bytes]) -> None:
        shutil.rmtree(self.project)
        self.project.mkdir()
        for name, data in files.items():
            (self.project / name).parent.mkdir(parents=True, exist_ok=True)
            (self.project / name).write_bytes(data)
        storage.reset_roots()


class NoGitOutputTest(InProcessBase):
    """C4 item 6, no Git: with no Git on PATH, and with PATH absent, every operation's whole output and effect equal
    a baseline recorded by making subprocess.run raise the exception the resolver raises, and no process starts."""

    def setUp(self):
        super().setUp()
        with self.assertRaises(FileNotFoundError) as raised, no_search():
            storage.resolve_git(None)
        original = raised.exception
        self.missing = lambda: type(original)(original.errno, original.strerror, original.filename,  # noqa: E731
                                              getattr(original, "winerror", None))
        self.assertEqual((str(self.missing()), self.missing().args), (str(original), original.args))
        # A PATH without Git, though it holds names a broader lookup would accept.
        self.without = self.root / "nogit"
        if WINDOWS:
            plant(self.without, "git.cmd", b"@echo off\r\n")
            plant(self.without, "git.bat", b"@echo off\r\n")
            (self.without / NAME).mkdir()
        else:
            plant(self.without, mode=0o644)

    def baseline(self, args, **kwargs):
        raise self.missing()

    def refused(self, args, **kwargs):
        self.started.append(list(args))
        raise AssertionError(f"a process started although no Git was resolved: {args}")

    def fixture(self) -> tuple[dict[str, bytes], str, str]:
        (self.project / "a.txt").write_bytes(b"a\n")
        _, snapshot = self.invoke(["--exact-root", "snapshot"], {"paths": ["a.txt"]}, self.baseline)
        _, created = self.invoke(["--exact-root", "create", "--work", "w.md"],
                                 {"title": "w", "fields": FIELDS, "snapshot": json.loads(snapshot)["snapshot"]},
                                 self.baseline)
        _, done = self.invoke(["--exact-root", "create", "--work", "done.md"],
                              {"title": "done", "fields": {**FIELDS, "updated": COMPLETED_AT, "status": "完成"}},
                              self.baseline)
        created, done = json.loads(created), json.loads(done)
        self.assertEqual((created["cause_code"], done["cause_code"]), ("git-unavailable", "git-unavailable"))
        self.assertTrue((self.project / ".feather/handoffs/done.md").is_file())
        return self.tree(), created["version"], done["version"]

    def test_every_operation_reports_what_it_reports_today(self):
        files, version, done = self.fixture()
        operations = [("list", ["list"], None), ("read", ["read", "--work", "w.md"], None),
                      ("snapshot", ["snapshot"], {"paths": ["a.txt"]}), ("compare", ["compare", "--work", "w.md"], None),
                      ("create", ["create", "--work", "new.md"], {"title": "n", "fields": FIELDS}),
                      ("update", ["update", "--work", "w.md"],
                       {"version": version, "fields": {"next": "m", "updated": UPDATED}}),
                      ("archive", ["archive", "--work", "done.md"], {"version": done})]
        for exact in (False, True):
            for label, args, payload in operations:
                args = (["--exact-root"] if exact else []) + args
                with self.subTest(label, exact_root=exact):
                    self.restore(files)
                    expected = self.invoke(args, payload, self.baseline)
                    effect = self.tree()
                    self.assert_today(label, exact, json.loads(expected[1]))
                    for case, environment in (("no Git on PATH", {"PATH": str(self.without)}), ("PATH absent", None)):
                        self.restore(files)
                        self.started = []
                        with mock.patch.dict(os.environ, environment or {}):
                            if environment is None:
                                os.environ.pop("PATH", None)
                            self.assertEqual(self.invoke(args, payload, self.refused), expected, case)
                        self.assertEqual(self.started, [], case)
                        self.assertEqual(self.tree(), effect, case)

    def assert_today(self, label: str, exact: bool, result: dict):
        """What today's handling of a missing Git reports, so the baseline is the documented one."""
        self.assertEqual(result["root"]["state"], "explicit" if exact else "uncertain", result)
        if label == "snapshot":
            self.assertEqual(result["snapshot"]["git"], {"state": "unknown", "reason": "git-unavailable"})
        elif label == "compare":
            self.assertEqual(result["git"]["comparison"], "unknown", result)
        elif label in {"create", "update", "archive"}:
            if exact:
                self.assertEqual((result["code"], result["cause_code"]), ("tracking-failed", "git-unavailable"))
            else:
                self.assertEqual(result["code"], "project-root-uncertain", result)
        elif not exact:  # list and read keep readable results from an uncertain root
            self.assertEqual((result["status"], result["operation_status"]), ("partial", "ok"), result)


class GitCallTest(InProcessBase):
    """C4 item 6, in process: every Git process the tool starts during its operations is the resolver's absolute
    path, runs from that executable's directory, gets a PATH without any skipped entry, and takes an absolute -C
    that is not the process's working directory."""

    def setUp(self):
        super().setUp()
        real_path = os.environ.get("PATH")
        try:
            self.executable = storage.resolve_git(real_path)
        except FileNotFoundError:
            self.skipTest("no Git is found on PATH")
        environment = isolated_environment(self.root)
        try:
            for args in (["init", "--quiet", "--initial-branch=main", "."], ["config", "core.autocrlf", "false"]):
                subprocess.run([self.executable, *args], cwd=self.project, env=environment, check=True,
                               capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as error:
            self.skipTest(f"Git cannot set up the repository: {error}")
        empty = self.root / "empty"
        empty.mkdir()
        if WINDOWS:
            drive, rooted = os.path.splitdrive(str(self.cwd))
            # D-3: an entry whose first part is the working directory, which holds a planted Git, followed by `:.`,
            # and a UNC entry holding a `:`; Git's MSYS layer would split either at that `:` for its children. The
            # same holds for U+F03A, which that layer maps back to `:` (Adversarial review call 5 at ddfc2ef).
            self.skipped = ["", ".", "bin", drive + "bin", rooted, "%FEATHER_LOOKUP_DIR%", "\\\\?\\" + str(self.cwd),
                            "\\\\.\\" + str(self.cwd), str(self.cwd) + ":.", "\\\\localhost\\share:x\\cwd",
                            str(self.cwd) + ".", f'"{empty}"']
        else:
            self.skipped = ["", ".", "bin", "$HOME/bin", "/proc/self/cwd", "//proc//self/cwd/", "/dev/fd/0",
                            "/var/run/../proc/self/cwd", str(self.cwd) + "/../cwd"]
        environment["PATH"] = os.pathsep.join([*self.skipped, real_path or ""])
        self.enterContext(mock.patch.dict(os.environ, environment, clear=True))
        self.expected = storage.resolve_git(os.environ["PATH"])
        self.empty = str(empty)

    def test_every_git_start_uses_the_resolved_path_its_directory_and_a_cleaned_path(self):
        real, calls = subprocess.run, []

        def recorded(args, **kwargs):
            calls.append((list(args), kwargs))
            return real(args, **kwargs)
        (self.project / "a.txt").write_bytes(b"a\n")
        _, snapshot = self.invoke(["snapshot"], {"paths": ["a.txt"]}, recorded)
        _, created = self.invoke(["create", "--work", "w.md"],
                                 {"title": "w", "fields": FIELDS, "snapshot": json.loads(snapshot)["snapshot"]},
                                 recorded)
        created = json.loads(created)
        self.assertEqual((created["status"], created["root"]["state"], created["tracking"]), ("ok", "git", "ignored"),
                         created)
        _, updated = self.invoke(["update", "--work", "w.md"],
                                 {"version": created["version"], "tracking": "track", "fields": {"updated": UPDATED}},
                                 recorded)
        self.assertEqual(json.loads(updated)["status"], "ok", updated)
        for args in (["list"], ["read", "--work", "w.md"], ["compare", "--work", "w.md"]):
            code, output = self.invoke(args, None, recorded)
            self.assertEqual(code, 0, output)
        code, done = self.invoke(["create", "--work", "done.md"],
                                 {"title": "done", "fields": {**FIELDS, "updated": COMPLETED_AT, "status": "完成"}},
                                 recorded)
        self.assertEqual((code, json.loads(done)["archived"]), (0, True), done)
        self.assertTrue(calls)
        self.assertTrue(os.path.isabs(self.expected) and os.path.basename(self.expected).lower() == NAME, self.expected)
        for args, kwargs in calls:
            with self.subTest(args=args[5:]):
                self.assertEqual(args[0], self.expected)
                self.assertEqual(kwargs["cwd"], os.path.dirname(self.expected))
                entries = kwargs["env"]["PATH"].split(os.pathsep)
                self.assertTrue(all(qualified(entry) for entry in entries), entries)
                self.assertFalse(set(self.skipped) & set(entries), entries)
                if WINDOWS:
                    self.assertIn(self.empty, entries, "a quoted entry is kept without its quotes")
                target = args[args.index("-C") + 1]
                self.assertEqual(target, str(self.project))
                self.assertTrue(qualified(target))
                self.assertNotEqual(os.path.normcase(target), os.path.normcase(os.getcwd()))


class PlantedGitTest(unittest.TestCase):
    """C4 item 6 through the tool's command line, as a separate process: a planted Git in the process's working
    directory, which a bare-name start would run, never runs, and the operations report their normal results."""

    def setUp(self):
        self.root = scratch(self)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        self.env = isolated_environment(self.root)

    def git(self, *args):
        try:
            result = subprocess.run(["git", *args], cwd=self.repo, env={**self.env, **COMMIT_ENV},
                                    stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            self.skipTest(f"Git cannot be run: {error}")
        self.assertEqual(result.returncode, 0, (args, result.stderr))
        return result.stdout.decode("utf-8").strip()

    def repository(self) -> str:
        self.git("-c", "core.fsmonitor=", "init", "--quiet", "--initial-branch=main", ".")
        self.git("config", "core.autocrlf", "false")
        (self.repo / "a.txt").write_bytes(b"a\n")
        self.git("-c", "core.fsmonitor=", "add", "--", "a.txt")
        self.git("-c", "core.fsmonitor=", "-c", "commit.gpgSign=false", "commit", "--quiet", "--no-verify", "-m", "f")
        return self.git("rev-parse", "HEAD")

    def bare_name_start(self, program: str = "git") -> subprocess.CompletedProcess:
        """The positive control: a child process with the tool's environment and working directory starts `git
        version` by its bare name, as the tool did before C4, or by the `program` path given."""
        code = ("import subprocess, sys\n"
                "try:\n"
                "    r = subprocess.run([sys.argv[1], 'version'], capture_output=True, timeout=30)\n"
                "except OSError as error:\n"
                "    sys.exit(f'not started: {error}')\n"
                "sys.stdout.buffer.write(r.stdout + r.stderr)\n")
        return subprocess.run([sys.executable, "-I", "-c", code, program], cwd=self.cwd, env=self.env,
                              capture_output=True, timeout=60)

    def run_tool(self, *args, payload=None, expected=0) -> dict:
        result = subprocess.run([sys.executable, "-B", str(TOOL), "--project", str(self.repo), *args], cwd=self.cwd,
                                input=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else b"",
                                capture_output=True, timeout=60, env=self.env)
        stdout = result.stdout.decode("utf-8")
        self.assertEqual(result.returncode, expected, stdout + result.stderr.decode("utf-8", "replace"))
        return json.loads(stdout)

    def operations(self, head: str):
        self.assertNotEqual(os.path.normcase(str(self.cwd)), os.path.normcase(str(self.repo)))
        root = {"requested": str(self.repo), "path": str(self.repo), "state": "git"}
        listed = self.run_tool("list")
        self.assertEqual((listed["status"], listed["root"]), ("missing", root), listed)
        snapshot = self.run_tool("snapshot", payload={"paths": ["a.txt"]})
        self.assertEqual(snapshot["snapshot"]["git"], {"state": "available", "head": head, "branch": "main"})
        created = self.run_tool("create", "--work", "w.md", payload={"title": "w", "fields": FIELDS,
                                                                     "snapshot": snapshot["snapshot"]})
        self.assertEqual((created["status"], created["tracking"], created["root"]), ("ok", "ignored", root), created)
        self.assertIn("/.feather/handoffs/", (self.repo / ".gitignore").read_text(encoding="utf-8"))
        read = self.run_tool("read", "--work", "w.md")
        self.assertEqual((read["status"], read["root"]), ("ok", root), read)
        compared = self.run_tool("compare", "--work", "w.md")
        self.assertEqual(compared["git"]["comparison"], "unchanged", compared)

    @unittest.skipUnless(WINDOWS, "the planted git.exe is the Windows case; the POSIX test plants a marker script")
    def test_windows_planted_git_exe_in_the_working_directory_never_runs(self):
        whoami = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        if not whoami.is_file():
            self.skipTest(f"no {whoami} to plant")
        head = self.repository()
        # whoami only reads; given Git's arguments it exits with an error instead of printing `git version`.
        for directory in (self.cwd, self.cwd / "bin"):
            directory.mkdir(exist_ok=True)
            shutil.copyfile(whoami, directory / NAME)
        self.env["PATH"] = os.pathsep.join(["", ".", "bin", self.env.get("PATH", "")])
        # A copy outside System32 finds no message resources and prints only a blank line, so the control judges
        # that a program started by the bare name and that it was not Git.
        control = self.bare_name_start()
        output = (control.stdout + control.stderr).decode("utf-8", "replace").strip()
        if control.returncode or output.startswith("git version"):
            self.skipTest(f"positive control: a bare-name start in this environment did not run the planted "
                          f"git.exe ({output[:120]!r}); this run cannot show the tool avoids it")
        self.operations(head)

    @unittest.skipIf(WINDOWS, "the marker script is the POSIX case; the Windows test plants whoami.exe")
    def test_posix_planted_git_script_in_the_working_directory_never_runs(self):
        head = self.repository()
        marker = self.root / "marker"
        script = f'#!/bin/sh\necho planted >> "{marker}"\nexit 1\n'.encode("utf-8")
        for directory in (self.cwd, self.cwd / "bin"):
            plant(directory, data=script)
        self.env["PATH"] = os.pathsep.join(["", ".", "bin", self.env.get("PATH", "")])
        self.bare_name_start()
        if not marker.exists():
            self.skipTest("positive control: a bare-name start in this environment did not run the planted script")
        marker.unlink()
        self.operations(head)
        self.assertFalse(marker.exists(), "an operation ran the planted git")

    @unittest.skipIf(WINDOWS, "/proc/self/cwd is a POSIX entry; on Windows a rooted entry without a drive is skipped")
    def test_posix_proc_self_cwd_entry_never_runs_the_planted_git(self):
        """Regression for the Adversarial review finding at 001d047: with PATH=/proc/self/cwd:<real Git's
        directory>, the first entry names the process's current directory, which holds a planted git. A start of
        /proc/self/cwd/git, and a bare-name start over that PATH, run the plant (positive controls); the tool's
        operations run Git from the second entry and never the plant."""
        self.process_entry_never_runs_the_planted_git("/proc/self/cwd")

    @unittest.skipIf(WINDOWS, "a POSIX link before `..`; Windows resolves `..` from the text")
    def test_posix_dot_dot_through_a_link_never_runs_the_planted_git(self):
        """Regression for code review call 2 at 79e7c01: with /var/run -> /run, PATH=/var/run/../proc/self/cwd
        names the process's current directory, because the kernel follows the link before applying `..`."""
        if not os.path.islink("/var/run"):
            self.skipTest("/var/run is not a symbolic link on this system")
        self.process_entry_never_runs_the_planted_git("/var/run/../proc/self/cwd")

    def process_entry_never_runs_the_planted_git(self, entry: str):
        """PATH=<entry>:<real Git's directory>, where <entry> names the process's current directory, which holds a
        planted git: starting <entry>/git, and a bare-name start over that PATH, run the plant (positive controls);
        the tool's operations run Git from the second entry and never the plant."""
        if not os.path.isdir("/proc/self/cwd"):
            self.skipTest("this system has no /proc/self/cwd")
        try:
            real = storage.resolve_git(self.env.get("PATH"))
        except FileNotFoundError:
            self.skipTest("no Git is found on PATH")
        head = self.repository()
        marker = self.root / "marker"
        plant(self.cwd, data=f'#!/bin/sh\necho planted >> "{marker}"\nexit 1\n'.encode("utf-8"))
        self.env["PATH"] = os.pathsep.join([entry, os.path.dirname(real)])
        for program in (entry + "/git", "git"):
            self.bare_name_start(program)
            if not marker.exists():
                self.skipTest(f"positive control: starting {program} here did not run the planted script")
            marker.unlink()
        self.operations(head)
        self.assertFalse(marker.exists(), "an operation ran the planted git")


class GitExecPathTest(unittest.TestCase):
    """Adopted with the 001d047 finding: an inherited GIT_EXEC_PATH that is not a considered entry would make Git,
    after -C, look up its git-* programs relative to the project or through the current directory, so the helper's
    Git processes do not get it; a considered one, the user's own, reaches Git unchanged. The value is judged as is:
    on Windows a quoted value is dropped, although a quoted PATH entry is considered without its quotes, and a value
    holding a path separator is dropped, because Git puts it before its children's PATH, and so is a Windows value
    with a `:` other than its drive letter's, at which Git's MSYS layer splits it, or with a character in
    U+F000-U+F0FF, which that layer maps back to `:` and the other characters Windows forbids.
    git_environment itself, which other code uses, is unchanged."""

    def setUp(self):
        self.root = scratch(self)
        plant(self.root / "tools")
        self.enterContext(mock.patch.dict(os.environ, {"PATH": str(self.root / "tools")}))
        self.addCleanup(storage.reset_roots)

    def started_with(self, value: str | None) -> str | None:
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.dict(os.environ), mock.patch.object(storage.subprocess, "run", return_value=completed) as run:
            os.environ.pop("GIT_EXEC_PATH", None)
            if value is not None:
                os.environ["GIT_EXEC_PATH"] = value
                self.assertEqual(storage.git_environment().get("GIT_EXEC_PATH"), value)
            storage.run_git(self.root, "rev-parse", "--is-inside-work-tree")
        self.assertEqual(run.call_count, 1)
        return run.call_args.kwargs["env"].get("GIT_EXEC_PATH")

    def test_a_relative_exec_path_is_dropped_and_a_fully_qualified_one_kept(self):
        kept = str(self.root / "libexec")
        dropped = ["", ".", "libexec", "./libexec", "../libexec"]
        if WINDOWS:
            drive, rooted = os.path.splitdrive(kept)
            dropped += [drive + "libexec", rooted, "%FEATHER_EXEC%", "\\\\?\\" + kept, f'"{kept}"']
        else:
            dropped += ["$HOME/libexec", "/proc/self/cwd", "//proc/./self/cwd/", "/dev/fd/3",
                        "/var/run/../proc/self/cwd", "/usr/../usr/libexec/git-core", kept + "/../libexec",
                        "/tmp/../tmp"]
        # Regression for code review call 4 at f265e54: Git puts GIT_EXEC_PATH before its children's PATH, so a
        # considered first entry followed by a path separator would hand them `.` (the project after -C), `..` or
        # /proc/self/cwd; a value holding a path separator is dropped whatever its entries are.
        dropped += [kept + ";."] if WINDOWS else [kept + ":.", kept + ":/proc/self/cwd", kept + ":.."]
        if WINDOWS:
            # Regression for the C4 outcome verification finding at 3051676 (D-3): Git's MSYS layer splits the
            # value at a `:` other than the drive letter's for the programs it starts, handing them `.`.
            dropped += [kept + ":.", kept + ":", Path(kept).as_posix() + ":.", "\\\\localhost\\share:x\\libexec"]
            # Regression for Adversarial review call 5 at ddfc2ef: that layer maps U+F03A back to `:` first.
            dropped += [kept + ".", kept + ""]
        for value in dropped:
            with self.subTest("dropped", GIT_EXEC_PATH=value):
                self.assertIsNone(self.started_with(value))
        with self.subTest("kept"):
            self.assertEqual(self.started_with(kept), kept)
        if WINDOWS:
            with self.subTest("kept, forward slashes"):
                self.assertEqual(self.started_with(Path(kept).as_posix()), Path(kept).as_posix())
        with self.subTest("absent stays absent"):
            self.assertIsNone(self.started_with(None))


if __name__ == "__main__":
    unittest.main()
