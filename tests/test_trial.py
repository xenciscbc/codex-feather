"""Exercise the isolated trial through its command-line entry point."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TrialTest(unittest.TestCase):
    def run_trial(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "scripts/trial.py"), *map(str, arguments)],
                              capture_output=True, text=True)

    def test_existing_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "keep.txt"
            marker.write_text("user data")
            result = self.run_trial("prepare", temporary)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(), "user data")
            self.assertFalse((Path(temporary) / "home").exists())

    def test_changed_workspace_fails_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.assertEqual(self.run_trial("prepare", trial).returncode, 0)
            self.assertEqual(self.run_trial("check", trial).returncode, 0)
            (trial / "workspace/settings.toml").write_text("port = 8080")
            result = self.run_trial("check", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("baseline", result.stderr)

    def test_live_run_requires_explicit_enablement(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.assertEqual(self.run_trial("prepare", trial).returncode, 0)
            result = self.run_trial("smoke", trial, "--codex", "does-not-exist")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--enable-live", result.stderr)
            self.assertFalse((trial / "version.stdout").exists())

    def test_prepare_isolated_scout_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/trial.py"), "prepare", str(trial)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((trial / "manifest.json").read_text())
            self.assertEqual(manifest["actual"], "unconfirmed")
            self.assertEqual(manifest["expected"], {"role": "scout", "model": "gpt-5.6-luna", "reasoning": "low"})
            self.assertTrue((trial / "home/agents/scout.toml").is_file())
            self.assertTrue((trial / "workspace/AGENTS.md").is_file())
            self.assertFalse((trial / "home/auth.json").exists())

    def test_all_scenarios_have_four_native_roles(self):
        for scenario in ["analyst-code", "analyst-doc", "mech", "executor", "direct-small", "direct-global", "generic", "coordination"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                result = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(list((trial / "home/agents").glob("*.toml"))), 4)
                self.assertEqual(self.run_trial("check", trial).returncode, 0)

    def test_mechanical_result_and_scope_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.run_trial("prepare", trial, "--scenario", "mech")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            for region, retries in [("east", 2), ("west", 3)]:
                (trial / f"workspace/configs/{region}.toml").write_text(
                    f"[api]\ntimeout_ms = 2500\nretries = {retries}\n")
            result = self.run_trial("verify", trial)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["actual"], "unconfirmed")
            (trial / "workspace/archive.toml").write_text("unexpected edit")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_executor_is_checked_by_behavior(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.run_trial("prepare", trial, "--scenario", "executor")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "workspace/retry.py").write_text('''import math
def retry_delay(attempt, base, cap):
    if type(attempt) is not int or attempt < 0:
        raise ValueError()
    for value in (base, cap):
        if type(value) not in (int, float) or value < 0 or (type(value) is float and not math.isfinite(value)):
            raise ValueError()
    if base == 0 or cap == 0:
        return 0
    delay = min(base, cap)
    while attempt and delay < cap:
        delay = min(delay * 2, cap)
        attempt -= 1
    return delay
''')
            result = self.run_trial("verify", trial)
            self.assertEqual(result.returncode, 0, result.stderr)
            (trial / "workspace/retry.py").write_text("def retry_delay(*args): return 0\n")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_coordination_requires_result_and_preserves_blocked_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.run_trial("prepare", trial, "--scenario", "coordination")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "workspace/output/summary.txt").write_text("7319\nVERIFIED\n")
            result = self.run_trial("verify", trial)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unconfirmed", json.loads(result.stdout)["actual"])
            (trial / "workspace/output/timeout.txt").write_text("1000")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_readonly_scenarios_reject_new_or_deleted_files(self):
        for scenario in ["scout", "analyst-code", "analyst-doc", "direct-small", "direct-global", "generic"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                self.run_trial("prepare", trial, "--scenario", scenario)
                result = self.run_trial("verify", trial)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("manual review", json.loads(result.stdout)["behavior"])
                (trial / "workspace/extra.txt").write_text("side effect")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                (trial / "workspace/extra.txt").unlink()
                (trial / "workspace/AGENTS.md").unlink()
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_configuration_drift_cannot_pass(self):
        for file, value in [("home/agents/analyst.toml", 'name="analyst"\nmodel="wrong"'),
                            ("home/config.toml", 'model="changed-main-model"')]:
            with self.subTest(file=file), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                self.run_trial("prepare", trial)
                (trial / file).write_text(value)
                self.assertNotEqual(self.run_trial("check", trial).returncode, 0)


if __name__ == "__main__":
    unittest.main()
