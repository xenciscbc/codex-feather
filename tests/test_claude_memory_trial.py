"""Exercise Claude memory trials through the public prepare/check/verify CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ClaudeMemoryTrialTest(unittest.TestCase):
    def run_trial(self, *arguments):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/trial.py"), *map(str, arguments)],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_direct_memory_trial_preserves_sources_and_requires_an_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            prepared = self.run_trial("prepare", trial, "--scenario", "claude-memory-direct")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(self.run_trial("check", trial).returncode, 0)
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("answer.md", result.stderr)
            (trial / "answer.md").write_text(
                "## cache-rollout\n明確交接，未完成。已確認 port 7319；尚未跑測試。"
                "下一步核對 readiness；timeout 等使用者決定。\n"
                "來源：[交接](workspace/memory/release.md:3)。\n", encoding="utf-8",
            )
            verified = self.run_trial("verify", trial)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["actual"], "unconfirmed")
            source = trial / "workspace/memory/release.md"
            source.write_text("changed by reader", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_answer_checks_reject_omitted_work_and_fabricated_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.assertEqual(self.run_trial("prepare", trial, "--scenario", "claude-memory-direct").returncode, 0)
            good = (
                "## cache-rollout\n未完成的明確交接；7319，readiness 待核對，timeout 未決。\n"
                "[來源](memory/release.md#cache-rollout)\n"
            )
            answers = {
                "omitted": "沒有符合的交接。\n",
                "invented-source": good.replace("memory/release.md", "memory/invented.md"),
                "wrong-existing-source": good.replace("memory/release.md", "memory/preferences.md"),
                "lost-finding": good.replace("7319", "port 已確認"),
            }
            for name, answer in answers.items():
                with self.subTest(name=name):
                    (trial / "answer.md").write_text(answer, encoding="utf-8")
                    result = self.run_trial("verify", trial)
                    self.assertNotEqual(result.returncode, 0)
                    saved = json.loads((trial / "verification.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["artifacts"], "unconfirmed")
            (trial / "answer.md").write_text(good, encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)

    def test_mixed_memory_checks_all_work_and_preserves_conflicting_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            prepared = self.run_trial("prepare", trial, "--scenario", "claude-memory-mixed")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            answer = (
                "## cache-rollout\n明確交接，未完成。7319 與 8443 衝突；readiness 待核對，timeout 未決。\n"
                "[原交接](memory/release.md:3) [另一記錄](memory/unindexed/observations.md:1)\n"
                "## asset-cleanup\n明確交接，已完成；移除了 17 個暫存檔。\n"
                "[完成記錄](memory/notes.md:1)\n"
                "## queue-check\n疑似交接，狀態不明；記下 probe-42；沒有下一步或完成聲明。\n"
                "[工作筆記](memory/notes.md:5)\n"
            )
            for name, bad in {
                "lost-work": answer.split("## queue-check")[0],
                "lost-conflict": answer.replace(" [另一記錄](memory/unindexed/observations.md:1)", ""),
                "duplicate-work": answer + answer.split("## asset-cleanup")[0],
            }.items():
                with self.subTest(name=name):
                    (trial / "answer.md").write_text(bad, encoding="utf-8")
                    self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "answer.md").write_text(answer, encoding="utf-8")
            result = self.run_trial("verify", trial)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["actual"], "unconfirmed")
            (trial / "workspace/memory/unindexed/observations.md").unlink()
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_source_diagnostics_and_no_request_do_not_report_hidden_work(self):
        reports = {
            "claude-memory-empty": "已完整搜尋 memory，沒有符合的交接；只有一般偏好。\n",
            "claude-memory-missing": "memory 不存在，無法搜尋；請提供明確目錄。\n",
            "claude-memory-no-request": "沒有 Feather 待接續交接。\n",
        }
        for scenario, answer in reports.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                prepared = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                (trial / "answer.md").write_text("## cache-rollout\nport 7319\n", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                (trial / "answer.md").write_text(answer, encoding="utf-8")
                verified = self.run_trial("verify", trial)
                self.assertEqual(verified.returncode, 0, verified.stderr)
                self.assertEqual(json.loads(verified.stdout)["actual"], "unconfirmed")
                (trial / "workspace/unrequested.md").write_text("imported handoff", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_partial_search_must_name_the_unreadable_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            prepared = self.run_trial("prepare", trial, "--scenario", "claude-memory-partial")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            answer = (
                "## cache-rollout\n明確交接，未完成。7319；readiness 待核對，timeout 未決。\n"
                "[來源](memory/release.md:3)\n"
            )
            (trial / "answer.md").write_text(answer, encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "answer.md").write_text(
                answer + "\n限制：memory/locked.md 無法讀取；搜尋不完整。\n", encoding="utf-8",
            )
            checked = self.run_trial("verify", trial)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(json.loads(checked.stdout)["actual"], "unconfirmed")

    def test_project_custom_memory_reuses_read_flow_and_protects_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            prepared = self.run_trial("prepare", trial, "--scenario", "claude-memory-project-custom")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(self.run_trial("check", trial).returncode, 0)
            (trial / "answer.md").write_text(
                "來源定位：project/.claude/settings.local.json 的 autoMemoryDirectory。\n"
                "## cache-rollout\n明確交接，未完成；7319，readiness 待核對，timeout 未決。\n"
                "[來源](memory/release.md:3)\n", encoding="utf-8",
            )
            verified = self.run_trial("verify", trial)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            settings = trial / "workspace/project/.claude/settings.local.json"
            settings.write_text("{}\n", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_project_default_and_worktree_trials_check_shared_source_and_git_state(self):
        for scenario in ("claude-memory-project-default", "claude-memory-project-worktree"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                prepared = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                source = next((trial / "workspace/claude-config/projects").glob("*/memory/release.md"))
                source_link = source.relative_to(trial / "workspace").as_posix()
                (trial / "answer.md").write_text(
                    "## cache-rollout\n明確交接，未完成；7319，readiness 待核對，timeout 未決。\n"
                    f"[來源]({source_link}:3)\n", encoding="utf-8",
                )
                result = self.run_trial("verify", trial)
                self.assertEqual(result.returncode, 0, result.stderr)
                config = trial / "workspace/project/.git/config"
                config.write_text(config.read_text(encoding="utf-8") + "\n# unexpected\n", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_ambiguous_project_requires_candidates_without_reporting_their_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            prepared = self.run_trial("prepare", trial, "--scenario", "claude-memory-project-ambiguous")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            (trial / "answer.md").write_text("位置不明，請選擇。\n", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            answer = (
                "因先前 Claude 的專案設定信任狀態不明，來源有兩個候選：\n"
                "- memory：專案本機 autoMemoryDirectory。\n"
                "- user-memory：使用者 autoMemoryDirectory。\n"
                "請選擇來源；尚未搜尋任一候選內容。\n"
            )
            (trial / "answer.md").write_text(answer, encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "answer.md").write_text(answer + "## cache-rollout\n7319\n", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_non_git_and_named_project_sources_use_the_same_answer_contract(self):
        for scenario in ("claude-memory-project-non-git", "claude-memory-project-named"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                prepared = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                source = next((trial / "workspace/claude-config/projects").glob("*/memory/release.md"))
                if scenario.endswith("non-git"):
                    self.assertFalse((trial / "workspace/project/.git").exists())
                else:
                    self.assertEqual(source.parent.parent.name, "isolated-project")
                (trial / "answer.md").write_text(
                    "## cache-rollout\n明確交接，未完成；7319，readiness 待核對，timeout 未決。\n"
                    f"[來源]({source.as_posix()}:3)\n", encoding="utf-8",
                )
                result = self.run_trial("verify", trial)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["actual"], "unconfirmed")


    def test_project_location_failures_report_the_effective_setting_without_fallback(self):
        answers = {
            "claude-memory-project-missing": "settings.local.json 的 autoMemoryDirectory 指向 missing-memory；該目錄不存在。",
            "claude-memory-project-invalid": "settings.local.json 的 autoMemoryDirectory 是 relative-memory，並非合法絕對或 home-relative 路徑。",
        }
        for scenario, answer in answers.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                prepared = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                (trial / "answer.md").write_text("找不到交接。", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                (trial / "answer.md").write_text(answer, encoding="utf-8")
                checked = self.run_trial("verify", trial)
                self.assertEqual(checked.returncode, 0, checked.stderr)
                (trial / "answer.md").write_text(answer + "\n## cache-rollout\n7319\n", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_non_git_fixture_rejects_an_enclosing_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True,
                           capture_output=True)
            prepared = self.run_trial("prepare", root / "trial", "--scenario", "claude-memory-project-non-git")
            self.assertNotEqual(prepared.returncode, 0)
            self.assertIn("outside an existing Git repository", prepared.stderr)


if __name__ == "__main__":
    unittest.main()
