"""Publishing and rollback retain modes; chmod failures do not publish bytes."""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from setup_installer.transaction import Plan, TransactionError, atomic_write


class TransactionModeTests(unittest.TestCase):
    def test_chmod_failure_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "config"
            target.write_bytes(b"original")
            with patch("setup_installer.transaction.os.chmod", side_effect=OSError("chmod denied")):
                with self.assertRaisesRegex(OSError, "chmod denied"):
                    atomic_write(target, b"changed", 0o640)
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["config"])

    def test_chmod_precedes_publish_including_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            if os.name != "nt":
                os.chmod(first, 0o640)
                os.chmod(second, 0o600)
            modes = {p: stat.S_IMODE(p.stat().st_mode) for p in (first, second)}
            plan = Plan()
            plan.add(first, b"new-first")
            plan.add(second, b"new-second")
            chmod, replace = os.chmod, os.replace
            prepared = {}
            published = []

            def track_mode(path, mode):
                chmod(path, mode)
                prepared[str(path)] = mode

            def track_replace(source, target):
                self.assertIn(str(source), prepared)
                if Path(target) in modes:
                    self.assertEqual(prepared[str(source)], modes[Path(target)])
                    if Path(target) == second:
                        raise OSError("publish failed")
                    published.append(Path(source).read_bytes())
                replace(source, target)

            with patch("setup_installer.transaction.os.chmod", side_effect=track_mode), patch(
                    "setup_installer.transaction.os.replace", side_effect=track_replace):
                with self.assertRaises(TransactionError) as error:
                    plan.apply(root / "backups")
            self.assertEqual(error.exception.details["recovery"], "rolled_back")
            self.assertEqual(published, [b"new-first", b"first"])
            for path, expected in modes.items():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected)
            self.assertEqual(first.read_bytes(), b"first")
            self.assertEqual(second.read_bytes(), b"second")
