"""Verify handoff artifacts through the existing isolated trial CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HandoffTrialTest(unittest.TestCase):
    def run_trial(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "scripts/trial.py"), *map(str, arguments)],
                              capture_output=True, text=True, encoding="utf-8")

    def final_body(self, original):
        return (original.split("\n", 1)[1].replace("T10:00:00", "T12:00:00")
                .replace("狀態：進行中", "狀態：完成")
                .replace("尚未核對 readiness", "已核對 readiness = /ready；未執行測試")
                .replace("下一步：核對 readiness", "下一步：無"))

    def test_create_requires_a_real_handoff_and_preserves_project_instructions(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-create")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((trial / "home/skills/feather-handoff/SKILL.md").is_file())
            self.assertEqual(self.run_trial("check", trial).returncode, 0)
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            workspace = trial / "workspace"
            handoff = workspace / ".feather/handoffs/config-audit.md"
            handoff.parent.mkdir(parents=True)
            handoff.write_text(
                "# config-audit\n更新：2026-09-08T10:00:00+08:00\n狀態：進行中\n\n"
                "目標：核對設定\n進度：確認 port = 7319；尚未測試。\n"
                "下一步：核對 readiness 路徑。\n", encoding="utf-8")
            result = self.run_trial("verify", trial)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["actual"], "unconfirmed")
            (workspace / "AGENTS.md").write_text("inserted skill entry", encoding="utf-8")
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside ownership scope", result.stderr)

    def test_update_requires_new_progress_and_preserves_other_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-update")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            handoff = trial / "workspace/.feather/handoffs/config-audit.md"
            content = handoff.read_text(encoding="utf-8")
            handoff.write_text(content.replace("尚未核對 readiness", "已核對 /ready；測試未執行")
                               .replace("核對 readiness", "評估 timeout"), encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            (handoff.parent / "other-work.md").unlink()
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_git_default_requires_ignore_without_staging_user_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-git-default")
            self.assertEqual(result.returncode, 0, result.stderr)
            workspace = trial / "workspace"
            handoff = workspace / ".feather/handoffs/config-audit.md"
            handoff.parent.mkdir(parents=True)
            handoff.write_text("# config-audit\n更新：2026-09-08T10:00:00+08:00\n狀態：進行中\n"
                               "目標：核對設定\n進度：port 7319，未測試\n下一步：核對 readiness\n", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            ignore = workspace / ".gitignore"
            ignore.write_text(ignore.read_text(encoding="utf-8") + "/.feather/handoffs/\n", encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            staged = subprocess.run(["git", "-C", str(workspace), "add", "settings.toml"], capture_output=True)
            self.assertEqual(staged.returncode, 0, staged.stderr)
            result = self.run_trial("verify", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("index", result.stderr)


    def test_git_tracking_choices_are_preserved(self):
        for scenario in ["handoff-git-track", "handoff-git-tracked"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                result = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                workspace = trial / "workspace"
                path = workspace / ".feather/handoffs/config-audit.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# config-audit\n更新：2026-09-08T10:00:00+08:00\n狀態：進行中\n"
                                "目標：核對設定\n進度：7319 /ready，未測試\n下一步：評估 timeout\n"
                                "注意：timeout 由使用者決定。\n", encoding="utf-8")
                result = self.run_trial("verify", trial)
                self.assertEqual(result.returncode, 0, result.stderr)
                (workspace / ".gitignore").write_text("/.feather/handoffs/\n", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_unactivated_work_rejects_handoff_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-no-request")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            unwanted = trial / "workspace/.feather/handoffs/unrequested.md"
            unwanted.parent.mkdir(parents=True)
            unwanted.write_text("unrequested handoff", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_reserved_work_name_creates_a_separate_file_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-name")
            self.assertEqual(result.returncode, 0, result.stderr)
            directory = trial / "workspace/.feather/handoffs"
            (directory / "history-task.md").write_text(
                "# history\n更新：2026-09-08T10:00:00+08:00\n狀態：進行中\n"
                "目標：核對設定\n進度：7319，未測試\n下一步：核對 readiness\n", encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            (directory / "history.md").write_text("replaced", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_read_and_ambiguous_selection_preserve_all_work(self):
        for scenario in ["handoff-read", "handoff-choose", "handoff-none"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                result = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.run_trial("verify", trial).returncode, 0)
                (trial / "workspace/readiness.txt").write_text("/ready\n", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_resume_requires_current_source_value_and_updated_handoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-resume")
            self.assertEqual(result.returncode, 0, result.stderr)
            workspace = trial / "workspace"
            result_file = workspace / "readiness.txt"
            result_file.write_text("/legacy\n", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            result_file.write_text("/ready\n", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            handoff = workspace / ".feather/handoffs/config-audit.md"
            content = handoff.read_text(encoding="utf-8")
            handoff.write_text(content.replace("/legacy", "/ready") + "\n進度補充：readiness.txt 已寫入；未跑測試。\n", encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)


    def test_archive_requires_saved_record_before_removing_active_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-archive")
            self.assertEqual(result.returncode, 0, result.stderr)
            directory = trial / "workspace/.feather/handoffs"
            original = (directory / "config-audit.md").read_text(encoding="utf-8")
            (directory / "config-audit.md").unlink()
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            history = directory / "history.md"
            history.write_text(history.read_text(encoding="utf-8") +
                               "\n## config-audit · 完成：2026-09-08T12:00:00+08:00\n" +
                               self.final_body(original), encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            history.write_text(history.read_text(encoding="utf-8").replace("previous", "lost"), encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_archive_rejects_missing_fields_invalid_times_and_lost_constraints(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.assertEqual(self.run_trial("prepare", trial, "--scenario", "handoff-archive").returncode, 0)
            directory = trial / "workspace/.feather/handoffs"
            history = directory / "history.md"
            prefix = history.read_text(encoding="utf-8")
            work = directory / "config-audit.md"
            body = self.final_body(work.read_text(encoding="utf-8"))
            entry = "\n## config-audit · 完成：2026-09-08T12:00:00+08:00\n" + body
            work.unlink()
            invalid = {
                "keyword-only": "\n## config-audit · 完成：not-a-time\n狀態：完成\n7319 /ready\n",
                "bad-date": entry.replace("2026-09-08", "2026-02-30"),
                "no-timezone": entry.replace("+08:00", ""),
                "different-time": entry.replace("更新：2026-09-08T12", "更新：2026-09-08T10"),
                "unfinished": entry.replace("狀態：完成", "狀態：進行中"),
                "duplicate-status": entry + "狀態：完成\n",
                "lost-constraint": entry.replace("timeout", "removed"),
                "lost-finding": entry.replace("/ready", "removed"),
                "empty-goal": entry.replace("目標：核對服務設定", "目標："),
            }
            for field in ["更新", "狀態", "目標", "進度", "下一步"]:
                invalid[f"missing-{field}"] = "\n".join(line for line in entry.split("\n")
                                                        if not line.startswith(field + "："))
            for name, content in invalid.items():
                with self.subTest(name=name):
                    history.write_text(prefix + content, encoding="utf-8")
                    self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            history.write_text(prefix + entry, encoding="utf-8")
            result = self.run_trial("verify", trial)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["actual"], "unconfirmed")


    def test_archive_failure_preserves_recoverable_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-archive-failure")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "workspace/.feather/handoffs/config-audit.md").unlink()
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_archive_retry_preserves_saved_history_without_duplicate_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-archive-retry")
            self.assertEqual(result.returncode, 0, result.stderr)
            directory = trial / "workspace/.feather/handoffs"
            history = directory / "history.md"
            saved = history.read_text(encoding="utf-8")
            (directory / "config-audit.md").unlink()
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            history.write_text(saved + saved[saved.index("## config-audit"):], encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_removal_failure_keeps_original_and_successfully_saved_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-archive-remove-failure")
            self.assertEqual(result.returncode, 0, result.stderr)
            directory = trial / "workspace/.feather/handoffs"
            original = (directory / "config-audit.md").read_text(encoding="utf-8")
            history = directory / "history.md"
            history.write_text(history.read_text(encoding="utf-8") +
                               "\n## config-audit · 完成：2026-09-08T10:00:00+08:00\n" + original.split("\n", 1)[1],
                               encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            saved = history.read_text(encoding="utf-8")
            history.write_text(saved + "驗證：invented extra result\n", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            history.write_text(saved, encoding="utf-8")
            (directory / "config-audit.md").unlink()
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_archive_preserves_same_name_with_different_completion_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-archive-same-name")
            self.assertEqual(result.returncode, 0, result.stderr)
            directory = trial / "workspace/.feather/handoffs"
            original = (directory / "config-audit.md").read_text(encoding="utf-8")
            history = directory / "history.md"
            history.write_text(history.read_text(encoding="utf-8") +
                               "\n## config-audit · 完成：2026-09-08T12:00:00+08:00\n" +
                               self.final_body(original), encoding="utf-8")
            (directory / "config-audit.md").unlink()
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            history.write_text(history.read_text(encoding="utf-8").replace("2026-09-07T09:00:00+08:00", "lost"), encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_history_queries_and_ambiguous_clear_have_no_side_effects(self):
        for scenario in ["handoff-history", "handoff-clear-ambiguous", "handoff-keep-history", "handoff-history-missing", "handoff-history-empty",
                         "handoff-history-search", "handoff-history-search-sealed", "handoff-seal-conflict"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                result = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.run_trial("verify", trial).returncode, 0)
                history = trial / "workspace/.feather/handoffs/history.md"
                if history.exists():
                    history.unlink()
                else:
                    history.write_text("unrequested history", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_sealing_preserves_complete_entry_and_supports_retry(self):
        for scenario in ["handoff-seal", "handoff-seal-retry", "handoff-seal-other-completion"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                result = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                directory = trial / "workspace/.feather/handoffs"
                source = directory / "history.md"
                original = source.read_text(encoding="utf-8")
                start = original.index("## config-audit · 完成：2026-09-08")
                entry = original[start:]
                destination = directory / "archive/september.md"
                destination.parent.mkdir(exist_ok=True)
                source.write_text(original[:start], encoding="utf-8")
                if scenario != "handoff-seal-retry":
                    self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                destination.write_text("# 交接歷史\n\n" + entry, encoding="utf-8")
                result = self.run_trial("verify", trial)
                self.assertEqual(result.returncode, 0, result.stderr)
                destination.write_text("# 交接歷史\n\n" + entry.replace("timeout", "lost"), encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                destination.write_text("# 交接歷史\n\n" + entry, encoding="utf-8")
                source.write_text("# 交接歷史\n", encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_sealing_defers_when_completed_work_survives_archival(self):
        for scenario in ["handoff-seal-pending-archive", "handoff-seal-pending-archive-conflict",
                         "handoff-seal-pending-archive-retry"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                trial = Path(temporary) / "trial"
                prepared = self.run_trial("prepare", trial, "--scenario", scenario)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                directory = trial / "workspace/.feather/handoffs"
                work = directory / "retained-work.md"
                self.assertIn("狀態：完成", work.read_text(encoding="utf-8"))
                self.assertFalse((directory / "config-audit.md").exists())
                checked = self.run_trial("verify", trial)
                self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertEqual(json.loads(checked.stdout)["actual"], "unconfirmed")

                history = directory / "history.md"
                original = history.read_text(encoding="utf-8")
                start = original.index("## config-audit · 完成：2026-09-08")
                destination = directory / "archive/september.md"
                destination.parent.mkdir(exist_ok=True)
                saved = destination.read_bytes() if destination.exists() else None
                destination.write_text("# 交接歷史\n\n" + original[start:], encoding="utf-8")
                history.write_text(original[:start], encoding="utf-8")
                # The previously accepted seal would hide the identity from archival retry.
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
                history.write_text(original, encoding="utf-8")
                if saved is None:
                    destination.unlink()
                else:
                    destination.write_bytes(saved)
                self.assertEqual(self.run_trial("verify", trial).returncode, 0)
                work.unlink()
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_busy_history_writer_keeps_completed_work_without_touching_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.assertEqual(self.run_trial("prepare", trial, "--scenario", "handoff-history-writer-busy").returncode, 0)
            directory = trial / "workspace/.feather/handoffs"
            work = directory / "config-audit.md"
            work.write_text("# config-audit\n" + self.final_body(work.read_text(encoding="utf-8")), encoding="utf-8")
            checked = self.run_trial("verify", trial)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            history = directory / "history.md"
            history.write_text(history.read_text(encoding="utf-8") + "unexpected change\n", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_partial_history_clear_preserves_other_completions_and_active_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-clear")
            self.assertEqual(result.returncode, 0, result.stderr)
            directory = trial / "workspace/.feather/handoffs"
            history = directory / "history.md"
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            current = history.read_text(encoding="utf-8")
            history.write_text(current.split("## config-audit · 完成：2026-09-08")[0], encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            (directory / "config-audit.md").unlink()
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_clear_all_is_limited_to_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-clear-all")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            directory = trial / "workspace/.feather/handoffs"
            (directory / "history.md").unlink()
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            (directory / "other-work.md").unlink()
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_failed_clear_keeps_original_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-clear-failure")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "workspace/.feather/handoffs/history.md").write_text("partial", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_existing_readonly_trials_still_reject_git_metadata_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.assertEqual(self.run_trial("prepare", trial, "--scenario", "scout").returncode, 0)
            metadata = trial / "workspace/.git"
            metadata.mkdir()
            (metadata / "config").write_text("unexpected Git configuration", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


    def test_git_handoff_cannot_change_repository_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            self.assertEqual(self.run_trial("prepare", trial, "--scenario", "handoff-git-default").returncode, 0)
            config = trial / "workspace/.git/config"
            config.write_text(config.read_text(encoding="utf-8") + "\n[alias]\n  unexpected = status\n", encoding="utf-8")
            result = self.run_trial("check", trial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("metadata", result.stderr)


    def test_first_archive_creates_shared_history_before_removing_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            result = self.run_trial("prepare", trial, "--scenario", "handoff-archive-first")
            self.assertEqual(result.returncode, 0, result.stderr)
            directory = trial / "workspace/.feather/handoffs"
            history = directory / "history.md"
            self.assertFalse(history.exists())
            original = (directory / "config-audit.md").read_text(encoding="utf-8")
            (directory / "config-audit.md").unlink()
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            history.write_text("# 交接歷史\n\n## config-audit · 完成：2026-09-08T12:00:00+08:00\n" +
                               self.final_body(original), encoding="utf-8")
            self.assertEqual(self.run_trial("verify", trial).returncode, 0)


if __name__ == "__main__":
    unittest.main()
