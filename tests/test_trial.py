"""Exercise the isolated trial through its command-line entry point."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TrialTest(unittest.TestCase):
    def run_trial(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "scripts/trial.py"), *map(str, arguments)],
                              capture_output=True, text=True, encoding="utf-8")

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
            self.assertEqual(manifest["expected"], {"role": "scout", "model": "gpt-6-luna", "reasoning": "low"})
            self.assertTrue((trial / "home/agents/scout.toml").is_file())
            self.assertTrue((trial / "workspace/AGENTS.md").is_file())
            self.assertFalse((trial / "home/auth.json").exists())

    def test_all_scenarios_have_five_native_roles(self):
        for scenario in ["analyst-code", "analyst-doc", "analyst-report", "mech", "executor", "direct-small", "direct-global", "generic", "coordination", "return-contract", "bounded-reclaim"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                result = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(list((trial / "home/agents").glob("*.toml"))), 5)
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

    def test_return_contract_covers_every_child_type_and_rejects_extra_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "return-contract")
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((trial / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["expected"],
                             ["scout", "analyst", "mech-executor", "executor", "generic"])
            prompt = (trial / "prompt.txt").read_text(encoding="utf-8")
            for field in ["outcome", "results and evidence", "actual changes", "validation", "blockers"]:
                self.assertIn(field, prompt)
            review = json.loads((trial / "review.json").read_text(encoding="utf-8"))
            self.assertEqual(review["behavior"], "unconfirmed")
            self.assertIn("rejected despite claiming completed", review["criteria"])
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("batch result", result.stderr)

            (trial / "workspace/output/east.txt").write_text("READY\n", encoding="utf-8")
            (trial / "workspace/output/west.txt").write_text("READY\n", encoding="utf-8")
            (trial / "workspace/output/retry.py").write_text(
                "def retry_delay(attempt):\n"
                "    if type(attempt) is not int or attempt < 0:\n"
                "        raise ValueError()\n"
                "    return min(2 ** attempt, 8)\n", encoding="utf-8")
            result = self.run_trial("verify", trial)
            self.assertEqual(result.returncode, 0, result.stderr)
            verified = json.loads(result.stdout)
            self.assertEqual(verified["actual"], "unconfirmed")
            self.assertIn("manual review", verified["behavior"])

            for path, bad_value, error in [
                ("output/east.txt", "BROKEN\n", "batch result"),
                ("output/west.txt", "READY", "batch result"),
                ("output/retry.py", "def retry_delay(attempt): return 0\n", "executor behavior"),
            ]:
                with self.subTest(path=path):
                    artifact = trial / "workspace" / path
                    good_value = artifact.read_text(encoding="utf-8")
                    artifact.write_text(bad_value, encoding="utf-8")
                    result = self.run_trial("verify", trial)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(error, result.stderr)
                    artifact.write_text(good_value, encoding="utf-8")

            (trial / "workspace/output/east.txt").unlink()
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("batch result", result.stderr)
            (trial / "workspace/output/east.txt").write_text("READY\n", encoding="utf-8")

            (trial / "workspace/return-report.md").write_text("completed\n", encoding="utf-8")
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside ownership scope", result.stderr)

    def test_bounded_reclaim_fixture_preserves_partial_work_and_stops_after_second_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "bounded-reclaim")
            self.assertEqual(result.returncode, 0, result.stderr)
            workspace = trial / "workspace"
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact PARTIAL", result.stderr)
            (workspace / "output/partial.txt").write_text("PARTIAL\n", encoding="utf-8")

            failures = []
            for _ in range(2):
                attempt = subprocess.run([sys.executable, "retry_once.py"], cwd=workspace,
                                         capture_output=True, text=True, encoding="utf-8")
                self.assertNotEqual(attempt.returncode, 0)
                failures.append(attempt.stderr.strip())
            self.assertEqual(failures[0], failures[1])
            self.assertIn("target release-check dependency unavailable", failures[0])
            self.assertEqual((workspace / "attempts.txt").read_text(encoding="utf-8"), "2\n")
            self.assertEqual((workspace / "output/partial.txt").read_text(encoding="utf-8"), "PARTIAL\n")

            result = self.run_trial("verify", trial)
            self.assertEqual(result.returncode, 0, result.stderr)
            verified = json.loads(result.stdout)
            self.assertEqual(verified["actual"], "unconfirmed")
            self.assertIn("does not run the third attempt", verified["review_criteria"])
            self.assertEqual((workspace / "attempts.txt").read_text(encoding="utf-8"), "2\n")

            (workspace / "attempts.txt").write_text("3\n", encoding="utf-8")
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly two failed attempts", result.stderr)
            (workspace / "attempts.txt").write_text("2\n", encoding="utf-8")

            (workspace / "output/partial.txt").write_text("PENDING\n", encoding="utf-8")
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact PARTIAL", result.stderr)
            (workspace / "output/partial.txt").write_text("PARTIAL\n", encoding="utf-8")

            (workspace / "attempts.txt").unlink()
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly two failed attempts", result.stderr)

    def test_delegation_templates_define_return_review_and_bounded_reclaim(self):
        agents = (ROOT / "templates/entrances/delegation.md").read_text(encoding="utf-8")
        skill = (ROOT / "templates/feather-delegation/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`feather-delegation` skill", agents)
        self.assertLess(len(agents.split()), 450)
        for required in ["`outcome`", "Results and evidence", "Changes:", "Validation:",
                         "Blockers and next step", "does not by itself complete",
                         "Retry the same operation unchanged at most once",
                         "confirm the previous child has stopped or completed"]:
            self.assertIn(required, skill)

        for role in ["scout", "analyst", "mech-executor", "executor"]:
            with self.subTest(role=role):
                template = (ROOT / f"templates/{role}.toml").read_text(encoding="utf-8")
                for required in ["outcome (completed, partial, or blocked)", "validation",
                                 "unverified items", "blockers", "smallest next step",
                                 "do not create"]:
                    self.assertIn(required, template.lower())

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

    def test_role_model_locks_are_rejected_without_changing_other_fields(self):
        for role in ["scout", "analyst", "mech-executor", "executor"]:
            for binding in ['model = "gpt-6-luna"', 'model_reasoning_effort = "low"']:
                with self.subTest(role=role, binding=binding), tempfile.TemporaryDirectory() as temporary:
                    trial = Path(temporary) / "trial"
                    self.assertEqual(self.run_trial("prepare", trial).returncode, 0)
                    file = trial / f"home/agents/{role}.toml"
                    file.write_text(binding + "\n" + file.read_text(encoding="utf-8"), encoding="utf-8")
                    result = self.run_trial("check", trial)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("locks model or reasoning", result.stderr)

    def test_override_trials_keep_unspecified_defaults_and_sources_readonly(self):
        cases = [("scout-model", "scout", "gpt-6-sol", "low", "settings.toml"),
                 ("scout-effort", "scout", "gpt-6-luna", "high", "settings.toml"),
                 ("analyst-override", "analyst", "gpt-6-luna", "low", "access.py")]
        for scenario, role, model, effort, fixture in cases:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                result = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                manifest = json.loads((trial / "manifest.json").read_text())
                self.assertEqual(manifest["expected"], {"role": role, "model": model, "reasoning": effort})
                result = self.run_trial("check", trial)
                self.assertEqual(result.returncode, 0, result.stderr)
                config = json.loads(result.stdout)["configured"][role]
                self.assertIsNone(config["model"])
                self.assertIsNone(config["reasoning"])
                self.assertEqual(config["sandbox"], "workspace-write" if role == "analyst" else "read-only")
                self.assertEqual(self.run_trial("verify", trial).returncode, 0)
                (trial / "workspace" / fixture).write_text("unauthorized change")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_old_trial_format_requires_fresh_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.run_trial("prepare", trial)
            path = trial / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest["format"] = 2
            path.write_text(json.dumps(manifest))
            result = self.run_trial("check", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("prepare a fresh trial", result.stderr)

    def test_analyst_artifact_requires_output_and_preserves_sources(self):
        for unwanted in ["access.py", "requirements.md", "extra.md"]:
            with self.subTest(unwanted=unwanted), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                result = self.run_trial("prepare", trial, "--scenario", "analyst-report")
                self.assertEqual(result.returncode, 0, result.stderr)
                report = trial / "workspace/analysis.md"
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                report.write_text("   \n", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                report.write_text("# Analysis\naccess.py:2 uses OR; requirements.md:1 requires AND.\n", encoding="utf-8")
                result = self.run_trial("verify", trial)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["changed_files"], ["analysis.md"])
                (trial / "workspace" / unwanted).write_text("out of scope", encoding="utf-8")
                result = self.run_trial("verify", trial)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("outside ownership scope", result.stderr)

    def test_analyst_artifact_cannot_alias_a_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.assertEqual(self.run_trial("prepare", trial, "--scenario", "analyst-report").returncode, 0)
            try:
                os.link(trial / "workspace/access.py", trial / "workspace/analysis.md")
            except OSError as error:
                self.skipTest(f"Hard links unavailable: {error}")
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("separate from source files", result.stderr)

    def test_rejected_repeat_preserves_original_version_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.run_trial("prepare", trial)
            (trial / "smoke.stdout").write_text("original run")
            (trial / "version.stdout").write_text("original version")
            result = self.run_trial("smoke", trial, "--codex", sys.executable,
                                    "--enable-live", "--main-model", "test-model", "--main-reasoning", "low")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((trial / "version.stdout").read_text(), "original version")
            self.assertEqual((trial / "smoke.stdout").read_text(), "original run")


if __name__ == "__main__":
    unittest.main()
