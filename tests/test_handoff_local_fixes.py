"""Local handoff fixes that are not part of the inherited upstream tests."""
import contextlib
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_handoff_storage import skewed_fstat

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/handoff/scripts"
TOOL = SCRIPTS / "handoff.py"
sys.path.insert(0, str(SCRIPTS))

from feather_handoff import cli, history, history_mutations, observations, storage, tracking  # noqa: E402

COMPLETED = "2026-09-11T10:00:00+08:00"
FAKE = "## Bar · 完成：2020-01-01T00:00:00+00:00"
MARKER = "# cc-feather: track /.feather/handoffs/"
FIELDS = {"goal": "g", "progress": "p", "next": "n"}


def record(title="Foo", status="完成", updated=COMPLETED, details="證據。", eol="\n", heading=None):
    text = (f"# {heading or title}\n更新：{updated}\n狀態：{status}\n目標：g\n進度：p\n下一步：n\n"
            f"\n## 詳細紀錄\n{details}\n")
    return text.replace("\n", eol).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalFixesBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(os.path.realpath(self.temp.name))
        self.directory = self.project / ".feather/handoffs"
        self.directory.mkdir(parents=True)
        self.history = self.directory / "history.md"

    def run_tool(self, *args, payload=None, raw=None, expected=0) -> dict:
        data = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        result = subprocess.run([sys.executable, "-B", str(TOOL), "--project", str(self.project), *args],
                                input=data, capture_output=True, timeout=30)
        stdout = result.stdout.decode("utf-8")
        self.assertEqual(result.returncode, expected, stdout + result.stderr.decode("utf-8", "replace"))
        return json.loads(stdout)

    def put(self, name: str, data: bytes) -> Path:
        path = self.directory / name
        path.write_bytes(data)
        return path

    def archive(self, name: str, data: bytes | None = None, expected=0) -> dict:
        data = self.put(name, data).read_bytes() if data is not None else (self.directory / name).read_bytes()
        return self.run_tool("archive", "--work", name, payload={"version": sha(data)}, expected=expected)

    def invoke(self, *args, payload=None) -> tuple[int, dict]:
        self.addCleanup(storage.reset_roots)
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["handoff", "--project", str(self.project), *args]), \
                mock.patch.object(cli, "input_payload", return_value=payload), contextlib.redirect_stdout(out):
            code = cli.main()
        return code, json.loads(out.getvalue())

    def tree(self) -> dict:
        return {p.relative_to(self.project).as_posix(): p.read_bytes()
                for p in self.project.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.project).parts}


class CompletedBodyTest(LocalFixesBase):
    def test_create_completed_with_fake_history_heading_writes_nothing(self):
        payload = {"title": "Foo", "fields": {"updated": COMPLETED, "status": "完成", "goal": "g",
                                              "progress": "p", "next": "n"},
                   "details": f"x\n{FAKE}\ny"}
        result = self.run_tool("create", "--work", "a.md", payload=payload, expected=2)
        self.assertEqual(result["code"], "format")
        self.assertFalse((self.directory / "a.md").exists())
        self.assertFalse(self.history.exists())

    def test_active_work_with_fake_heading_saves_but_cannot_become_completed(self):
        payload = {"title": "Foo", "fields": {"updated": COMPLETED, "goal": "g", "progress": "p", "next": "n"},
                   "details": f"x\n{FAKE}\ny"}
        self.run_tool("create", "--work", "a.md", payload=payload)
        path = self.directory / "a.md"
        before = path.read_bytes()
        result = self.run_tool("update", "--work", "a.md", expected=2,
                               payload={"version": sha(before), "fields": {"status": "完成"}})
        self.assertEqual(result["code"], "format")
        self.assertEqual(path.read_bytes(), before)
        self.assertIn("狀態：進行中", before.decode("utf-8"))
        self.assertFalse(self.history.exists())

    def test_title_line_whitespace_archives_with_the_stripped_title(self):
        for name, heading in (("a.md", "Foo  "), ("b.md", " Bar")):
            self.put(name, record(title=heading.strip(), heading=heading, updated=COMPLETED if name == "a.md"
                                  else "2026-09-12T10:00:00+08:00"))
            result = self.archive(name)
            self.assertEqual(result["title"], heading.strip())
            self.assertFalse((self.directory / name).exists())
        text = self.history.read_text(encoding="utf-8")
        self.assertIn(f"## Foo · 完成：{COMPLETED}\n", text)
        entries = self.run_tool("history")["entries"]
        self.assertEqual({entry["title"] for entry in entries}, {"Foo", "Bar"})

    def test_stuck_completed_work_reports_replacement_path_and_can_be_repaired(self):
        stuck = record(details=f"x\n{FAKE}\ny")
        path = self.put("a.md", stuck)
        result = self.archive("a.md", expected=2)
        self.assertEqual(result["code"], "format")
        self.assertIn("replacement", result["message"])
        self.assertIn(FAKE, result["message"])
        self.assertFalse(self.history.exists())
        self.assertEqual(path.read_bytes(), stuck)

        fixed = record(details="x\nBar reworded\ny")
        report = self.run_tool("update", "--work", "a.md",
                               payload={"version": sha(stuck), "replacement": fixed.decode("utf-8")})
        self.assertTrue(report["archived"])
        self.assertFalse(path.exists())
        self.assertIn(b"Bar reworded", self.history.read_bytes())

    def test_replacement_of_completed_work_must_keep_identity_and_status(self):
        original = record()
        path = self.put("a.md", original)
        refused = {
            "updated": record(updated="2026-09-12T10:00:00+08:00"),
            "title": record(title="Other"),
            "status": record(status="進行中"),
        }
        for label, replacement in refused.items():
            with self.subTest(label):
                result = self.run_tool("update", "--work", "a.md", expected=2,
                                       payload={"version": sha(original), "replacement": replacement.decode("utf-8")})
                self.assertEqual(result["code"], "completed")
                self.assertEqual(path.read_bytes(), original)
        result = self.run_tool("update", "--work", "a.md", expected=2,
                               payload={"version": sha(original), "fields": {"progress": "q"}})
        self.assertEqual(result["code"], "completed")
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(self.history.exists())

    def test_replacement_is_refused_when_history_already_holds_the_identity(self):
        stuck = record(details=f"x\n{FAKE}\ny")
        path = self.put("a.md", stuck)
        self.history.write_bytes(f"# 交接歷史\n\n## Foo · 完成：{COMPLETED}\nbody\n".encode("utf-8"))
        history_before = self.history.read_bytes()
        result = self.run_tool("update", "--work", "a.md", expected=2,
                               payload={"version": sha(stuck), "replacement": record().decode("utf-8")})
        self.assertEqual(result["code"], "completed")
        self.assertEqual(path.read_bytes(), stuck)
        self.assertEqual(self.history.read_bytes(), history_before)


class CliContractTest(LocalFixesBase):
    def test_invalid_stdin_is_an_input_error(self):
        for label, raw in (("bracket", b"["), ("deep", b"[" * 100000), ("not-utf8", b"\xff\xfe\x00{")):
            with self.subTest(label):
                result = self.run_tool("clear", raw=raw, expected=2)
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["code"], "input")

    def test_unexpected_exception_becomes_internal_json_error(self):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["handoff", "--project", str(self.project), "list"]), \
                mock.patch.object(cli, "list_work", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stdout(out):
            code = cli.main()
        result = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual((result["status"], result["code"]), ("error", "internal"))
        self.assertEqual(result["message"], "RuntimeError: boom")

    def test_missing_file_outside_the_project_is_an_io_error(self):
        # HF5: only the project's own missing files are not-found.
        outside = self.project.parent / f"{self.project.name}-outside" / "absent.md"
        for filename, expected in ((outside, "io"), (self.directory / "gone.md", "not-found")):
            with self.subTest(expected):
                with mock.patch.object(cli, "list_work", side_effect=FileNotFoundError(2, "No such file", str(filename))):
                    code, result = self.invoke("list")
                self.assertEqual((code, result["status"], result["code"]), (2, "error", expected))


class LineEndingTest(LocalFixesBase):
    def test_update_details_follow_the_file_newline(self):
        data = record(status="進行中", eol="\r\n")
        path = self.put("a.md", data)
        self.run_tool("update", "--work", "a.md", payload={"version": sha(data), "details": "a\nb\r\nc\rd"})
        saved = path.read_bytes()
        self.assertIsNone(re.search(rb"(?<!\r)\n", saved))
        self.assertIn(b"a\r\nb\r\nc\r\nd\r\n", saved)

    def test_crlf_history_gets_crlf_marker_and_round_trips(self):
        previous = "# 交接歷史\r\n\r\n## old · 完成：2026-09-10T00:00:00+00:00\r\nold\r\n".encode("utf-8")
        self.history.write_bytes(previous)
        work = record(eol="\r\n")
        result = self.archive("a.md", work)
        self.assertEqual(self.history.read_bytes(),
                         previous + f"## Foo · 完成：{COMPLETED}\r\n".encode("utf-8") + work.split(b"\r\n", 1)[1])
        entries = self.run_tool("history")["entries"]
        self.assertEqual([entry["title"] for entry in entries], ["old", "Foo"])
        self.assertEqual(entries[1]["id"], result["id"])

    def test_new_history_stays_lf(self):
        self.archive("a.md", record(eol="\r\n"))
        self.assertTrue(self.history.read_bytes().startswith("# 交接歷史\n\n".encode("utf-8")))
        self.assertIn(f"## Foo · 完成：{COMPLETED}\n".encode("utf-8"), self.history.read_bytes())

    def test_crlf_separator_after_unterminated_body_is_accepted_on_retry(self):
        self.history.write_bytes("# 交接歷史\r\n\r\n".encode("utf-8"))
        first = record(title="A", eol="\n").rstrip(b"\n")
        self.archive("a.md", first)
        self.archive("b.md", record(title="B", updated="2026-09-12T10:00:00+08:00"))
        saved = self.history.read_bytes()
        self.assertIn(first.split(b"\n", 1)[1] + b"\r\n## B", saved)
        retry = self.archive("a.md", first)
        self.assertFalse(retry["history_appended"])
        self.assertFalse((self.directory / "a.md").exists())
        self.assertEqual(self.history.read_bytes(), saved)


class SmallFixesTest(LocalFixesBase):
    def test_clear_defers_with_pending_archive_for_identical_body(self):
        work = record()
        body = work.split(b"\n", 1)[1]
        self.history.write_bytes(f"# 交接歷史\n\n## Foo · 完成：{COMPLETED}\n".encode("utf-8") + body)
        before = self.history.read_bytes()
        self.put("a.md", work)
        entry = self.run_tool("history")["entries"][0]
        result = self.run_tool("clear", expected=2,
                               payload={"version": entry["document_version"], "ids": [entry["id"]]})
        self.assertEqual(result["code"], "pending-archive")
        self.assertEqual(self.history.read_bytes(), before)
        (self.directory / "a.md").unlink()
        cleared = self.run_tool("clear", payload={"version": entry["document_version"], "ids": [entry["id"]]})
        self.assertEqual(cleared["status"], "ok")

    def test_superscript_com_and_lpt_names_are_reserved(self):
        for name in ("COM¹.md", "com².md", "LPT³", "COM1.md"):
            with self.subTest(name), self.assertRaises(storage.HandoffError) as raised:
                storage.legal_name(name)
            self.assertEqual(raised.exception.code, "unsafe-name")
        storage.legal_name("COM10.md")

    def test_unavailable_inode_does_not_flag_distinct_sources_as_duplicates(self):
        (self.project / "a.txt").write_text("a", encoding="utf-8")
        (self.project / "b.txt").write_text("b", encoding="utf-8")
        self.addCleanup(storage.reset_roots)
        zero_inode = lambda info, **kwargs: (info.st_dev, 0, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns)
        with mock.patch.object(observations, "signature", zero_inode), \
                mock.patch.object(observations, "git_observation", return_value={"state": "not-repository"}):
            result = observations.capture(storage.Store(str(self.project), exact_root=True),
                                          {"paths": ["a.txt", "b.txt"]})
        self.assertNotIn("duplicate-source", json.dumps(result))
        self.assertEqual([item["state"] for item in result["snapshot"]["files"]], ["present", "present"])

    def test_history_byte_offsets_match_prefix_encoding_with_bom_and_multibyte_text(self):
        text = ("# 交接歷史\n\n## 一 · 完成：2026-09-01T00:00:00+00:00\n內容 😀 é\n"
                "## two · 完成：2026-09-02T00:00:00+00:00\r\nbody\r\n"
                "## 三 · 完成：2026-09-03T00:00:00+00:00\n結尾")
        for bom in (b"", b"\xef\xbb\xbf"):
            data = bom + text.encode("utf-8")
            document = history.parse_history(storage.Snapshot(self.directory / "history.md", data))
            self.assertEqual(len(document.entries), 3)
            for entry in document.entries:
                for offset, expected in ((entry.start, entry.byte_start), (entry.body_start, entry.byte_body_start),
                                         (entry.end, entry.byte_end)):
                    self.assertEqual(expected, len(bom) + len(text[:offset].encode("utf-8")))
                self.assertEqual(entry.content_bytes.decode("utf-8"), entry.content)
                self.assertEqual(entry.body_bytes.decode("utf-8"), entry.body)


class DetailsSectionsTest(LocalFixesBase):
    """H1: a details update never hides or changes the sections that follow it."""

    def test_details_that_would_hide_a_sibling_are_refused_then_closed_fence_keeps_it(self):
        self.run_tool("create", "--work", "a.md", payload={"title": "Foo", "fields": FIELDS, "details": "old"})
        path = self.directory / "a.md"
        path.write_bytes(path.read_bytes() + b"\n## Notes\nKEEP\n")
        before = path.read_bytes()
        result = self.run_tool("update", "--work", "a.md", expected=2,
                               payload={"version": sha(before), "details": "```text\nexample"})
        self.assertEqual(result["code"], "details-format")
        self.assertIn("## Notes", result["message"])
        self.assertEqual(path.read_bytes(), before)
        saved = self.run_tool("update", "--work", "a.md",
                              payload={"version": sha(before), "details": "```text\nexample\n```"})
        self.assertEqual(saved["preserved_sections"], ["## Notes"])
        self.assertTrue(path.read_text(encoding="utf-8").endswith("## 詳細紀錄\n```text\nexample\n```\n## Notes\nKEEP\n"))

    def test_plain_details_update_reports_preserved_sections(self):
        data = record(status="進行中") + b"\n## Notes\nKEEP\n"
        path = self.put("a.md", data)
        saved = self.run_tool("update", "--work", "a.md", payload={"version": sha(data), "details": "new evidence"})
        self.assertEqual(saved["preserved_sections"], ["## Notes"])
        self.assertNotIn("warnings", saved)
        self.assertTrue(path.read_bytes().endswith(b"new evidence\n## Notes\nKEEP\n"))

    def test_level_two_heading_inside_details_is_reported_without_refusal(self):
        created = self.run_tool("create", "--work", "a.md",
                                payload={"title": "Foo", "fields": FIELDS, "details": "a\n## 附錄\nb"})
        self.assertEqual(created["status"], "ok")
        self.assertEqual(len(created["warnings"]), 1)
        self.assertIn("'## 附錄' starts a separate section", created["warnings"][0])
        fenced = self.run_tool("create", "--work", "b.md",
                               payload={"title": "Bar", "fields": FIELDS, "details": "```text\n## 附錄\n```\n### Sub"})
        self.assertNotIn("warnings", fenced)
        updated = self.run_tool("update", "--work", "a.md", payload={"version": created["version"], "details": "c\n# X\nd"})
        self.assertEqual(updated["preserved_sections"], ["## 附錄"])
        self.assertEqual(len(updated["warnings"]), 1)

    def test_open_fence_that_shifts_repeated_sibling_headings_is_refused(self):
        # HF3: equal heading texts at other positions still mean the tail was re-interpreted.
        tail = "## Notes\nKEEP\n## Appendix\n```\n## Notes\n## Appendix\n```\n"
        data = record(status="進行中") + tail.encode("utf-8")
        path = self.put("a.md", data)
        result = self.run_tool("update", "--work", "a.md", expected=2,
                               payload={"version": sha(data), "details": "example\n```text"})
        self.assertEqual(result["code"], "details-format")
        self.assertIn("## Notes, ## Appendix", result["message"])
        self.assertEqual(path.read_bytes(), data)


class CompletionArchiveFailureTest(LocalFixesBase):
    """H2: an archival failure after the completed work was saved is a partial result."""

    BROKEN = "# 交接歷史\n\nmanual preamble\n## old · 完成：2026-09-10T00:00:00+00:00\nold\n".encode("utf-8")

    def check_partial(self, result):
        path = self.directory / "a.md"
        self.assertEqual((result["status"], result["code"], result["cause_code"]), ("partial", "archive-failed", "history-format"))
        self.assertFalse(result["complete"])
        self.assertEqual(result["recovery"], "retry-archive")
        self.assertEqual(Path(result["work_path"]), path)
        self.assertEqual(result["saved_version"], sha(path.read_bytes()))
        self.assertEqual(result["version"], result["saved_version"])
        self.assertIn("狀態：完成", path.read_text(encoding="utf-8"))
        self.assertEqual(self.history.read_bytes(), self.BROKEN)

    def test_create_and_update_completion_report_archive_failure_then_retry_succeeds(self):
        self.history.write_bytes(self.BROKEN)
        completed = {"title": "Foo", "fields": {**FIELDS, "updated": COMPLETED, "status": "完成"}}
        self.check_partial(self.run_tool("create", "--work", "a.md", payload=completed, expected=2))
        (self.directory / "a.md").unlink()
        created = self.run_tool("create", "--work", "a.md", payload={"title": "Foo", "fields": {**FIELDS, "updated": COMPLETED}})
        result = self.run_tool("update", "--work", "a.md", expected=2,
                               payload={"version": created["version"], "fields": {"status": "完成"}})
        self.check_partial(result)
        self.history.write_bytes(self.BROKEN.replace(b"manual preamble\n", b""))
        retried = self.run_tool("archive", "--work", "a.md", payload={"version": result["saved_version"]})
        self.assertTrue(retried["archived"])
        self.assertFalse((self.directory / "a.md").exists())


class TrackingMarkerTest(LocalFixesBase):
    """H3: an explicit track choice is recorded as a Git-inert comment and survives default saves."""

    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True, capture_output=True)
        self.ignore = self.project / ".gitignore"

    def index(self) -> bytes:
        return subprocess.run(["git", "-c", f"safe.directory={self.project.as_posix()}", "-C", str(self.project),
                               "ls-files"], capture_output=True, check=True).stdout

    def test_track_records_marker_and_later_default_update_keeps_it(self):
        created = self.run_tool("create", "--work", "a.md", payload={"fields": FIELDS, "tracking": "track"})
        self.assertEqual(created["tracking"], "track")
        self.assertEqual(self.ignore.read_bytes(), (MARKER + "\n").encode())
        updated = self.run_tool("update", "--work", "a.md", payload={"version": created["version"], "fields": {"next": "m"}})
        self.assertEqual(updated["tracking"], "existing-rule")
        self.assertEqual(self.ignore.read_bytes(), (MARKER + "\n").encode())
        self.assertEqual(self.index(), b"")

    def test_track_replaces_rule_with_marker_in_one_write_and_keeps_crlf(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)):
                self.ignore.write_bytes(f"*.log{newline}/.feather/handoffs/{newline}".encode())
                self.addCleanup(storage.reset_roots)
                store = storage.Store(str(self.project))
                with mock.patch.object(tracking, "replace_file", wraps=tracking.replace_file) as replaced, \
                        mock.patch.object(tracking, "create_file", wraps=tracking.create_file) as created:
                    self.assertEqual(tracking.ensure_tracking(store, "a.md", "track"), "track")
                self.assertEqual(replaced.call_count + created.call_count, 1)
                self.assertEqual(self.ignore.read_bytes(), f"*.log{newline}{MARKER}{newline}".encode())
                self.assertEqual(tracking.ensure_tracking(store, "a.md", "default"), "existing-rule")
                self.assertEqual(self.ignore.read_bytes(), f"*.log{newline}{MARKER}{newline}".encode())
        self.assertEqual(self.index(), b"")

    def test_broader_ignore_rule_still_blocks_tracking(self):
        self.ignore.write_bytes(b".feather/\n")
        result = self.run_tool("create", "--work", "a.md", payload={"fields": FIELDS, "tracking": "track"}, expected=2)
        self.assertEqual((result["code"], result["cause_code"]), ("tracking-failed", "tracking-blocked"))
        self.assertEqual(self.ignore.read_bytes(), f".feather/\n{MARKER}\n".encode())
        self.assertTrue((self.directory / "a.md").is_file())
        self.assertEqual(self.index(), b"")


class GitEnvironmentTest(LocalFixesBase):
    """HF2: inherited Git variables cannot redirect the root or output; user configuration still applies."""

    DROPPED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
               "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_IMPLICIT_WORK_TREE", "GIT_PREFIX",
               "GIT_GRAFT_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_SHALLOW_FILE", "GIT_CONFIG",
               "GIT_REDIRECT_STDIN", "GIT_REDIRECT_STDOUT", "GIT_REDIRECT_STDERR")
    KEPT = {"GIT_CONFIG_PARAMETERS": "'core.excludesfile'='user-excludes'", "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.excludesFile", "GIT_CONFIG_VALUE_0": "user-excludes",
            "GIT_CONFIG_GLOBAL": "user-global", "GIT_CONFIG_SYSTEM": "user-system", "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": "user-home", "XDG_CONFIG_HOME": "user-xdg", "USERPROFILE": "user-profile",
            "GIT_CEILING_DIRECTORIES": "user-ceiling", "GIT_DISCOVERY_ACROSS_FILESYSTEM": "1"}

    def test_git_environment_drops_routing_and_redirection_and_keeps_user_configuration(self):
        with mock.patch.dict(os.environ, {**dict.fromkeys(self.DROPPED, "inherited"), **self.KEPT}):
            environment = storage.git_environment()
        self.assertEqual([key for key in self.DROPPED if key in environment], [])
        self.assertEqual({key: environment.get(key) for key in self.KEPT}, self.KEPT)
        self.assertEqual((environment["GIT_OPTIONAL_LOCKS"], environment["LC_ALL"]), ("0", "C"))

    @unittest.skipUnless(os.name == "nt", "GIT_REDIRECT_STDOUT is a Git for Windows feature")
    def test_inherited_output_redirection_cannot_select_the_working_directory_as_root(self):
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True, capture_output=True)
        nested = self.project / "nested"
        nested.mkdir()
        redirected = self.directory / "redirected.txt"
        previous = os.getcwd()
        os.chdir(nested)
        self.addCleanup(os.chdir, previous)
        self.addCleanup(storage.reset_roots)
        with mock.patch.dict(os.environ, {"GIT_REDIRECT_STDOUT": str(redirected)}):
            store = storage.Store(str(nested))
        self.assertEqual((store.root["state"], store.project), ("git", self.project))
        self.assertFalse(redirected.exists())

    def test_user_git_configuration_variables_still_decide_default_tracking(self):
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True, capture_output=True)
        config = tempfile.TemporaryDirectory()
        self.addCleanup(config.cleanup)
        home = Path(os.path.realpath(config.name))
        (home / "global").write_bytes(b"")
        excludes = home / "excludes"
        excludes.write_bytes(b"/.feather/\n")
        # Isolate global, system and XDG ignore files so only the variables below can ignore the handoffs.
        isolated = {"GIT_CONFIG_GLOBAL": str(home / "global"), "GIT_CONFIG_NOSYSTEM": "1", "XDG_CONFIG_HOME": str(home)}
        user = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.excludesFile",
                "GIT_CONFIG_VALUE_0": excludes.as_posix()}
        self.addCleanup(storage.reset_roots)
        store = storage.Store(str(self.project))
        with mock.patch.dict(os.environ, {**isolated, **user}):
            self.assertEqual(tracking.ensure_tracking(store, "a.md", "default"), "existing-rule")
        self.assertFalse((self.project / ".gitignore").exists())
        with mock.patch.dict(os.environ, isolated):
            self.assertEqual(tracking.ensure_tracking(store, "a.md", "default"), "ignored")
        self.assertEqual((self.project / ".gitignore").read_bytes(), b"/.feather/handoffs/\n")


class PendingUnknownTest(LocalFixesBase):
    """H4/HX6: a work that may be an unfinished archival blocks clear and seal as pending-unknown; a malformed
    work whose title is on the first line and whose only status line reads 進行中 or 受阻 is reported instead.
    HP1: a well-formed work with more than one status line or a merge-conflict marker line also blocks them."""

    HISTORY = f"# 交接歷史\n\n## Foo · 完成：{COMPLETED}\nbody\n".encode("utf-8")
    SELECTIONS = (("clear", {}), ("seal", {"destination": "batch.md"}))

    def payload(self, extra: dict) -> dict:
        entry = self.run_tool("history")["entries"][0]
        return {"version": entry["document_version"], "ids": [entry["id"]], **extra}

    def assert_pending_unknown(self, name: str, reasons: str):
        for command, extra in self.SELECTIONS:
            with self.subTest(work=name, command=command):
                self.history.write_bytes(self.HISTORY)
                (self.directory / "archive" / "batch.md").unlink(missing_ok=True)
                before = self.tree()
                result = self.run_tool(command, expected=2, payload=self.payload(extra))
                self.assertEqual(result["code"], "pending-unknown")
                self.assertTrue(result["message"].endswith(
                    f"{name}: {reasons}; cannot rule out an unfinished archival"), result["message"])
                self.assertEqual(self.tree(), before)

    def test_work_that_may_be_completed_blocks_clear_and_seal_as_pending_unknown(self):
        old = ("# Old\n更新：2026-09-10T10:00:00+08:00\n狀態：完成\n目標：g\n進度：p\n下一步：n\n")
        new = old.replace("# Old", "# New").replace("狀態：完成", "狀態：進行中")
        cases = {
            "completed.md": record(title="Other", updated="2026-09-11T10:00:00"),
            "duplicate.md": record(title="Other", status="進行中").replace(
                "狀態：進行中".encode(), "狀態：進行中\n狀態：進行中".encode()),
            "conflict.md": f"<<<<<<< ours\n{new}=======\n{old}>>>>>>> theirs\n".encode("utf-8"),
            "untitled.md": record(title="Other", status="進行中").split(b"\n", 1)[1],
        }
        self.history.write_bytes(self.HISTORY)
        for name, data in cases.items():
            path = self.put(name, data)
            before = self.tree()
            for command, extra in self.SELECTIONS:
                with self.subTest(work=name, command=command):
                    result = self.run_tool(command, expected=2, payload=self.payload(extra))
                    self.assertEqual(result["code"], "pending-unknown")
                    self.assertIn(name, result["message"])
                    self.assertIn("cannot rule out an unfinished archival", result["message"])
                    self.assertEqual(self.tree(), before)
            path.unlink()

    def test_malformed_unfinished_work_is_reported_without_blocking_clear_or_seal(self):
        # Expectation change: a readable 進行中 work with a zone-less timestamp used to return pending-unknown.
        cases = {
            "legacy.md": (record(title="Other", status="進行中", updated="2026-09-11T10:00:00"),
                          "Invalid ISO timestamp with timezone"),
            "baseline.md": (record(title="Other", status="受阻") + "\n## 檔案基準\n```json\n{bad}\n```\n".encode("utf-8"),
                            "Expecting property name"),
        }
        for name, (data, problem) in cases.items():
            work = self.put(name, data)
            for command, extra in self.SELECTIONS:
                with self.subTest(work=name, command=command):
                    self.history.write_bytes(self.HISTORY)
                    result = self.run_tool(command, payload=self.payload(extra))
                    self.assertEqual(result["status"], "ok")
                    self.assertEqual(len(result["warnings"]), 1)
                    self.assertIn(name, result["warnings"][0])
                    self.assertIn(problem, result["warnings"][0])
                    self.assertEqual(work.read_bytes(), data)
                    self.assertEqual(self.history.read_bytes(), "# 交接歷史\n\n".encode("utf-8"))
                    (self.directory / "archive" / "batch.md").unlink(missing_ok=True)
            work.unlink()

    def test_reported_work_is_still_rechecked_before_writing(self):
        self.history.write_bytes(self.HISTORY)
        self.put("legacy.md", record(title="Other", status="進行中", updated="2026-09-11T10:00:00"))
        with mock.patch.object(history_mutations, "require_current", wraps=history_mutations.require_current) as checked:
            code, result = self.invoke("clear", payload=self.payload({}))
        self.assertEqual((code, result["status"]), (0, "ok"))
        self.assertIn("legacy.md", [call.args[0].path.name for call in checked.call_args_list])

    def test_second_status_line_in_a_well_formed_work_blocks_clear_and_seal(self):
        # The title is on the first line and the header holds one status line, so the summary finds no problem.
        copy = f"# Foo\n更新：{COMPLETED}\n狀態：完成\n目標：g\n進度：p\n下一步：n\n".encode("utf-8")
        cases = {
            "copy.md": record(status="進行中", updated="2026-09-12T10:00:00+08:00", details="new") + copy,
            "indented.md": record(title="Other", status="進行中", details="  狀態：完成"),
            "ascii-colon.md": record(title="Other", status="進行中", details="狀態: 完成"),
            "spaced-colon.md": record(title="Other", status="進行中", details="狀態 ：完成"),
            # Documented cost: a status line under a details heading also blocks until it is reworded.
            "section.md": record(title="Other", status="進行中", details="## 附註\n狀態：完成"),
        }
        for name, data in cases.items():
            path = self.put(name, data)
            self.assert_pending_unknown(name, "more than one status line")
            path.unlink()

    def test_shared_title_merge_conflict_blocks_clear_and_seal(self):
        # Git kept the shared title outside the conflict, which spans 詳細紀錄; the summary reads only one side.
        new = record(status="進行中", updated="2026-09-12T10:00:00+08:00", details="new").split(b"\n", 1)[1]
        old = record(details="old").split(b"\n", 1)[1]
        conflict = b"# Foo\n<<<<<<< ours\n" + new + b"=======\n" + old + b">>>>>>> theirs\n"
        cases = {"conflict.md": conflict, "conflict-crlf.md": b"\xef\xbb\xbf" + conflict.replace(b"\n", b"\r\n")}
        for name, data in cases.items():
            path = self.put(name, data)
            self.assert_pending_unknown(name, "more than one status line; merge-conflict marker line")
            path.unlink()

    def test_merge_marker_with_one_status_line_blocks_clear_and_seal(self):
        cases = {
            "ours.md": record(title="Other", status="進行中", details="<<<<<<< ours\nnew"),
            "base.md": record(title="Other", status="受阻", details="||||||| base\nold"),
            "theirs.md": record(title="Other", status="進行中", details="new\n>>>>>>>", eol="\r\n"),
        }
        for name, data in cases.items():
            path = self.put(name, data)
            self.assert_pending_unknown(name, "merge-conflict marker line")
            path.unlink()

    def test_selected_completed_work_with_a_second_status_line_stays_pending_archive(self):
        # Order guard (passes before HP1 too): the selected completion identity is checked first.
        work = record(details="## 附註\n狀態：完成\n其餘說明")
        self.history.write_bytes(f"# 交接歷史\n\n## Foo · 完成：{COMPLETED}\n".encode("utf-8") + work.split(b"\n", 1)[1])
        self.put("a.md", work)
        before = self.tree()
        for command, extra in self.SELECTIONS:
            with self.subTest(command=command):
                result = self.run_tool(command, expected=2, payload=self.payload(extra))
                self.assertEqual(result["code"], "pending-archive")
                self.assertIn("a.md", result["message"])
                self.assertEqual(self.tree(), before)

    def test_well_formed_unfinished_work_does_not_block_clear_or_seal(self):
        # Guard (passes before HP1 too); the reworded lines and a setext underline are not status or marker lines.
        cases = {
            "plain.md": record(title="Other", status="進行中"),
            "reworded.md": record(title="Other", status="受阻",
                                  details="- 狀態：完成\n> 狀態：完成\n`狀態：完成`\n標題\n======="),
        }
        for name, data in cases.items():
            work = self.put(name, data)
            for command, extra in self.SELECTIONS:
                with self.subTest(work=name, command=command):
                    self.history.write_bytes(self.HISTORY)
                    result = self.run_tool(command, payload=self.payload(extra))
                    self.assertEqual(result["status"], "ok")
                    self.assertNotIn("warnings", result)
                    self.assertEqual(work.read_bytes(), data)
                    self.assertEqual(self.history.read_bytes(), "# 交接歷史\n\n".encode("utf-8"))
                    (self.directory / "archive" / "batch.md").unlink(missing_ok=True)
            work.unlink()


class CliUsageTest(LocalFixesBase):
    """H6: usage errors and missing files keep the JSON contract."""

    def test_usage_errors_and_missing_work_are_json(self):
        for args, code in ((("read",), "usage"), (("unknown",), "usage"), ((), "usage"),
                           (("read", "--work", "absent.md"), "not-found")):
            with self.subTest(args=args):
                result = self.run_tool(*args, raw=b"", expected=2)
                self.assertEqual((result["status"], result["complete"], result["code"]), ("error", False, code))
        result = subprocess.run([sys.executable, "-B", str(TOOL), "--help"], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith(b"usage:"))

    def run_bare(self, *args, expected=0) -> dict:
        result = subprocess.run([sys.executable, "-B", str(TOOL), *args], input=b"", capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout.decode("utf-8"))

    def test_root_options_are_accepted_after_the_command(self):
        self.put("work.md", "# work\n更新：2026-09-11T10:00:00+08:00\n狀態：進行中\n\n目標：g\n進度：p\n下一步：n\n".encode("utf-8"))
        project = str(self.project)
        before = self.run_bare("--project", project, "--exact-root", "list")
        for args in (("list", "--project", project, "--exact-root"),
                     ("--exact-root", "list", "--project", project),
                     ("--project", project, "list", "--exact-root")):
            with self.subTest(args=args):
                self.assertEqual(self.run_bare(*args), before)
        read = self.run_bare("read", "--work", "work.md", "--project", project, "--exact-root")
        self.assertEqual((read["status"], read["root"]["state"]), ("ok", "explicit"))
        self.assertEqual(before["root"]["state"], "explicit")
        for args in (("list",), ("list", "--exact-root")):
            with self.subTest(args=args):
                result = self.run_bare(*args, expected=2)
                self.assertEqual(result["code"], "usage")
                self.assertIn("--project", result["message"])


class FailingWrite:
    def __init__(self, handle):
        self.handle = handle

    def fileno(self):
        return self.handle.fileno()

    def write(self, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    def flush(self):
        self.handle.flush()

    def close(self):
        self.handle.close()


def failing_open(name):
    real = Path.open

    def open_(self, mode="r", *args, **kwargs):
        handle = real(self, mode, *args, **kwargs)
        return FailingWrite(handle) if mode == "xb" and self.name == name else handle
    return open_


class CreateCleanupTest(LocalFixesBase):
    """H7: an interrupted first-time creation leaves no partial file."""

    def test_failed_create_write_leaves_no_work_file(self):
        with mock.patch.object(Path, "open", failing_open("a.md")):
            code, result = self.invoke("create", "--work", "a.md", payload={"fields": FIELDS})
        self.assertEqual((code, result["status"], result["code"]), (2, "error", "io"))
        self.assertFalse((self.directory / "a.md").exists())

    def test_failed_first_history_creation_reports_pending_archive(self):
        work = self.put("a.md", record())
        with mock.patch.object(Path, "open", failing_open("history.md")):
            code, result = self.invoke("archive", "--work", "a.md", payload={"version": sha(work.read_bytes())})
        self.assertEqual((code, result["status"], result["code"]), (2, "partial", "history-save-failed"))
        self.assertFalse(result["history_present"])
        self.assertTrue(result["work_present"])
        self.assertFalse(self.history.exists())
        self.assertEqual(work.read_bytes(), record())

    def test_existing_destination_and_unknown_identity_are_kept(self):
        path = self.put("a.md", b"existing")
        with self.assertRaises(storage.HandoffError) as raised:
            storage.create_file(path, b"new")
        self.assertEqual(raised.exception.code, "exists")
        self.assertEqual(path.read_bytes(), b"existing")
        target = self.directory / "b.md"
        with mock.patch.object(Path, "open", failing_open("b.md")), \
                mock.patch.object(storage.os, "fstat", side_effect=skewed_fstat(st_ino=0)), \
                self.assertRaises(OSError) as failed:
            storage.create_file(target, b"data")
        self.assertEqual(failed.exception.errno, errno.ENOSPC)
        self.assertTrue(target.exists())


class CompletedTrackingRecoveryTest(LocalFixesBase):
    """HX1: a completed save whose tracking failed is recovered with archive, which then applies tracking."""

    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True, capture_output=True)
        self.ignore = self.project / ".gitignore"

    def save_completed(self, name: str, choice: str) -> dict:
        self.ignore.write_bytes(b"\xff")
        payload = {"title": name.removesuffix(".md"), "fields": {**FIELDS, "updated": COMPLETED, "status": "完成"},
                   "tracking": choice}
        saved = self.run_tool("create", "--work", name, payload=payload, expected=2)
        self.assertEqual((saved["status"], saved["code"], saved["state"]), ("partial", "tracking-failed", "saved"))
        self.assertTrue((self.directory / name).is_file())
        return saved

    def test_completed_save_with_tracking_failure_is_archived_and_tracked(self):
        for choice, line, reported in (("default", "/.feather/handoffs/", "ignored"), ("track", MARKER, "track")):
            with self.subTest(choice):
                name = f"{choice}.md"
                saved = self.save_completed(name, choice)
                self.assertIn(f'run archive with {{"version": "<current version>", "tracking": "{choice}"}}',
                              saved["recovery"])
                self.assertNotIn("retry update", saved["recovery"])
                self.assertEqual(saved["version"], sha((self.directory / name).read_bytes()))
                self.ignore.write_bytes(b"# corrected by user\n")
                for invalid in ({"version": saved["version"], "tracking": "always"},
                                {"version": saved["version"], "defer_history": True}):
                    refused = self.run_tool("archive", "--work", name, payload=invalid, expected=2)
                    self.assertEqual(refused["code"], "input")
                    self.assertTrue((self.directory / name).is_file())
                archived = self.run_tool("archive", "--work", name,
                                         payload={"version": saved["version"], "tracking": choice})
                self.assertEqual((archived["status"], archived["archived"], archived["tracking"]),
                                 ("ok", True, reported))
                self.assertFalse((self.directory / name).exists())
                self.assertEqual(self.ignore.read_bytes(), f"# corrected by user\n{line}\n".encode("utf-8"))

    def test_tracking_failure_after_archival_reports_saved_history(self):
        saved = self.save_completed("a.md", "default")
        archived = self.run_tool("archive", "--work", "a.md", payload={"version": saved["version"]}, expected=2)
        self.assertEqual((archived["status"], archived["code"], archived["tracking"]),
                         ("partial", "tracking-failed", "error"))
        self.assertTrue(archived["archived"])
        self.assertFalse(archived["complete"])
        self.assertIn("do not retry archive", archived["recovery"])
        self.assertFalse((self.directory / "a.md").exists())
        self.assertIn(f"## a · 完成：{COMPLETED}\n".encode("utf-8"), self.history.read_bytes())
        self.assertEqual(archived["history_version"], sha(self.history.read_bytes()))
        self.assertEqual(self.ignore.read_bytes(), b"\xff")


class SwallowedDetailsTest(LocalFixesBase):
    """HX2: a details update never drops sections that an unbalanced fence in the old details already hides."""

    BASELINE = ('## 檔案基準\n```json\n{"schema_version": 1, "captured_at": "2026-09-11T10:00:00+08:00", '
                '"git": {"state": "not-repository"}, "files": [{"path": "a.py", "state": "missing"}]}\n```\n')

    def update_details(self, data: bytes, expected: int) -> dict:
        path = self.put("a.md", data)
        result = self.run_tool("update", "--work", "a.md", expected=expected,
                               payload={"version": sha(data), "details": "new evidence"})
        if expected:
            self.assertEqual(path.read_bytes(), data)
        return result

    def test_unclosed_details_fence_over_later_sections_is_refused(self):
        unclosed = record(status="進行中", details="```\nopen")
        cases = {
            "baseline": (unclosed + b"\n" + self.BASELINE.encode("utf-8"), "inside a code fence that also holds"),
            "baseline-and-notes": (unclosed + b"\n" + self.BASELINE.encode("utf-8") + "## 手動備註\nkeep\n".encode(),
                                   "inside a code fence that also holds"),
            "notes": (unclosed + "\n## 手動備註\nkeep\n".encode("utf-8"), "leave a code fence open over"),
        }
        for label, (data, cause) in cases.items():
            with self.subTest(label):
                result = self.update_details(data, expected=2)
                self.assertEqual(result["code"], "details-format")
                self.assertIn(cause, result["message"])
                self.assertIn("## 檔案基準" if label != "notes" else "## 手動備註", result["message"])
                self.assertIn("reviewed replacement", result["message"])

    def test_closed_fenced_example_with_a_heading_is_replaced_normally(self):
        data = record(status="進行中", details="```text\n## X\n```\nmore") + "\n## 手動備註\nkeep\n".encode("utf-8")
        result = self.update_details(data, expected=0)
        self.assertEqual(result["preserved_sections"], ["## 手動備註"])
        self.assertTrue((self.directory / "a.md").read_bytes().endswith(
            "## 詳細紀錄\nnew evidence\n## 手動備註\nkeep\n".encode("utf-8")))

    def test_unclosed_opener_over_a_section_holding_a_bare_code_block_is_refused(self):
        # T2 by design: from the text alone this swallowed section looks like a closed example with a heading
        # followed by an unrelated open fence, so both stay refused rather than risk dropping the section.
        data = (record(status="進行中", details="```text\nopen")
                + "\n## 手動備註\nkeep\n```\ncode\n```\ntail\n".encode("utf-8"))
        result = self.update_details(data, expected=2)
        self.assertEqual(result["code"], "details-format")
        self.assertIn("leave a code fence open over ## 手動備註", result["message"])


class ReadOnlyTargetTest(LocalFixesBase):
    """HX3: a read-only target is reported as such and no temporary file is left behind."""

    def test_read_only_work_is_preserved_without_temporary_files(self):
        data = record(status="進行中")
        path = self.put("a.md", data)
        os.chmod(path, stat.S_IREAD)
        self.addCleanup(os.chmod, path, stat.S_IREAD | stat.S_IWRITE)
        # Elsewhere rename may replace a read-only file, so only Windows reports the refusal.
        windows = os.name == "nt"
        result = self.run_tool("update", "--work", "a.md", expected=2 if windows else 0,
                               payload={"version": sha(data), "fields": {"next": "m"}})
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ["a.md"])
        if windows:
            self.assertEqual((result["status"], result["code"]), ("error", "read-only"))
            self.assertIn("is read-only; existing data preserved", result["message"])
            self.assertEqual(path.read_bytes(), data)


class InputValidationTest(LocalFixesBase):
    """HX4, HX5, HX8, HX10: input that later operations would refuse or lose is rejected or normalized."""

    def test_blank_optional_fields_are_refused_on_create_and_update(self):
        result = self.run_tool("create", "--work", "a.md", expected=2, payload={"fields": {**FIELDS, "notes": "   "}})
        self.assertEqual(result["code"], "input")
        self.assertIn("notes (注意) must not be blank; omit it instead", result["message"])
        self.assertEqual(self.tree(), {})
        required = self.run_tool("create", "--work", "a.md", expected=2, payload={"fields": {**FIELDS, "next": " "}})
        self.assertEqual(required["message"], "Missing or empty next")
        created = self.run_tool("create", "--work", "a.md", payload={"fields": FIELDS})
        path = self.directory / "a.md"
        before = path.read_bytes()
        result = self.run_tool("update", "--work", "a.md", expected=2,
                               payload={"version": created["version"], "fields": {"notes": "  "}})
        self.assertEqual(result["code"], "input")
        self.assertEqual(path.read_bytes(), before)
        updated = self.run_tool("update", "--work", "a.md", payload={"version": created["version"], "fields": {"notes": "real"}})
        self.assertEqual(updated["notes"], "real")

    def test_work_name_without_a_stem_is_refused_and_never_listed(self):
        result = self.run_tool("create", "--work", ".md", expected=2, payload={"fields": FIELDS})
        self.assertEqual(result["code"], "unsafe-name")
        self.assertEqual(self.tree(), {})
        self.put(".md", record(status="進行中"))
        self.put("a.md", record(title="A", status="進行中"))
        self.assertEqual([item["work"] for item in self.run_tool("list")["items"]], ["a.md"])
        self.assertEqual(self.run_tool("read", "--work", ".md", expected=2)["code"], "unsafe-name")

    def test_duplicate_json_keys_on_stdin_are_input_errors(self):
        raw = json.dumps({"fields": FIELDS}).replace('{"fields"', '{"fields": {}, "fields"', 1).encode("utf-8")
        result = self.run_tool("create", "--work", "a.md", raw=raw, expected=2)
        self.assertEqual((result["status"], result["code"]), ("error", "input"))
        self.assertEqual(result["message"], "Duplicate JSON key: fields")
        self.assertEqual(self.tree(), {})

    def test_create_normalizes_details_line_endings(self):
        self.run_tool("create", "--work", "a.md", payload={"fields": FIELDS, "details": "a\r\nb\rc\r\n"})
        saved = (self.directory / "a.md").read_bytes()
        self.assertNotIn(b"\r", saved)
        self.assertTrue(saved.endswith("## 詳細紀錄\na\nb\nc\n".encode("utf-8")))


class EmptyHistoryFramingTest(LocalFixesBase):
    """HX9: archival into an empty or whitespace-only history writes the history header."""

    def test_completed_save_into_blank_history_writes_the_header(self):
        for name, existing in (("a.md", b""), ("b.md", b" \r\n\n")):
            with self.subTest(existing=existing):
                self.history.write_bytes(existing)
                created = self.run_tool("create", "--work", name, payload={
                    "fields": {**FIELDS, "updated": COMPLETED, "status": "完成"}})
                self.assertTrue(created["archived"])
                saved = self.history.read_bytes()
                self.assertTrue(saved.startswith("# 交接歷史\n\n## ".encode("utf-8")))
                self.assertNotIn(b"\r", saved)
                entries = self.run_tool("history")["entries"]
                self.assertEqual([entry["title"] for entry in entries], [name.removesuffix(".md")])


if __name__ == "__main__":
    unittest.main()
