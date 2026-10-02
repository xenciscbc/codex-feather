"""Atomic replacement returns promptly on permission denial and preserves collisions."""
from pathlib import Path
import sys
import tempfile
import os
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/handoff/scripts"))
from feather_handoff import storage


def skewed_fstat(**overrides):
    real_fstat = os.fstat

    def fstat(fd):
        info = real_fstat(fd)
        fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
        return SimpleNamespace(**{**fields, **overrides})
    return fstat


class HandoffStorageTest(unittest.TestCase):
    def test_windows_read_accepts_stable_ctime_difference_between_apis(self):
        fstat = os.fstat
        def changed_ctime(fd):
            info = fstat(fd)
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            values["st_ctime_ns"] += 1_000_000_000
            return SimpleNamespace(**values)
        with patch.object(storage.sys, "platform", "win32"), patch.object(os, "fstat", side_effect=changed_ctime):
            self.assertEqual(storage.read_file(self.path).data, b"original")

    def test_read_detects_descriptor_changes_even_with_windows_ctime_offset(self):
        fstat = os.fstat
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_nlink"):
            calls = 0
            def changed(fd):
                nonlocal calls
                calls += 1
                info = fstat(fd)
                values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                values["st_ctime_ns"] += 1_000_000_000
                if calls % 2 == 0:
                    values[field] += 1
                return SimpleNamespace(**values)
            with self.subTest(field=field), patch.object(sys, "platform", "win32"), patch.object(os, "fstat", side_effect=changed):
                with self.assertRaises(storage.HandoffError) as caught:
                    storage.read_file(self.path)
                self.assertEqual(caught.exception.code, "changed")

    def test_posix_cross_api_ctime_difference_is_rejected(self):
        fstat = os.fstat
        def changed(fd):
            info = fstat(fd)
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            values["st_ctime_ns"] += 1_000_000_000
            return SimpleNamespace(**values)
        with patch.object(sys, "platform", "linux"), patch.object(os, "fstat", side_effect=changed):
            with self.assertRaises(storage.HandoffError) as caught:
                storage.read_file(self.path)
            self.assertEqual(caught.exception.code, "changed")

    def test_windows_path_ctime_change_is_rejected(self):
        original_stat = os.stat
        calls = 0
        def changed(path, *args, **kwargs):
            nonlocal calls
            info = original_stat(path, *args, **kwargs)
            if Path(path).name != "work.md" or not kwargs.get("follow_symlinks", True):
                return info
            calls += 1
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            values["st_ctime_ns"] += calls
            return SimpleNamespace(**values)
        with patch.object(sys, "platform", "win32"), patch.object(os, "stat", side_effect=changed):
            with self.assertRaises(storage.HandoffError) as caught:
                storage.read_file(self.path)
            self.assertEqual(caught.exception.code, "changed")

    def test_real_file_write_during_read_is_rejected(self):
        path = self.path
        fstat = os.fstat
        calls = 0
        def write_after_open(fd):
            nonlocal calls
            calls += 1
            info = fstat(fd)
            if calls % 2:
                path.write_bytes(b"changed" * calls)
            return info
        with patch.object(os, "fstat", side_effect=write_after_open):
            with self.assertRaises(storage.HandoffError) as caught:
                storage.read_file(path)
            self.assertEqual(caught.exception.code, "changed")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(os.path.realpath(self.temp.name)) / "work.md"
        self.path.write_bytes(b"original")
        self.original = storage.read_file(self.path)

    def test_permission_denial_is_not_retried(self):
        with patch.object(storage.os, "open", side_effect=PermissionError("sandbox denied")) as opened:
            with self.assertRaises(PermissionError):
                storage.replace_file(self.original, b"new")
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(self.path.read_bytes(), b"original")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_inherited_git_routing_cannot_redirect_project_or_tracking(self):
        from feather_handoff.observations import capture
        from feather_handoff.tracking import git
        parent = self.path.parent
        asked, redirected = parent / "asked", parent / "redirected"
        for project in (asked, redirected):
            project.mkdir()
            subprocess.run(["git", "-C", str(project), "init", "--quiet"], check=True, capture_output=True)
            (project / "source.txt").write_text(project.name, encoding="utf-8")
        self.addCleanup(storage.reset_roots)
        with patch.dict(os.environ, {"GIT_DIR": str(redirected / ".git"), "GIT_WORK_TREE": str(redirected)}):
            store = storage.Store(str(asked))
            self.assertEqual(store.project, asked.resolve())
            result = capture(store, {"paths": ["source.txt"]})
            self.assertEqual(result["snapshot"]["files"][0]["sha256"], storage.hashlib.sha256(b"asked").hexdigest())
            self.assertEqual(Path(git(store, "rev-parse", "--show-toplevel").stdout.strip()), asked)

    def test_ctime_mismatch_between_stat_and_fstat_is_not_a_change(self):
        # Python 3.12+ on Windows: stat() reports creation time, fstat() reports change time.
        with patch.object(sys, "platform", "win32"), patch.object(storage.os, "fstat", side_effect=skewed_fstat(st_ctime_ns=0)):
            self.assertEqual(storage.read_file(self.path).data, b"original")
        with patch.object(storage.os, "fstat", side_effect=skewed_fstat(st_mtime_ns=0)), \
                self.assertRaises(storage.HandoffError):
            storage.read_file(self.path)

    def test_collisions_are_bounded_and_never_deleted(self):
        collision = self.path.parent / ".feather-fixed.tmp"
        collision.write_bytes(b"another writer")
        with patch.object(storage.secrets, "token_hex", return_value="fixed") as names:
            with self.assertRaises(storage.HandoffError) as caught:
                storage.replace_file(self.original, b"new")
        self.assertEqual(caught.exception.code, "temporary-conflict")
        self.assertEqual(names.call_count, 3)
        self.assertEqual(collision.read_bytes(), b"another writer")
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_collision_then_success_keeps_other_writers_file(self):
        collision = self.path.parent / ".feather-fixed.tmp"
        collision.write_bytes(b"another writer")
        with patch.object(storage.secrets, "token_hex", side_effect=["fixed", "fresh"]):
            saved = storage.replace_file(self.original, b"new")
        self.assertEqual(saved.data, b"new")
        self.assertEqual(collision.read_bytes(), b"another writer")
        self.assertFalse((self.path.parent / ".feather-fresh.tmp").exists())


if __name__ == "__main__":
    unittest.main()
