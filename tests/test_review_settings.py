"""Policy toggles persist only in a verified existing installation."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_model
ROOT = test_model.ROOT
from setup_installer.environment import Environment
from setup_installer.installer import execute
from setup_installer.migration import migrate
from setup_installer.review_settings import run


class ReviewPolicyTests(unittest.TestCase):
    setUp = test_model.ModelTests.setUp
    install = test_model.ModelTests.install

    def snapshot(self):
        return {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}

    def save(self, environment, mode):
        preview = run("preview", environment, mode)
        return run("apply", environment, mode, preview["plan_id"])

    def test_default_preview_apply_and_update_preserve_choice(self):
        self.install()
        self.assertEqual(run("show", self.env)["review_mode"], "off")
        before = self.snapshot()
        preview = run("preview", self.env, "auto")
        self.assertEqual(before, self.snapshot())
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            run("apply", self.env, "off", preview["plan_id"])
        self.assertEqual(before, self.snapshot())
        self.save(self.env, "auto")
        execute("update", self.env, self.bundle, ["delegation"], None)
        self.assertEqual(run("show", self.env)["review_mode"], "auto")
        state = json.loads(self.env.state_path.read_text())
        self.assertEqual(state["components"]["delegation"]["review_mode"], "auto")
        self.save(self.env, "off")
        self.install()
        self.assertEqual(run("show", self.env)["review_mode"], "off")

    def test_no_implicit_install_or_entrance_creation(self):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "No existing"):
            run("preview", self.env, "auto")
        self.assertEqual(before, self.snapshot())
        self.install(entrance="none")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "No managed entrance"):
            run("preview", self.env, "auto")
        self.assertEqual(before, self.snapshot())

    def test_user_and_reused_project_policy_are_independent(self):
        self.install("user", "user")
        self.install("project", "project")
        user = Environment(self.project, self.user_home, self.codex_home, "user")
        self.save(user, "auto")
        self.assertEqual(run("show", self.env)["review_mode"], "off")
        self.assertEqual(run("show", user)["review_mode"], "auto")
        self.save(self.env, "auto")
        self.save(user, "off")
        self.assertEqual(run("show", self.env)["review_mode"], "auto")
        self.assertEqual(run("show", user)["review_mode"], "off")

    def test_migration_and_model_edit_keep_policy(self):
        from model import run as model_run
        self.install()
        self.save(self.env, "auto")
        preview = model_run("preview", self.env, ["security-executor.reasoning=medium"])
        model_run("apply", self.env, ["security-executor.reasoning=medium"], preview["plan_id"])
        self.assertEqual(run("show", self.env)["review_mode"], "auto")
        migrate(self.env, self.bundle, ["delegation"], "project", "user", None, entrance="user")
        user = Environment(self.project, self.user_home, self.codex_home, "user")
        self.assertEqual(run("show", user)["review_mode"], "auto")
        self.assertEqual(model_run("show", self.env, [])["roles"]["security-executor"]["reasoning"], "medium")

    def test_custom_guidance_and_shared_owner_blocked_without_writes(self):
        self.install("user", "user")
        self.install("project", "user")
        before = self.snapshot()
        user = Environment(self.project, self.user_home, self.codex_home, "user")
        with self.assertRaisesRegex(ValueError, "shared owners"):
            run("preview", user, "auto")
        self.assertEqual(before, self.snapshot())
        execute("remove", self.env, self.bundle, ["delegation"], None)
        target = self.codex_home / "AGENTS.md"
        target.write_text(target.read_text().replace("Automatic plan review mode: off", "Automatic plan review mode: auto"))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "conflict"):
            run("preview", user, "off")
        self.assertEqual(before, self.snapshot())

    def test_cli_preview_json_and_missing_preview_error(self):
        self.install()
        command = [sys.executable, str(ROOT / "scripts/feather_review.py"), "preview",
                   "--project", str(self.project), "--scope", "project", "--user-home", str(self.user_home),
                   "--codex-home", str(self.codex_home), "--review-mode", "auto"]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["after"], "auto")
        command[2] = "apply"
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected-plan", json.loads(result.stdout)["error"])
