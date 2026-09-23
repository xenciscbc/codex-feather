"""Behavioral tests for managed Feather model defaults."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "skills/feather-model/scripts"))

from setup_installer.bundle import Bundle, ROLES
from setup_installer.environment import Environment
from setup_installer.installer import execute
from setup_installer.migration import migrate
from setup_installer.model_settings import values
from model import run


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / ".scratch")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.project = self.base / "project"
        self.project.mkdir()
        (self.project / ".git").mkdir()
        self.user_home = self.base / "home"
        self.user_home.mkdir()
        self.codex_home = self.user_home / ".codex"
        self.env = Environment(self.project, self.user_home, self.codex_home)
        payload = {"assets/templates/AGENTS.md": (ROOT / "templates/AGENTS.md").read_bytes()}
        files = {}
        for role in ROLES:
            source = f"assets/templates/{role}.toml"
            payload[source] = (f'name = "{role}"\ndescription = "Role"\ndeveloper_instructions = "Work"\n').encode()
            files[source] = f".codex/agents/{role}.toml"
        self.bundle = Bundle(self.base, "1.2.0", {"delegation": {"files": files}}, payload)
        self.codex_patch = patch("setup_installer.installer.find_codex", return_value={"path": "codex", "version": "test"})
        self.codex_patch.start()
        self.addCleanup(self.codex_patch.stop)
        self.migrate_patch = patch("setup_installer.migration.find_codex", return_value={"path": "codex", "version": "test"})
        self.migrate_patch.start()
        self.addCleanup(self.migrate_patch.stop)

    def install(self, scope="project", entrance="project"):
        return execute("install", Environment(self.project, self.user_home, self.codex_home, scope),
                       self.bundle, ["delegation"], None, entrance=entrance)

    def apply(self, *assignments):
        before = run("preview", self.env, list(assignments))
        applied = run("apply", self.env, list(assignments), before["plan_id"])
        self.assertEqual(applied["after"], before["after"])
        return applied

    def test_show_and_partial_field_update_survive_reinstall_and_update(self):
        self.install()
        shown = run("show", self.env, [])
        self.assertEqual(shown["roles"], values((ROOT / "templates/AGENTS.md").read_text(encoding="utf-8")))
        self.assertEqual(shown["owner"]["scope"], "project")
        self.apply("scout.model=other-model")
        self.assertEqual(run("show", self.env, [])["roles"]["scout"],
                         {"model": "other-model", "reasoning": "low"})
        self.install()
        execute("update", self.env, self.bundle, ["delegation"], None)
        self.assertEqual(run("show", self.env, [])["roles"]["scout"]["model"], "other-model")
        state = json.loads(self.env.state_path.read_text())
        self.assertEqual(state["components"]["delegation"]["model_overrides"],
                         {"scout": {"model": "other-model"}})
        self.assertNotIn(b"model =", (self.project / ".codex/agents/scout.toml").read_bytes())

    def test_preview_is_read_only_and_fingerprint_guards_apply(self):
        self.install()
        before = {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        preview = run("preview", self.env, ["analyst.reasoning=max"])
        self.assertEqual(before, {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()})
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            run("apply", self.env, ["analyst.reasoning=low"], preview["plan_id"])
        self.assertEqual(before, {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()})
        self.apply("analyst.reasoning=max")
        self.assertEqual(run("show", self.env, [])["roles"]["analyst"]["reasoning"], "max")

    def test_migration_preserves_field_override(self):
        self.install()
        self.apply("executor.reasoning=ultra")
        migrate(self.env, self.bundle, ["delegation"], "project", "user", None, entrance="user")
        shown = run("show", self.env, [])
        self.assertEqual(shown["owner"]["scope"], "user")
        self.assertEqual(shown["roles"]["executor"]["reasoning"], "ultra")

    def test_reused_user_owner_and_conflicting_project_entrance(self):
        self.install("user", "user")
        nested = self.project / "nested"
        nested.mkdir()
        self.assertEqual(run("show", Environment(nested, self.user_home, self.codex_home), [])["owner"]["scope"], "user")
        self.env = Environment(nested, self.user_home, self.codex_home)
        self.apply("scout.reasoning=high")
        project_guidance = self.project / "AGENTS.md"
        project_guidance.write_text("<!-- feather-setup:delegation:begin -->\nother table\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Another visible delegation entrance"):
            run("show", self.env, [])

    def test_reused_owner_cannot_rewrite_entrance_or_accept_role_alias(self):
        self.install("user", "user")
        self.apply("scout.model=custom-model")
        entrance = self.codex_home / "AGENTS.md"
        before = entrance.read_bytes()
        with self.assertRaisesRegex(ValueError, "cannot be shared"):
            self.install("project", "user")
        self.assertEqual(entrance.read_bytes(), before)
        alias = self.codex_home / "agents/renamed.toml"
        alias.write_text('name = "scout"\ndescription = "Alias"\ndeveloper_instructions = "Work"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already declared"):
            run("show", self.env, [])

    def test_identical_plain_entrance_can_still_be_shared_by_setup(self):
        self.install("user", "user")
        self.install("project", "user")
        ledger = json.loads((self.codex_home / "feather-setup/entrances.json").read_text())
        self.assertEqual(len(ledger["blocks"]["delegation"]["owners"]), 2)
        with self.assertRaisesRegex(ValueError, "shared owners"):
            run("show", self.env, [])

    def test_native_role_binding_is_rejected(self):
        source = "assets/templates/scout.toml"
        self.bundle.payload[source] += b'model = "locked-model"\n'
        self.install()
        with self.assertRaisesRegex(ValueError, "Native role binding"):
            run("show", self.env, [])

    def test_missing_entrance_and_unmanaged_roles_are_rejected(self):
        self.install(entrance="none")
        shown = run("show", self.env, [])
        self.assertEqual(shown["owner"]["entrance"]["status"], "missing")
        with self.assertRaisesRegex(ValueError, "No managed delegation entrance"):
            run("preview", self.env, ["scout.model=another"])
        execute("remove", self.env, self.bundle, ["delegation"], None)
        role = self.project / ".codex/agents/scout.toml"
        role.parent.mkdir(parents=True, exist_ok=True)
        role.write_text('name = "scout"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            run("show", self.env, [])

    def test_cli_outputs_json_error(self):
        script = ROOT / "skills/feather-model/scripts/model.py"
        result = subprocess.run([sys.executable, str(script), "apply", "--project", str(ROOT),
                                 "--user-home", str(self.user_home), "--codex-home", str(self.codex_home),
                                 "--set", "scout.reasoning=high"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected-plan", json.loads(result.stdout)["error"])

    def test_cli_reports_missing_dependency_as_json(self):
        script = ROOT / "skills/feather-model/scripts/model.py"
        result = subprocess.run([sys.executable, "-S", str(script), "show", "--project", str(ROOT)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("dependency unavailable", json.loads(result.stdout)["error"])

    def test_show_and_preview_create_no_import_cache_or_installation_files(self):
        self.install()
        plugin = self.base / "plugin"
        destination = plugin / "skills/feather-model/scripts"
        destination.mkdir(parents=True)
        shutil.copyfile(ROOT / "skills/feather-model/scripts/model.py", destination / "model.py")
        shutil.copytree(ROOT / "scripts/setup_installer", plugin / "scripts/setup_installer",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (plugin / "templates").mkdir()
        shutil.copyfile(ROOT / "templates/AGENTS.md", plugin / "templates/AGENTS.md")
        before = {path.relative_to(self.base): path.read_bytes() for path in self.base.rglob("*") if path.is_file()}
        for action, extra in (("show", []), ("preview", ["--set", "scout.reasoning=max"])):
            result = subprocess.run([sys.executable, str(destination / "model.py"), action,
                                     "--project", str(self.project), "--user-home", str(self.user_home),
                                     "--codex-home", str(self.codex_home), *extra],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = {path.relative_to(self.base): path.read_bytes() for path in self.base.rglob("*") if path.is_file()}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
