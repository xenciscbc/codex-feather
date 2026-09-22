"""The actual offline payload deploys a runnable snapshot tool and preserves records."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_setup import payload
from setup_installer.bundle import Bundle


class SnapshotDeploymentTest(unittest.TestCase):
    def test_payload_contains_snapshot_sources_without_native_codex(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle_dir = Path(temporary)
            payload(bundle_dir)
            files = Bundle.read(bundle_dir).files("handoff")
            for relative in ["scripts/feather_handoff/baseline.py", "scripts/feather_handoff/observations.py", "references/snapshots.md"]:
                target = ".agents/skills/feather-handoff/" + relative
                self.assertEqual(files[target], (ROOT / "skills/feather-handoff" / relative).read_bytes())

    def test_real_payload_installs_updates_and_removes_without_losing_baseline(self):
        native = os.environ.get("FEATHER_TEST_CODEX") or shutil.which("codex.exe" if os.name == "nt" else "codex")
        if not native:
            self.skipTest("Native Codex is required for actual installer checks")
        runs = ROOT / ".scratch/feather-resume-reliability/deployment-tests"
        runs.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runs) as temporary:
            root = Path(temporary)
            bundle_dir = root / "bundle"
            bundle_dir.mkdir()
            payload(bundle_dir)
            bundle = Bundle.read(bundle_dir)
            files = bundle.files("handoff")
            for relative in ["scripts/feather_handoff/baseline.py", "scripts/feather_handoff/observations.py", "references/snapshots.md"]:
                target = ".agents/skills/feather-handoff/" + relative
                self.assertEqual(files[target], (ROOT / "skills/feather-handoff" / relative).read_bytes())
            project = root / "project"
            project.mkdir()
            initialized = subprocess.run(["git", "-C", str(project), "init", "--initial-branch=main"],
                                         capture_output=True, text=True, timeout=10)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            (project / "source.txt").write_bytes(b"before")
            env = {key: value for key, value in os.environ.items() if not key.upper().startswith("CODEX_")}
            env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
            def setup(action):
                result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/feather_setup.py"), action,
                    "--project", str(project), "--user-home", str(root / "user"), "--codex-home", str(root / "codex"),
                    "--bundle", str(bundle_dir), "--components", "handoff", "--scope", "project", "--codex", native, "--json"],
                    capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return json.loads(result.stdout)
            setup("install")
            tool = project / ".agents/skills/feather-handoff/scripts/handoff.py"
            def run(*args, data=None):
                result = subprocess.run([sys.executable, "-B", str(tool), "--project", str(project), *args],
                    input=json.dumps(data) if data is not None else None, capture_output=True,
                    text=True, encoding="utf-8", env=env, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return json.loads(result.stdout)
            value = run("snapshot", data={"paths": ["source.txt"]})["snapshot"]
            run("create", "--work", "demo.md", data={"fields": {"goal": "check", "progress": "before", "next": "review"}, "snapshot": value})
            handoff = project / ".feather/handoffs/demo.md"
            saved = handoff.read_bytes()
            (project / "source.txt").write_bytes(b"after")
            setup("update")
            self.assertEqual(run("compare", "--work", "demo.md")["files"][0]["comparison"], "changed")
            setup("check")
            setup("remove")
            self.assertFalse(tool.exists())
            self.assertEqual(handoff.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
