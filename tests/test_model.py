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
sys.path.insert(0, str(ROOT / "skills/model/scripts"))

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

    def test_crlf_model_table_preserves_line_endings(self):
        key = "assets/templates/AGENTS.md"
        self.bundle.payload[key] = self.bundle.payload[key].replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        self.install()
        self.apply("security-executor.reasoning=medium")
        target = self.project / "AGENTS.md"
        self.assertIn(b"| security-executor | gpt-6-sol | medium |\r\n", target.read_bytes())
        execute("update", self.env, self.bundle, ["delegation"], None)
        self.assertEqual(run("show", self.env, [])["roles"]["security-executor"]["reasoning"], "medium")

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

    def test_shared_entrance_upgrade_preserves_owners_and_blocks_reused_downgrade(self):
        key = "assets/templates/AGENTS.md"
        latest = self.bundle.payload[key]
        legacy = latest.replace(b"gpt-6-", b"gpt-5.6-")
        self.bundle.payload[key] = legacy
        self.install("user", "user")
        self.install("project", "user")
        target = self.codex_home / "AGENTS.md"
        target.write_bytes(b"Keep personal guidance.\n" + target.read_bytes())
        ledger_path = self.codex_home / "feather-setup/entrances.json"
        owners = json.loads(ledger_path.read_text())["blocks"]["delegation"]["owners"]
        before = {path: path.read_bytes() for path in self.base.rglob("*") if path.is_file()}
        self.bundle.payload[key] = latest
        owner = Environment(self.project, self.user_home, self.codex_home, "user")
        preview = execute("update", owner, self.bundle, ["delegation"], None, dry_run=True)
        self.assertEqual(before, {path: path.read_bytes() for path in self.base.rglob("*") if path.is_file()})
        result = execute("update", owner, self.bundle, ["delegation"], None,
                         expected_plan=preview["_plan_id"])
        self.assertIn("backup", result)
        self.assertEqual(values(target.read_text()), values(latest.decode()))
        self.assertTrue(target.read_bytes().startswith(b"Keep personal guidance.\n"))
        self.assertEqual(json.loads(ledger_path.read_text())["blocks"]["delegation"]["owners"], owners)
        self.bundle.payload[key] = legacy
        upgraded = {path: path.read_bytes() for path in self.base.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(ValueError, "cannot be shared"):
            self.install("project", "user")
        self.assertEqual(upgraded, {path: path.read_bytes() for path in self.base.rglob("*") if path.is_file()})
        with self.assertRaisesRegex(ValueError, "shared owners"):
            run("preview", self.env, ["scout.reasoning=high"])

    def test_shared_entrance_upgrade_still_preserves_manual_edits(self):
        key = "assets/templates/AGENTS.md"
        latest = self.bundle.payload[key]
        self.bundle.payload[key] = latest.replace(b"gpt-6-", b"gpt-5.6-")
        self.install("user", "user")
        self.install("project", "user")
        target = self.codex_home / "AGENTS.md"
        target.write_bytes(target.read_bytes().replace(b"gpt-5.6-luna", b"custom-model"))
        before = {path: path.read_bytes() for path in self.base.rglob("*") if path.is_file()}
        self.bundle.payload[key] = latest
        from setup_installer.conflicts import ConflictError
        with self.assertRaises(ConflictError):
            execute("update", Environment(self.project, self.user_home, self.codex_home, "user"),
                    self.bundle, ["delegation"], None)
        self.assertEqual(before, {path: path.read_bytes() for path in self.base.rglob("*") if path.is_file()})

    def test_model_edit_preserves_unrelated_guidance_and_rejects_modified_block(self):
        self.install()
        target = self.project / "AGENTS.md"
        target.write_bytes(b"Personal prefix\n" + target.read_bytes() + b"Personal suffix\n")
        self.apply("scout.reasoning=medium")
        self.assertTrue(target.read_bytes().startswith(b"Personal prefix\n"))
        self.assertTrue(target.read_bytes().endswith(b"Personal suffix\n"))
        target.write_bytes(target.read_bytes().replace(b"gpt-6-luna", b"custom-model"))
        before = {path: path.read_bytes() for path in self.base.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(ValueError, "entrance is conflict"):
            run("preview", self.env, ["scout.reasoning=high"])
        self.assertEqual(before, {path: path.read_bytes() for path in self.base.rglob("*") if path.is_file()})

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
        script = ROOT / "skills/model/scripts/model.py"
        result = subprocess.run([sys.executable, str(script), "apply", "--project", str(ROOT),
                                 "--user-home", str(self.user_home), "--codex-home", str(self.codex_home),
                                 "--set", "scout.reasoning=high"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected-plan", json.loads(result.stdout)["error"])

    def test_cli_reports_missing_dependency_as_json(self):
        script = ROOT / "skills/model/scripts/model.py"
        result = subprocess.run([sys.executable, "-S", str(script), "show", "--project", str(ROOT)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("dependency unavailable", json.loads(result.stdout)["error"])

    def test_show_and_preview_create_no_import_cache_or_installation_files(self):
        self.install()
        plugin = self.base / "plugin"
        destination = plugin / "skills/model/scripts"
        destination.mkdir(parents=True)
        shutil.copyfile(ROOT / "skills/model/scripts/model.py", destination / "model.py")
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
