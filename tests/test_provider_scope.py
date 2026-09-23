"""Standalone writes must respect visible plugin-backed handoff ownership."""
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_upgrade_short_names as fixtures
from setup_installer.installer import execute
from setup_installer.migration import migrate


class ProviderScopeTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ShortNameUpgradeTests()
        self.addCleanup(self.fixture.doCleanups)
        runs = fixtures.ROOT / ".scratch/feather-setup/runs"
        runs.mkdir(parents=True, exist_ok=True)
        temporary_directory = fixtures.tempfile.TemporaryDirectory
        with patch.object(fixtures.tempfile, "TemporaryDirectory", side_effect=lambda: temporary_directory(dir=runs)):
            self.fixture.setUp()
        self.environment = self.fixture.environment
        self.bundle = self.fixture.bundle
        self.root = Path(self.fixture.temporary.name)
        self.provider = self.root / "plugin/SKILL.md"
        self.provider.parent.mkdir()
        self.provider.write_bytes(self.fixture.new_skill)

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def install_plugin(self, environment):
        execute("install", environment, self.bundle, ["handoff"], None,
                entrance=environment.scope, handoff_provider=self.provider)

    def test_other_scope_plugin_blocks_standalone_install_without_writes(self):
        for owner_scope, target_scope in (("user", "project"), ("project", "user")):
            with self.subTest(owner=owner_scope):
                owner = replace(self.environment, scope=owner_scope)
                target = replace(self.environment, scope=target_scope)
                self.install_plugin(owner)
                before = self.files()
                with self.assertRaisesRegex(ValueError, "[Pp]lugin handoff"):
                    execute("install", target, self.bundle, ["handoff"], None)
                self.assertEqual(self.files(), before)
                execute("remove", owner, self.bundle, ["handoff"], None)

    def test_ancestor_plugin_blocks_nested_standalone_install(self):
        self.install_plugin(self.environment)
        nested = self.environment.project / "child"
        nested.mkdir()
        before = self.files()
        with self.assertRaisesRegex(ValueError, "[Pp]lugin handoff"):
            execute("install", replace(self.environment, project=nested), self.bundle, ["handoff"], None)
        self.assertEqual(self.files(), before)

    def test_standalone_update_and_migration_preserve_conflicting_provider(self):
        nested = self.environment.project / "child"
        nested.mkdir()
        source = replace(self.environment, project=nested)
        execute("install", source, self.bundle, ["handoff"], None)
        self.install_plugin(self.environment)
        before = self.files()
        with self.assertRaisesRegex(ValueError, "[Pp]lugin handoff"):
            execute("update", source, self.bundle, ["handoff"], None)
        with self.assertRaisesRegex(ValueError, "[Pp]lugin handoff"):
            migrate(source, self.bundle, ["handoff"], "project", "user", None)
        self.assertEqual(self.files(), before)

    def test_invalid_provider_record_is_not_treated_as_an_empty_scope(self):
        owner = replace(self.environment, scope="user")
        owner.state_path.parent.mkdir(parents=True)
        for record in ("invalid", {"files": []}, {"files": {}, "provider": "plugin"}):
            with self.subTest(record=record):
                owner.state_path.write_text(json.dumps({"format": 1, "environment": owner.identity,
                                                       "components": {"handoff": record}}), encoding="utf-8")
                before = self.files()
                with self.assertRaisesRegex(ValueError, "Invalid installation"):
                    execute("install", self.environment, self.bundle, ["handoff"], None)
                self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
