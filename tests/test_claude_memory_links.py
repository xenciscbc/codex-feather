"""Exercise linked Claude memory sources through the public trial CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ClaudeMemoryLinksTrialTest(unittest.TestCase):
    def run_trial(self, *arguments):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/trial.py"), *map(str, arguments)],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_same_project_link_is_reported_once_and_outside_references_are_only_listed(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            prepared = self.run_trial("prepare", trial, "--scenario", "claude-memory-links")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertTrue((trial / "workspace/project/docs/not-a-file.md").is_dir())
            self.assertEqual(
                (trial / "workspace/project/docs/unreadable.md").read_bytes(), b"\xff\xfe\xfa",
            )
            self.assertIn(
                "transcript-secret-866",
                (trial / "workspace/project/transcripts/session.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(self.run_trial("check", trial).returncode, 0)

            answer = (
                "## linked-rollout\n"
                "明確交接，狀態未完成。memory 記載 port 7319，連結交接記載 port 8443，"
                "兩者尚未核對；下一步為 readiness-check，限制是 timeout-owner。\n"
                "[memory 來源](memory/MEMORY.md:4) "
                "[同專案交接](project/docs/release-handoff.md:1)\n\n"
                "未展開的參照：outside/external-handoff.md（跨專案）、"
                "https://example.invalid/runbook（網頁）、project/docs/missing.md（失效）、"
                "project/docs/not-a-file.md（不是檔案）、project/docs/unreadable.md（解碼失敗）、"
                "project/docs/reference.md（內容非交接）。搜尋有部分限制。\n"
            )
            (trial / "answer.md").write_text(answer, encoding="utf-8")
            verified = self.run_trial("verify", trial)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["actual"], "unconfirmed")

            windows_answer = answer.replace("project/", "project\\").replace("docs/", "docs\\")
            windows_answer = windows_answer.replace("outside/", "outside\\").replace(" 的 autoMemoryDirectory", " 的設定")
            (trial / "answer.md").write_text(windows_answer, encoding="utf-8")
            accepted = self.run_trial("verify", trial)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

            for bad in (
                answer.replace("[同專案交接](project/docs/release-handoff.md:1)", ""),
                answer + "外部文件內容：outside-secret-913。\n",
                answer + "逐字稿內容：transcript-secret-866。\n",
                answer + "\n## linked-rollout\n重複結果。\n",
            ):
                (trial / "answer.md").write_text(bad, encoding="utf-8")
                self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)
            (trial / "answer.md").write_text(answer, encoding="utf-8")
            source = trial / "workspace/project/docs/release-handoff.md"
            source.write_text("changed after the read", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_unknown_project_still_searches_memory_but_does_not_expand_its_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            prepared = self.run_trial("prepare", trial, "--scenario", "claude-memory-links-unknown")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            answer = (
                "未提供可確認的專案範圍，因此目錄外連結只列出，不展開："
                "unknown-project/handoff.md。\n"
                "## memory-audit\n"
                "疑似交接，狀態不明；已記錄 mem-204，下一步或限制未記載。\n"
                "[來源](memory/notes.md:1)\n"
            )
            (trial / "answer.md").write_text(answer, encoding="utf-8")
            verified = self.run_trial("verify", trial)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["actual"], "unconfirmed")

            (trial / "answer.md").write_text(answer + "未知專案內容：unknown-secret-518。\n", encoding="utf-8")
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)

    def test_alias_ancestor_is_out_of_scope_and_its_identity_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            prepared = self.run_trial("prepare", trial, "--scenario", "claude-memory-links-alias")
            if prepared.returncode:
                self.assertIn("symlink/reparse fixture unavailable", prepared.stderr)
                self.skipTest(prepared.stderr.strip())
            answer = (
                "## alias-control\n"
                "明確交接，未完成；control-311，下一步 verify-alias-boundary。\n"
                "[來源](project/docs/control-handoff.md:1)\n\n"
                "project/linked-outside/external.md 的解析目標位於專案外，只列出且未展開。\n"
            )
            (trial / "answer.md").write_text(answer, encoding="utf-8")
            verified = self.run_trial("verify", trial)
            self.assertEqual(verified.returncode, 0, verified.stderr)

            alias = trial / "workspace/project/linked-outside"
            if alias.is_symlink():
                alias.unlink()
                alias.symlink_to(Path("../outside-copy"), target_is_directory=True)
            else:
                alias.rmdir()
            changed = self.run_trial("check", trial)
            self.assertNotEqual(changed.returncode, 0)
            self.assertIn("identity", changed.stderr)

    def test_project_location_flows_into_same_project_link_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary) / "trial"
            prepared = self.run_trial(
                "prepare", trial, "--scenario", "claude-memory-project-links",
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            settings = json.loads(
                (trial / "workspace/project/.claude/settings.local.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(settings["autoMemoryDirectory"], str(trial / "workspace/memory"))
            answer = (
                "定位依據：project/.claude/settings.local.json 的 autoMemoryDirectory 指向 memory。\n"
                "## linked-rollout\n"
                "明確交接，未完成；memory 的 7319 與連結交接的 8443 衝突。"
                "下一步 readiness-check；限制 timeout-owner。\n"
                "[memory](memory/MEMORY.md:3) "
                "[同專案交接](project/docs/release-handoff.md:1)\n\n"
                "只列出：outside/external-handoff.md、https://example.invalid/runbook、"
                "project/docs/missing.md、project/docs/not-a-file.md、"
                "project/docs/unreadable.md、project/docs/reference.md。\n"
            )
            (trial / "answer.md").write_text(answer, encoding="utf-8")
            verified = self.run_trial("verify", trial)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["actual"], "unconfirmed")
            cited_evidence = answer.replace(
                "project/.claude/settings.local.json 的 autoMemoryDirectory",
                "[本機設定](project/.claude/settings.local.json:1)",
            )
            (trial / "answer.md").write_text(cited_evidence, encoding="utf-8")
            accepted = self.run_trial("verify", trial)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            (trial / "answer.md").write_text(
                cited_evidence.replace("[本機設定](project/.claude/settings.local.json:1)", "本機設定"),
                encoding="utf-8",
            )
            self.assertNotEqual(self.run_trial("verify", trial).returncode, 0)


if __name__ == "__main__":
    unittest.main()
