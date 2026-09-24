"""Upgrade behavior for short skill names and the fifth native role."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from setup_installer.bundle import Bundle, LEGACY_ROLES, ROLES, digest
from setup_installer.discovery import reuse_candidate
from setup_installer.environment import Environment
from setup_installer.installer import execute
from setup_installer.migration import migrate
from setup_installer import entrances


class ShortNameUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.project = base / "project"
        self.project.mkdir()
        (self.project / ".git").mkdir()
        self.home = base / "home"
        self.home.mkdir()
        self.environment = Environment(self.project, self.home, self.home / ".codex")
        self.old_skill = b"---\nname: feather-handoff\ndescription: Old\n---\nold\n"
        self.new_skill = b"---\nname: handoff\ndescription: New\n---\nnew\n"
        self.bundle = self.make_bundle()
        for module in ("setup_installer.installer", "setup_installer.migration"):
            context = patch(f"{module}.find_codex", return_value={"path": "codex", "version": "test"})
            context.start()
            self.addCleanup(context.stop)

    def make_bundle(self):
        files = {"assets/skills/handoff/SKILL.md": ".agents/skills/handoff/SKILL.md"}
        payload = {"assets/skills/handoff/SKILL.md": self.new_skill,
                   "assets/templates/entrances/delegation.md": b"Role guidance",
                   "assets/templates/entrances/handoff.md": (ROOT / "templates/entrances/handoff.md").read_bytes()}
        roles = {}
        for role in ROLES:
            source = f"assets/templates/{role}.toml"
            roles[source] = f".codex/agents/{role}.toml"
            payload[source] = (f'name = "{role}"\ndescription = "Role"\n'
                               'developer_instructions = "Work"\n').encode()
        return Bundle(self.project, "2.0", {"handoff": {"files": files}, "delegation": {"files": roles}}, payload)

    def record(self, component, files, *, scope="project", **extra):
        environment = Environment(self.project, self.home, self.home / ".codex", scope)
        record = {"version": "1.2.1", "files": {target: digest(content) for target, content in files.items()},
                  "contents": {target: base64.b64encode(content).decode() for target, content in files.items()}, **extra}
        for target, content in files.items():
            path = environment.target(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        environment.state_path.parent.mkdir(parents=True, exist_ok=True)
        environment.state_path.write_text(json.dumps({"format": 1, "environment": environment.identity,
                                                     "components": {component: record}}), encoding="utf-8")
        return environment

    def legacy_entrance(self):
        """Recreate a valid v1 managed block and ledger without changing installer code."""
        link = entrances.location(self.environment, "project")
        old_instruction = (
            "Use this capability only when feather-handoff is listed among the skills available in the "
            "current environment. This declaration does not install the skill in other projects.\n\n"
            "When the user requests a handoff or continuation of recorded work, read and follow the "
            "available feather-handoff skill. Preserve its handoff-file and history rules. "
            "This entry grants no additional authorization to edit, delegate, or delete data."
        )
        block = ("\n\n<!-- feather-setup:handoff:begin -->\n" + old_instruction
                 + "\n<!-- feather-setup:handoff:end -->\n")
        outside = (b"# Project rules\nKeep this section.\n", b"\nOther instructions stay.\n")
        (self.project / "AGENTS.md").write_bytes(outside[0] + block.encode() + outside[1])
        ledger = {"format": 1, "location": link,
                  "blocks": {"handoff": {"file": "AGENTS.md", "content": block,
                                         "owners": [str(self.environment.state_path) + "#handoff"],
                                         "version": "1.2.1"}}}
        ledger_path = self.project / ".feather/setup/entrances.json"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
        return link, outside

    def test_update_moves_owned_legacy_skill_in_one_plan(self):
        old = ".agents/skills/feather-handoff/SKILL.md"
        new = ".agents/skills/handoff/SKILL.md"
        self.record("handoff", {old: self.old_skill})
        preview = execute("update", self.environment, self.bundle, ["handoff"], None, dry_run=True)
        self.assertEqual({change["action"] for change in preview["changes"]}, {"write", "remove"})
        self.assertTrue(self.environment.target(old).exists())
        execute("update", self.environment, self.bundle, ["handoff"], None,
                expected_plan=preview["_plan_id"])
        self.assertFalse(self.environment.target(old).exists())
        self.assertEqual(self.environment.target(new).read_bytes(), self.new_skill)
        self.assertEqual(set(json.loads(self.environment.state_path.read_text())["components"]["handoff"]["files"]), {new})

    def test_update_refreshes_legacy_entrance_and_keeps_handoff_history(self):
        old = ".agents/skills/feather-handoff/SKILL.md"
        link, outside = self.legacy_entrance()
        self.record("handoff", {old: self.old_skill}, entrance=link)
        history = self.project / ".feather/handoffs/history/done.md"
        history.parent.mkdir(parents=True)
        history.write_bytes(b"completed handoff\r\ncustom history bytes\n")
        execute("update", self.environment, self.bundle, ["handoff"], None)
        guidance = (self.project / "AGENTS.md").read_bytes()
        self.assertTrue(guidance.startswith(outside[0]))
        self.assertTrue(guidance.endswith(outside[1]))
        self.assertEqual(guidance.count(b"feather-setup:handoff:begin"), 1)
        self.assertIn(b"When the current work already has a handoff", guidance)
        self.assertIn(b"available handoff skill", guidance)
        self.assertNotIn(b"when feather-handoff is listed", guidance)
        self.assertEqual(history.read_bytes(), b"completed handoff\r\ncustom history bytes\n")

    def test_modified_legacy_skill_requires_explicit_replace(self):
        old = ".agents/skills/feather-handoff/SKILL.md"
        self.record("handoff", {old: self.old_skill})
        self.environment.target(old).write_bytes(self.old_skill + b"custom edit\n")
        with self.assertRaisesRegex(ValueError, "Conflict"):
            execute("update", self.environment, self.bundle, ["handoff"], None)
        self.assertFalse(self.environment.target(".agents/skills/handoff/SKILL.md").exists())
        self.assertTrue(self.environment.target(old).exists())
        execute("update", self.environment, self.bundle, ["handoff"], None, on_conflict="replace")
        self.assertFalse(self.environment.target(old).exists())

    def test_unowned_legacy_skill_and_native_alias_block_install(self):
        legacy = self.environment.target(".agents/skills/feather-handoff/SKILL.md")
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(self.old_skill)
        with self.assertRaisesRegex(ValueError, "unowned legacy handoff"):
            execute("install", self.environment, self.bundle, ["handoff"], None)
        legacy.unlink()
        alias = self.environment.target(".agents/skills/another/SKILL.md")
        alias.parent.mkdir(parents=True)
        alias.write_bytes(self.new_skill)
        with self.assertRaisesRegex(ValueError, "native handoff skill"):
            execute("install", self.environment, self.bundle, ["handoff"], None)

    def test_recorded_legacy_and_existing_new_skill_conflict(self):
        old = ".agents/skills/feather-handoff/SKILL.md"
        self.record("handoff", {old: self.old_skill})
        current = self.environment.target(".agents/skills/handoff/SKILL.md")
        current.parent.mkdir(parents=True)
        current.write_bytes(self.new_skill)
        with self.assertRaisesRegex(ValueError, "both visible"):
            execute("update", self.environment, self.bundle, ["handoff"], None)
        self.assertEqual(current.read_bytes(), self.new_skill)
        self.assertEqual(self.environment.target(old).read_bytes(), self.old_skill)

    def test_owned_legacy_conflicts_with_external_new_skill(self):
        old = ".agents/skills/feather-handoff/SKILL.md"
        self.record("handoff", {old: self.old_skill})
        # The user scope is visible to this project and has a different target root.
        user = Environment(self.project, self.home, self.home / ".codex", "user")
        visible = user.target(".agents/skills/handoff/SKILL.md")
        visible.parent.mkdir(parents=True)
        visible.write_bytes(self.new_skill)
        with self.assertRaisesRegex(ValueError, "multiple visible scopes"):
            execute("update", self.environment, self.bundle, ["handoff"], None)
        self.assertEqual(self.environment.target(old).read_bytes(), self.old_skill)
        self.assertEqual(visible.read_bytes(), self.new_skill)

    def test_four_role_owner_upgrades_and_preserves_review_mode(self):
        files = {f".codex/agents/{role}.toml": self.bundle.payload[f"assets/templates/{role}.toml"]
                 for role in LEGACY_ROLES}
        self.record("delegation", files, review_mode="off", model_overrides={"scout": {"model": "custom"}})
        execute("update", self.environment, self.bundle, ["delegation"], None)
        record = json.loads(self.environment.state_path.read_text())["components"]["delegation"]
        self.assertEqual(set(record["files"]), {f".codex/agents/{role}.toml" for role in ROLES})
        self.assertEqual(record["review_mode"], "off")
        self.assertEqual(record["model_overrides"], {"scout": {"model": "custom"}})

    def test_external_four_role_set_is_reused(self):
        for role in LEGACY_ROLES:
            path = self.environment.target(f".codex/agents/{role}.toml")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.bundle.payload[f"assets/templates/{role}.toml"])
        nested = self.project / "nested"
        nested.mkdir()
        reused = reuse_candidate(Environment(nested, self.home, self.home / ".codex"), "delegation")
        self.assertEqual(reused["status"], "reused")
        self.assertEqual(len(reused["paths"]), 4)

    def test_legacy_remove_and_scope_migration(self):
        old = ".agents/skills/feather-handoff/SKILL.md"
        self.record("handoff", {old: self.old_skill})
        migrate(self.environment, self.bundle, ["handoff"], "project", "user", None)
        user = Environment(self.project, self.home, self.home / ".codex", "user")
        self.assertFalse(self.environment.target(old).exists())
        self.assertEqual(user.target(old).read_bytes(), self.old_skill)
        execute("remove", user, self.bundle, ["handoff"], None)
        self.assertFalse(user.target(old).exists())

    def test_legacy_migration_refreshes_entrance_and_preserves_skill_and_history(self):
        old = ".agents/skills/feather-handoff/SKILL.md"
        link, outside = self.legacy_entrance()
        self.record("handoff", {old: self.old_skill}, entrance=link)
        history = self.project / ".feather/handoffs/history/done.md"
        history.parent.mkdir(parents=True)
        history.write_bytes(b"history is project data\n")
        migrate(self.environment, self.bundle, ["handoff"], "project", "user", None, entrance="user")
        user = Environment(self.project, self.home, self.home / ".codex", "user")
        self.assertEqual(user.target(old).read_bytes(), self.old_skill)
        self.assertFalse(user.target(".agents/skills/handoff/SKILL.md").exists())
        guidance = (self.home / ".codex/AGENTS.md").read_bytes()
        self.assertIn(b"available handoff skill", guidance)
        self.assertIn(b"When the current work already has a handoff", guidance)
        self.assertNotIn(b"feather-handoff", guidance)
        self.assertEqual((self.project / "AGENTS.md").read_bytes(), outside[0] + outside[1])
        self.assertEqual(history.read_bytes(), b"history is project data\n")


if __name__ == "__main__":
    unittest.main()
