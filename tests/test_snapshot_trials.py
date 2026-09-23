"""Trial verifiers reject missing answers, stale outputs and scope expansion."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SnapshotTrialsTest(unittest.TestCase):
    def run_trial(self, *args):
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/trial.py"), *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_read_requires_answer_and_preserves_all_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "read"
            prepared = self.run_trial("prepare", trial, "--scenario", "handoff-snapshot-read")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(self.run_trial("check", trial).returncode, 0)
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "answer.md").write_text("Historical readiness /legacy; next check current sources.", encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "workspace/readiness.txt").write_text("/ready", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_resume_requires_current_output_and_unfinished_constraints(self):
        for scenario in ["handoff-snapshot-resume", "handoff-snapshot-partial"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "resume"
                prepared = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                (trial / "answer.md").write_text("Current /ready; timeout unresolved; evidence.bin remains unknown.", encoding="utf-8")
                workspace = trial / "workspace"
                helper = trial / "home/skills/handoff/scripts/handoff.py"
                compare = subprocess.run([sys.executable, "-B", str(helper), "--project", str(workspace), "compare", "--work", "config-audit.md"],
                                         capture_output=True, text=True, encoding="utf-8", timeout=15)
                compared = json.loads(compare.stdout)
                self.assertEqual(compare.returncode, 2 if scenario.endswith("partial") else 0)
                self.assertEqual(compared["files"][-1]["comparison"], "changed")
                handoff = workspace / ".feather/handoffs/config-audit.md"
                changed = handoff.read_text(encoding="utf-8").replace("上次 readiness = /legacy", "已核對 readiness = /ready")
                handoff.write_text(changed, encoding="utf-8")
                (workspace / "readiness.txt").write_text("/legacy", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                (workspace / "readiness.txt").write_text("/ready", encoding="utf-8")
                verified = self.run_trial("verify", trial)
                self.assertEqual(verified.returncode, 0, verified.stderr)
                self.assertEqual(json.loads(verified.stdout)["actual"], "unconfirmed")
                handoff.write_text(changed.replace("狀態：進行中", "狀態：完成"), encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


if __name__ == "__main__":
    unittest.main()
