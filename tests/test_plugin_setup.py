"""Integration checks for the native plugin's installer wrapper."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


def native_codex():
    configured = os.environ.get("FEATHER_TEST_CODEX")
    if configured:
        return Path(configured) if Path(configured).is_file() else None
    on_path = shutil.which("codex.exe" if os.name == "nt" else "codex")
    if on_path:
        return Path(on_path)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local_app_data:
        root = Path(local_app_data) / "OpenAI/Codex/bin"
        candidates = (path for path in root.glob("*/codex.exe") if path.is_file())
        return next(iter(sorted(candidates, key=lambda path: path.stat().st_mtime_ns, reverse=True)), None)
    return None


class PluginSetupTest(unittest.TestCase):
    def setUp(self):
        if sys.version_info < (3, 11):
            self.skipTest("Plugin setup requires Python 3.11+")
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("Plugin setup requires PyYAML")
        self.codex = native_codex()
        if self.codex is None:
            self.skipTest("Native Codex is required; set FEATHER_TEST_CODEX")
        runs = ROOT / ".scratch/feather-setup/runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=runs)
        self.directory = Path(self.temporary.name)

        def cleanup():
            if not self.directory.resolve().is_relative_to(runs.resolve()):
                raise AssertionError("Refusing cleanup outside isolated run root")
            deadline = time.monotonic() + 3
            while True:
                try:
                    self.temporary.cleanup()
                    return
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)

        self.addCleanup(cleanup)
        self.plugin = self.directory / "plugin cache/codex-feather"
        self.plugin.mkdir(parents=True)
        for name in (".codex-plugin", "templates", "scripts", "skills/setup", "skills/handoff", "skills/model", "skills/auto-on", "skills/auto-off", "docs"):
            source = ROOT / name
            target = self.plugin / name
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.project = self.directory / "project with spaces"
        self.project.mkdir()
        self.user_home = self.directory / "user"
        self.codex_home = self.user_home / ".codex"
        self.other_cwd = self.directory / "unrelated cwd"
        self.other_cwd.mkdir()
        self.existing_agents = "# Local instructions\nKeep this paragraph.\n"
        (self.project / "AGENTS.md").write_text(self.existing_agents, encoding="utf-8")
        handoff = self.project / ".feather/handoffs/work.md"
        handoff.parent.mkdir(parents=True)
        handoff.write_text("My handoff data\n", encoding="utf-8")

    def plugin_files(self):
        return {path.relative_to(self.plugin).as_posix(): path.read_bytes()
                for path in self.plugin.rglob("*") if path.is_file()}

    def target_files(self):
        return {path.relative_to(self.directory).as_posix(): path.read_bytes()
                for root in (self.project, self.user_home, self.other_cwd)
                for path in root.rglob("*") if path.is_file()}

    def run_setup(self, action=None, *extra, project=True, default_components=True):
        command = [sys.executable, str(self.plugin / "skills/setup/scripts/setup.py")]
        if action is not None:
            command.append(action)
        if project:
            command += ["--project", str(self.project)]
        if default_components and action != "check" and not any(arg == "--components" or str(arg).startswith("--components=") for arg in extra):
            command += ["--components", "delegation"]
        command += ["--user-home", str(self.user_home), "--codex-home", str(self.codex_home),
                    "--codex", str(self.codex), "--json", *map(str, extra)]
        environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("CODEX_")}
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.update(PYTHONUTF8="1", GIT_OPTIONAL_LOCKS="1", HOME=str(self.user_home),
                           USERPROFILE=str(self.user_home))
        return subprocess.run(command, cwd=self.other_cwd, env=environment, capture_output=True,
                              text=True, encoding="utf-8", timeout=45)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_dry_run_preserves_all_targets_and_plugin_source(self):
        source_before = self.plugin_files()
        targets_before = self.target_files()
        report = self.assert_success(self.run_setup("install", "--entrance", "project", "--dry-run"))
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["components"]["delegation"]["status"], "would-install")
        self.assertEqual(self.target_files(), targets_before)
        self.assertEqual(self.plugin_files(), source_before)
        self.assertFalse(any(path.name == "__pycache__" for path in self.plugin.rglob("*")))

    def test_git_backed_cache_is_unchanged_by_check_and_preview(self):
        git_executable = shutil.which("git")
        if git_executable is None:
            self.skipTest("Git is required for the native Git-cache regression")
        git = [git_executable, "-c", f"safe.directory={self.plugin.as_posix()}",
               "-c", "user.name=Feather Test", "-c", "user.email=feather@example.invalid",
               "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={self.directory / 'no-hooks'}"]

        def run_git(*arguments):
            result = subprocess.run([*git, *arguments], cwd=self.plugin, capture_output=True,
                                    text=True, encoding="utf-8", timeout=30,
                                    env={**os.environ, "GIT_OPTIONAL_LOCKS": "1"})
            self.assertEqual(result.returncode, 0, result.stderr)

        run_git("init")
        run_git("add", "templates/scout.toml")
        run_git("commit", "-m", "Track a plugin template")
        # Simulate stale index stat data after a Git snapshot is copied into a cache.
        template = self.plugin / "templates/scout.toml"
        timestamp = template.stat()
        os.utime(template, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns + 2_000_000_000))
        source_before = self.plugin_files()
        targets_before = self.target_files()
        for action, options, expected_code in (("check", (), 1), ("install", ("--dry-run",), 0)):
            with self.subTest(action=action):
                result = self.run_setup(action, *options)
                self.assertEqual(result.returncode, expected_code, result.stderr + result.stdout)
                self.assertEqual(self.plugin_files(), source_before)
                self.assertEqual(self.target_files(), targets_before)
        # Positive control: the fixture really does require an index refresh.
        run_git("status", "--porcelain", "--untracked-files=no")
        self.assertNotEqual((self.plugin / ".git/index").read_bytes(), source_before[".git/index"])

    def test_delegation_lifecycle_preserves_unrelated_content_and_handoff(self):
        source_before = self.plugin_files()
        installed = self.assert_success(self.run_setup("install", "--entrance", "project"))
        self.assertEqual(installed["components"]["delegation"]["status"], "installed")
        for role in ("scout", "analyst", "mech-executor", "executor", "security-executor"):
            self.assertEqual((self.project / f".codex/agents/{role}.toml").read_bytes(),
                             (self.plugin / f"templates/{role}.toml").read_bytes())
        agents = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(self.existing_agents, agents)
        self.assertIn("feather-setup:delegation:begin", agents)
        self.assertFalse((self.project / ".agents/skills/handoff").exists())
        self.assertEqual((self.project / ".feather/handoffs/work.md").read_text(), "My handoff data\n")
        checked = self.assert_success(self.run_setup("check"))
        self.assertEqual(checked["components"]["delegation"]["status"], "installed")
        self.assert_success(self.run_setup("update"))
        removed = self.assert_success(self.run_setup("remove"))
        self.assertEqual(removed["components"]["delegation"]["status"], "removed")
        self.assertEqual((self.project / "AGENTS.md").read_text(encoding="utf-8"), self.existing_agents)
        self.assertEqual((self.project / ".feather/handoffs/work.md").read_text(), "My handoff data\n")
        self.assertFalse((self.project / ".agents/skills/handoff").exists())
        self.assertEqual(self.plugin_files(), source_before)

    def test_existing_standalone_handoff_is_untouched_by_default(self):
        existing = self.project / ".agents/skills/handoff/SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("My standalone handoff\n", encoding="utf-8")
        self.assert_success(self.run_setup("install"))
        self.assert_success(self.run_setup("update"))
        self.assert_success(self.run_setup("remove"))
        self.assertEqual(existing.read_text(encoding="utf-8"), "My standalone handoff\n")
        self.assertEqual((self.project / ".feather/handoffs/work.md").read_text(), "My handoff data\n")

    def test_user_scope_install_and_project_to_user_migration(self):
        self.assert_success(self.run_setup("install", "--scope", "user", "--entrance", "user"))
        for role in ("scout", "analyst", "mech-executor", "executor", "security-executor"):
            self.assertEqual((self.codex_home / f"agents/{role}.toml").read_bytes(),
                             (self.plugin / f"templates/{role}.toml").read_bytes())
        self.assertIn("feather-setup:delegation:begin", (self.codex_home / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual((self.project / "AGENTS.md").read_text(encoding="utf-8"), self.existing_agents)
        self.assertFalse((self.user_home / ".agents/skills/handoff").exists())
        self.assert_success(self.run_setup("remove", "--scope", "user"))
        self.assert_success(self.run_setup("install", "--entrance", "project"))
        self.assert_success(self.run_setup("migrate", "--from", "project", "--to", "user"))
        self.assertFalse((self.project / ".codex/agents/scout.toml").exists())
        self.assertTrue((self.codex_home / "agents/scout.toml").exists())
        self.assertIn("feather-setup:delegation:begin", (self.project / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual((self.project / ".feather/handoffs/work.md").read_text(), "My handoff data\n")
        self.assertFalse((self.user_home / ".agents/skills/handoff").exists())

    def install_standalone_handoff(self, entrance="none"):
        bundle = self.directory / "legacy bundle"
        prepared = subprocess.run([sys.executable, "-B", str(self.plugin / "scripts/build_setup.py"),
                                   "--prepare-only", "--output", str(bundle)],
                                  cwd=self.other_cwd, capture_output=True, text=True, encoding="utf-8", timeout=45)
        self.assertEqual(prepared.returncode, 0, prepared.stderr + prepared.stdout)
        command = [sys.executable, "-B", str(self.plugin / "scripts/feather_setup.py"), "install",
                   "--project", str(self.project), "--user-home", str(self.user_home),
                   "--codex-home", str(self.codex_home), "--codex", str(self.codex),
                   "--bundle", str(bundle), "--components", "handoff", "--entrance", entrance, "--json"]
        legacy = subprocess.run(command, cwd=self.other_cwd, capture_output=True, text=True,
                                encoding="utf-8", timeout=45)
        self.assertEqual(legacy.returncode, 0, legacy.stderr + legacy.stdout)

    def test_explicit_handoff_remove_cleans_legacy_installation_only(self):
        self.install_standalone_handoff()
        skill = self.project / ".agents/skills/handoff/SKILL.md"
        self.assertTrue(skill.exists())
        self.assert_success(self.run_setup("remove", "--components", "handoff"))
        self.assertFalse(skill.exists())
        self.assertEqual((self.project / "AGENTS.md").read_text(encoding="utf-8"), self.existing_agents)
        self.assertEqual((self.project / ".feather/handoffs/work.md").read_text(), "My handoff data\n")

    def test_custom_role_conflict_is_preserved(self):
        role = self.project / ".codex/agents/scout.toml"
        role.parent.mkdir(parents=True)
        role.write_text('name = "my-scout"\n', encoding="utf-8")
        result = self.run_setup("install")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(role.read_text(encoding="utf-8"), 'name = "my-scout"\n')
        self.assertFalse((role.parent / "analyst.toml").exists())
        self.assertFalse((self.project / ".feather/setup/state.json").exists())

    def test_wrapper_requires_explicit_mutation_components_and_owns_its_bundle(self):
        before = self.target_files()
        for args in (("install",),
                     ("install", "--bundle", self.directory / "other bundle"),
                     ("install", "--interactive")):
            with self.subTest(args=args):
                result = self.run_setup(*args, default_components=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Choose --components" if len(args) == 1 else "plugin supplies its own bundle", result.stderr)
        missing = self.run_setup("install", "--components", "delegation", project=False)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("--project", missing.stderr)
        self.assertEqual(self.target_files(), before)

    def test_update_uses_new_plugin_template_payload(self):
        self.assert_success(self.run_setup("install"))
        role = self.project / ".codex/agents/scout.toml"
        template = self.plugin / "templates/scout.toml"
        marker = "\n# latest plugin payload marker\n"
        template.write_text(template.read_text(encoding="utf-8") + marker, encoding="utf-8")
        report = self.assert_success(self.run_setup("update"))
        self.assertEqual(report["components"]["delegation"]["status"], "installed")
        self.assertIn(marker, role.read_text(encoding="utf-8"))
        state = json.loads((self.project / ".feather/setup/state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["components"]["delegation"]["version"],
                         json.loads((self.plugin / ".codex-plugin/plugin.json").read_text())["version"])

    def test_abbreviated_components_cannot_bypass_handoff_install_guard(self):
        before = self.target_files()
        for options in (("--components", "delegation", "--comp", "handoff"),
                        ("--comp", "handoff", "--components", "delegation"),
                        ("--components", "delegation", "--comp=all")):
            with self.subTest(options=options):
                result = self.run_setup("install", *options)
                self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
                self.assertIn("unrecognized arguments", result.stderr)
                self.assertEqual(self.target_files(), before)

    def test_abbreviated_removal_target_cannot_remove_delegation(self):
        self.assert_success(self.run_setup("install", "--entrance", "project"))
        before = self.target_files()
        for options in (("--comp", "handoff"), ("--comp=handoff",)):
            with self.subTest(options=options):
                result = self.run_setup("remove", *options)
                self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
                self.assertIn("unrecognized arguments", result.stderr)
                self.assertEqual(self.target_files(), before)
        # A valid explicit handoff removal still leaves the installed roles untouched.
        report = self.assert_success(self.run_setup("remove", "--components", "handoff"))
        self.assertEqual(report["components"]["handoff"]["status"], "not-managed")
        self.assertEqual(self.target_files(), before)

    def test_missing_runtime_dependency_stops_before_target_writes(self):
        before = self.target_files()
        result = subprocess.run(
            [sys.executable, "-S", str(self.plugin / "skills/setup/scripts/setup.py"),
             "install", "--project", str(self.project), "--user-home", str(self.user_home),
             "--codex-home", str(self.codex_home), "--components", "delegation"],
            cwd=self.other_cwd, capture_output=True, text=True, encoding="utf-8", timeout=45)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires PyYAML", result.stderr)
        self.assertEqual(self.target_files(), before)

    def test_plugin_handoff_only_owns_guidance_and_preserves_data(self):
        source_before = self.plugin_files()
        preview_before = self.target_files()
        preview = self.assert_success(self.run_setup("install", "--components", "handoff", "--dry-run"))
        self.assertEqual(preview["components"]["handoff"]["status"], "would-install")
        self.assertEqual(self.target_files(), preview_before)
        installed = self.assert_success(self.run_setup("install", "--components", "handoff"))
        self.assertEqual(installed["components"]["handoff"]["status"], "installed")
        self.assertEqual(installed["components"]["handoff"]["provider"]["kind"], "plugin")
        state = json.loads((self.project / ".feather/setup/state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["components"]["handoff"]["files"], {})
        self.assertFalse((self.project / ".agents/skills/handoff").exists())
        self.assertFalse((self.project / ".codex/agents/scout.toml").exists())
        agents = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("feather-setup:handoff:begin", agents)
        self.assertIn("meaningful milestones, blockers, and completion", agents)
        checked = self.assert_success(self.run_setup("check", "--components", "handoff"))
        self.assertEqual(checked["components"]["handoff"]["status"], "installed")
        self.assertEqual(checked["components"]["handoff"]["provider"]["session"], "unconfirmed")
        self.assert_success(self.run_setup("remove", "--components", "handoff"))
        self.assertEqual((self.project / "AGENTS.md").read_text(encoding="utf-8"), self.existing_agents)
        self.assertEqual((self.project / ".feather/handoffs/work.md").read_text(), "My handoff data\n")
        self.assertEqual(self.plugin_files(), source_before)

    def test_all_components_are_independent_and_remove_is_partial(self):
        self.assert_success(self.run_setup("install", "--components", "all"))
        self.assertTrue((self.project / ".codex/agents/scout.toml").exists())
        self.assertIn("feather-setup:handoff:begin", (self.project / "AGENTS.md").read_text(encoding="utf-8"))
        self.assert_success(self.run_setup("remove", "--components", "handoff"))
        self.assertTrue((self.project / ".codex/agents/scout.toml").exists())
        self.assertNotIn("feather-setup:handoff:begin", (self.project / "AGENTS.md").read_text(encoding="utf-8"))
        self.assert_success(self.run_setup("install", "--components", "handoff"))
        self.assert_success(self.run_setup("remove", "--components", "delegation"))
        self.assertFalse((self.project / ".codex/agents/scout.toml").exists())
        self.assertIn("feather-setup:handoff:begin", (self.project / "AGENTS.md").read_text(encoding="utf-8"))

    def test_plugin_provider_change_requires_update_and_rebinds(self):
        self.assert_success(self.run_setup("install", "--components", "handoff"))
        skill = self.plugin / "skills/handoff/SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\n<!-- new plugin version -->\n", encoding="utf-8")
        checked = json.loads(self.run_setup("check", "--components", "handoff").stdout)
        self.assertEqual(checked["components"]["handoff"]["status"], "provider-changed")
        self.assert_success(self.run_setup("update", "--components", "handoff"))
        checked = self.assert_success(self.run_setup("check", "--components", "handoff"))
        self.assertEqual(checked["components"]["handoff"]["status"], "installed")
        self.assertFalse((self.project / ".agents/skills/handoff").exists())

    def test_plugin_handoff_migrates_zero_file_record(self):
        self.assert_success(self.run_setup("install", "--components", "handoff"))
        self.assert_success(self.run_setup("migrate", "--components", "handoff", "--from", "project", "--to", "user"))
        source = json.loads((self.project / ".feather/setup/state.json").read_text(encoding="utf-8"))
        destination = json.loads((self.codex_home / "feather-setup/state.json").read_text(encoding="utf-8"))
        self.assertNotIn("handoff", source["components"])
        self.assertEqual(destination["components"]["handoff"]["files"], {})
        self.assertEqual((self.project / ".feather/handoffs/work.md").read_text(), "My handoff data\n")

    def test_plugin_handoff_rejects_existing_standalone_and_explicit_no_entrance(self):
        before = self.target_files()
        no_entrance = self.run_setup("install", "--components", "handoff", "--entrance", "none")
        self.assertNotEqual(no_entrance.returncode, 0)
        self.assertEqual(self.target_files(), before)
        existing = self.project / ".agents/skills/handoff/SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("My standalone handoff\n", encoding="utf-8")
        result = self.run_setup("install", "--components", "handoff")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(existing.read_text(encoding="utf-8"), "My standalone handoff\n")
        self.assertFalse((self.project / ".feather/setup/state.json").exists())

    def test_plugin_handoff_check_detects_later_standalone_collision(self):
        self.assert_success(self.run_setup("install", "--components", "handoff"))
        existing = self.project / ".agents/skills/handoff/SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("Unmanaged duplicate\n", encoding="utf-8")
        checked = self.run_setup("check", "--components", "handoff")
        self.assertEqual(checked.returncode, 1)
        self.assertEqual(json.loads(checked.stdout)["components"]["handoff"]["status"], "conflict")
        update = self.run_setup("update", "--components", "handoff")
        self.assertNotEqual(update.returncode, 0)
        self.assertEqual(existing.read_text(encoding="utf-8"), "Unmanaged duplicate\n")

    def test_plugin_handoff_migration_rejects_destination_standalone(self):
        self.assert_success(self.run_setup("install", "--components", "handoff"))
        existing = self.user_home / ".agents/skills/handoff/SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("Unmanaged user skill\n", encoding="utf-8")
        result = self.run_setup("migrate", "--components", "handoff", "--from", "project", "--to", "user")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(existing.read_text(encoding="utf-8"), "Unmanaged user skill\n")
        state = json.loads((self.project / ".feather/setup/state.json").read_text(encoding="utf-8"))
        self.assertIn("handoff", state["components"])

    def test_repeat_install_preserves_existing_entrance_selection(self):
        self.assert_success(self.run_setup("install", "--components", "delegation", "--entrance", "none"))
        self.assert_success(self.run_setup("install", "--components", "delegation"))
        self.assertEqual((self.project / "AGENTS.md").read_text(encoding="utf-8"), self.existing_agents)
        self.assert_success(self.run_setup("install", "--components", "handoff", "--entrance", "user"))
        self.assert_success(self.run_setup("install", "--components", "handoff"))
        self.assertNotIn("feather-setup:handoff:begin", (self.project / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn("feather-setup:handoff:begin", (self.codex_home / "AGENTS.md").read_text(encoding="utf-8"))

    def test_handoff_only_does_not_require_delegation_runtime(self):
        config = self.codex_home / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("[agents]\nenabled = false\n", encoding="utf-8")
        self.assert_success(self.run_setup("install", "--components", "handoff"))
        refused = self.run_setup("install", "--components", "delegation")
        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse((self.project / ".codex/agents/scout.toml").exists())

    def test_both_install_rolls_back_when_delegation_conflicts(self):
        role = self.project / ".codex/agents/scout.toml"
        role.parent.mkdir(parents=True)
        role.write_text('name = "custom-scout"\n', encoding="utf-8")
        before = self.target_files()
        refused = self.run_setup("install", "--components", "all")
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.target_files(), before)
        self.assertNotIn("feather-setup:handoff:begin", (self.project / "AGENTS.md").read_text(encoding="utf-8"))

    def test_handoff_update_preserves_delegation_files_state_and_guidance(self):
        self.assert_success(self.run_setup("install", "--components", "all"))
        state_path = self.project / ".feather/setup/state.json"
        record = json.loads(state_path.read_text(encoding="utf-8"))["components"]["delegation"]
        roles = {path.name: path.read_bytes() for path in (self.project / ".codex/agents").glob("*.toml")}
        ledger_path = self.project / ".feather/setup/entrances.json"
        guidance = json.loads(ledger_path.read_text(encoding="utf-8"))["blocks"]["delegation"]
        skill = self.plugin / "skills/handoff/SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\n<!-- updated source -->\n", encoding="utf-8")
        self.assert_success(self.run_setup("update", "--components", "handoff"))
        self.assertEqual(json.loads(state_path.read_text(encoding="utf-8"))["components"]["delegation"], record)
        self.assertEqual(json.loads(ledger_path.read_text(encoding="utf-8"))["blocks"]["delegation"], guidance)
        self.assertEqual({path.name: path.read_bytes() for path in (self.project / ".codex/agents").glob("*.toml")}, roles)

    def test_plugin_migration_rejects_unowned_standalone_at_source(self):
        self.assert_success(self.run_setup("install", "--components", "handoff"))
        duplicate = self.project / ".agents/skills/handoff/SKILL.md"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text("---\nname: handoff\ndescription: Existing standalone\n---\n", encoding="utf-8")
        before = self.target_files()
        migrated = self.run_setup("migrate", "--components", "handoff", "--from", "project", "--to", "user", "--entrance", "user")
        self.assertNotEqual(migrated.returncode, 0, migrated.stdout)
        self.assertEqual(self.target_files(), before)

    def test_check_keeps_delegation_results_when_standalone_path_is_invalid(self):
        self.assert_success(self.run_setup("install", "--components", "all"))
        invalid = self.project / ".agents/skills/handoff/SKILL.md"
        invalid.mkdir(parents=True)
        checked = self.run_setup("check")
        self.assertEqual(checked.returncode, 1)
        self.assertTrue(checked.stdout, checked.stderr)
        report = json.loads(checked.stdout)
        self.assertEqual(report["components"]["handoff"]["status"], "conflict")
        self.assertEqual(report["components"]["delegation"]["status"], "installed")
        self.assertEqual(report["entrances"]["handoff"]["status"], "installed")

    def test_plugin_check_reports_owned_standalone_and_its_guidance(self):
        self.install_standalone_handoff(entrance="project")
        before = self.target_files()
        checked = self.assert_success(self.run_setup("check", "--components", "handoff"))
        self.assertEqual(checked["components"]["handoff"]["status"], "installed")
        self.assertEqual(checked["components"]["handoff"]["provider"]["kind"], "standalone")
        self.assertEqual(checked["entrances"]["handoff"]["status"], "installed")
        self.assertEqual(self.target_files(), before)


if __name__ == "__main__":
    unittest.main()
