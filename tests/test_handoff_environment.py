"""Exercise handoff runtime diagnostics through the public installer CLI."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CODEX = os.environ.get("FEATHER_TEST_CODEX") or shutil.which("codex.exe" if os.name == "nt" else "codex")


class HandoffEnvironmentTest(unittest.TestCase):
    def setUp(self):
        runs = ROOT / ".scratch/feather-setup/runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=runs)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.project = self.directory / "project"
        self.project.mkdir()
        self.user_home = self.directory / "user"
        self.codex_home = self.user_home / ".codex"
        self.bundle = self.directory / "bundle"
        skill = self.bundle / "assets/skills/feather-handoff/SKILL.md"
        skill.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "skills/feather-handoff/SKILL.md", skill)
        source = "assets/skills/feather-handoff/SKILL.md"
        self.bundle.joinpath("bundle.json").write_text(json.dumps({
            "format": 1,
            "version": "0.1.0",
            "files": {source: hashlib.sha256(skill.read_bytes()).hexdigest()},
            "components": {"handoff": {"files": {
                source: ".agents/skills/feather-handoff/SKILL.md",
            }}},
        }), encoding="utf-8")

    def make_python_candidate(self, name: str, version: str) -> Path:
        directory = self.directory / "path"
        directory.mkdir(exist_ok=True)
        candidate = directory / (name + (".cmd" if os.name == "nt" else ""))
        if os.name == "nt":
            candidate.write_text(f"@echo off\necho Python {version}\n", encoding="utf-8")
        else:
            candidate.write_text(f"#!/bin/sh\nprintf '%s\\n' 'Python {version}'\n", encoding="utf-8")
            candidate.chmod(0o755)
        return candidate

    def run_check(self, path: Path) -> subprocess.CompletedProcess[str]:
        self.assertIsNotNone(CODEX, "Native Codex required for installer integration tests")
        base = [sys.executable, str(ROOT / "scripts/feather_setup.py"),
                "--project", str(self.project), "--user-home", str(self.user_home),
                "--codex-home", str(self.codex_home), "--bundle", str(self.bundle),
                "--components", "handoff", "--codex", str(CODEX), "--json"]
        installed = subprocess.run([*base[:2], "install", *base[2:]], cwd=self.directory,
                                   capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        environment = dict(os.environ)
        environment.update(PATH=str(path), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
                           NoDefaultCurrentDirectoryInExePath="1")
        before = {item.relative_to(self.directory): item.read_bytes()
                  for item in self.directory.rglob("*") if item.is_file()}
        result = subprocess.run([*base[:2], "check", *base[2:]], cwd=self.directory, env=environment,
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        after = {item.relative_to(self.directory): item.read_bytes()
                 for item in self.directory.rglob("*") if item.is_file()}
        self.assertEqual(after, before, "The public check must remain read-only")
        return result

    def test_check_reports_compatible_python_selected_from_path(self):
        candidate = self.make_python_candidate("python", "3.12.7")
        result = self.run_check(candidate.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        python = json.loads(result.stdout)["runtime"]["python"]
        self.assertEqual(python["status"], "available")
        self.assertEqual(python["version"], "3.12.7")
        self.assertEqual(python["command"], "python")
        self.assertEqual(Path(python["path"]), candidate.resolve())

    def test_check_reports_python_missing_without_a_path_candidate(self):
        empty_path = self.directory / "empty-path"
        empty_path.mkdir()
        result = self.run_check(empty_path)
        self.assertEqual(result.returncode, 1, result.stderr)
        python = json.loads(result.stdout)["runtime"]["python"]
        self.assertEqual(python["status"], "missing")
        self.assertNotIn("path", python)
        self.assertIn("does not install", python["message"])

    def test_check_reports_incompatible_python_version(self):
        candidate = self.make_python_candidate("python", "3.10.14")
        result = self.run_check(candidate.parent)
        self.assertEqual(result.returncode, 1, result.stderr)
        python = json.loads(result.stdout)["runtime"]["python"]
        self.assertEqual(python["status"], "incompatible")
        self.assertEqual(python["version"], "3.10.14")
        self.assertEqual(python["command"], "python")
        self.assertEqual(Path(python["path"]), candidate.resolve())

    def test_check_selects_a_compatible_fallback_after_an_older_python(self):
        self.make_python_candidate("python", "3.10.14")
        candidate = self.make_python_candidate("python3", "3.11.9")
        result = self.run_check(candidate.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        python = json.loads(result.stdout)["runtime"]["python"]
        self.assertEqual(python["status"], "available")
        self.assertEqual(python["version"], "3.11.9")
        self.assertEqual(python["command"], "python3")
        self.assertEqual(Path(python["path"]), candidate.resolve())

    def test_check_can_select_the_python_launcher(self):
        candidate = self.make_python_candidate("py", "3.13.2")
        if os.name == "nt":
            candidate.write_text('@echo off\nif "%~1"=="-3" (echo Python 3.13.2) else (echo Python 3.10.14)\n', encoding="utf-8")
        else:
            candidate.write_text('#!/bin/sh\nif [ "$1" = "-3" ]; then echo Python 3.13.2; else echo Python 3.10.14; fi\n', encoding="utf-8")
        result = self.run_check(candidate.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        python = json.loads(result.stdout)["runtime"]["python"]
        self.assertEqual(python["status"], "available")
        self.assertEqual(python["version"], "3.13.2")
        self.assertEqual(python["command"], "py")
        self.assertEqual(python["arguments"], ["-3"])
        self.assertEqual(Path(python["path"]), candidate.resolve())

    def test_full_payload_install_update_execute_and_remove_preserves_records(self):
        release = self.directory / "release"
        built = subprocess.run([sys.executable, str(ROOT / "scripts/build_setup.py"),
                                "--prepare-only", "--output", str(release)],
                               capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(built.returncode, 0, built.stderr)
        base = [sys.executable, str(ROOT / "scripts/feather_setup.py")]
        options = ["--project", str(self.project), "--user-home", str(self.user_home),
                   "--codex-home", str(self.codex_home), "--bundle", str(release),
                   "--components", "handoff", "--codex", str(CODEX), "--json"]
        installed = self.project / ".agents/skills/feather-handoff/scripts/handoff.py"
        for action in ("install", "update"):
            result = subprocess.run([*base, action, *options], capture_output=True,
                                    text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(installed.read_bytes(), (ROOT / "skills/feather-handoff/scripts/handoff.py").read_bytes())
            queried = subprocess.run([sys.executable, "-B", str(installed), "--project", str(self.project), "list"],
                                     capture_output=True, text=True, encoding="utf-8", timeout=15)
            self.assertEqual(queried.returncode, 0, queried.stderr)
        record = self.project / ".feather/handoffs/manual.md"
        record.parent.mkdir(parents=True)
        record.write_bytes(b"manual record must survive removal\n")
        result = subprocess.run([*base, "remove", *options], capture_output=True,
                                text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(installed.exists())
        self.assertEqual(record.read_bytes(), b"manual record must survive removal\n")


if __name__ == "__main__":
    unittest.main()
