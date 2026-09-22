"""Atomic replacement returns promptly on permission denial and preserves collisions."""
from pathlib import Path
import sys
import tempfile
import os
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/feather-handoff/scripts"))
from feather_handoff import storage


class HandoffStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "work.md"
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
        with patch.dict(os.environ, {"GIT_DIR": str(redirected / ".git"), "GIT_WORK_TREE": str(redirected)}):
            store = storage.Store(str(asked))
            self.assertEqual(store.project, asked.resolve())
            result = capture(store, {"paths": ["source.txt"]})
            self.assertEqual(result["snapshot"]["files"][0]["sha256"], storage.hashlib.sha256(b"asked").hexdigest())
            self.assertEqual(Path(git(store, "rev-parse", "--show-toplevel").stdout.strip()), asked)

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
