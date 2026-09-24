"""Exercise the public installer command against isolated homes and projects."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from setup_native import capture_tools, registered_tools, render_messages, skill_paths


ROOT = Path(__file__).resolve().parents[1]
CODEX = os.environ.get("FEATHER_TEST_CODEX") or shutil.which("codex.exe" if os.name == "nt" else "codex")


class SetupTest(unittest.TestCase):
    def setUp(self):
        runs = ROOT / ".scratch/feather-setup/runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=runs)
        self.directory = Path(self.temporary.name)

        def cleanup_trial():
            if not self.directory.resolve().is_relative_to(runs.resolve()):
                raise AssertionError("Refusing cleanup outside the isolated trial root")
            deadline = time.monotonic() + 3
            while True:
                try:
                    self.temporary.cleanup()
                    return
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)  # Native Codex/Git can release temporary handles just after exit.

        self.addCleanup(cleanup_trial)
        self.project = self.directory / "project with spaces"
        self.project.mkdir()
        (self.project / "notes.txt").write_text("keep my project\n", encoding="utf-8")
        self.user_home = self.directory / "user"
        self.codex_home = self.user_home / ".codex"
        self.bundle = self.directory / "bundle"
        skill = self.bundle / "assets/skills/handoff/SKILL.md"
        skill.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "skills/handoff/SKILL.md", skill)
        shutil.copytree(ROOT / "templates/entrances", self.bundle / "assets/templates/entrances")
        self.write_manifest()

    def write_manifest(self, version="0.1.0"):
        files = {path.relative_to(self.bundle).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted((self.bundle / "assets").rglob("*")) if path.is_file()}
        (self.bundle / "bundle.json").write_text(json.dumps({
            "format": 1, "version": version, "files": files,
            "components": {"handoff": {"files": {
                source: source.replace("assets/skills/", ".agents/skills/", 1)
                for source in files if source.startswith("assets/skills/")}},
                **({"delegation": {"files": {
                    **{source: ".codex/agents/" + Path(source).name
                       for source in files if source.startswith("assets/templates/") and source.endswith(".toml")},
                    "assets/templates/feather-delegation/SKILL.md": ".agents/skills/feather-delegation/SKILL.md"}}}
                   if any(source.endswith(".toml") for source in files) else {})},
        }), encoding="utf-8")

    def add_delegation(self):
        templates = self.bundle / "assets/templates"
        templates.mkdir(parents=True, exist_ok=True)
        for source in (ROOT / "templates").glob("*.toml"):
            shutil.copyfile(source, templates / source.name)
        shutil.copytree(ROOT / "templates/feather-delegation", templates / "feather-delegation")
        self.write_manifest()

    def test_handoff_update_uses_bundled_template_and_preserves_other_guidance(self):
        target = self.project / "AGENTS.md"
        target.write_text("Project instructions\n", encoding="utf-8")
        result = self.run_setup("install", "--components", "handoff", "--entrance", "project")
        self.assertEqual(result.returncode, 0, result.stderr)
        template = self.bundle / "assets/templates/entrances/handoff.md"
        template.write_text(template.read_text(encoding="utf-8") + "\nUpdated handoff guidance.\n", encoding="utf-8")
        self.write_manifest()
        result = self.run_setup("update", "--components", "handoff")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.read_text(encoding="utf-8").startswith("Project instructions\n"))
        self.assertIn("Updated handoff guidance.", target.read_text(encoding="utf-8"))
        self.assertEqual(target.read_text().count("feather-setup:handoff:begin"), 1)

    def test_missing_handoff_template_rejects_install_without_writes(self):
        (self.bundle / "assets/templates/entrances/handoff.md").unlink()
        self.write_manifest()
        result = self.run_setup("install", "--components", "handoff", "--entrance", "project")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("entrance template is required", result.stderr)
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertFalse((self.project / ".agents").exists())

    def run_setup(self, action, *arguments, codex=CODEX, input=None, environment=None, fail_replace=(), fail_unlink=(), pause_replace=None, edit_after_read=None):
        executable = os.environ.get("FEATHER_TEST_INSTALLER")
        command = [executable] if executable else [sys.executable, str(ROOT / "scripts/feather_setup.py")]
        if fail_replace or fail_unlink or pause_replace or edit_after_read:
            if executable:
                self.skipTest("Filesystem fault adapter exercises the source CLI; native binaries use real filesystem checks")
            wrapper = self.directory / "filesystem_fault.py"
            wrapper.write_text(
                "import os, pathlib, runpy, sys, time\n"
                "original_replace = os.replace\n"
                "original_unlink = os.unlink\n"
                "original_read = pathlib.Path.read_bytes\n"
                f"targets = {list(fail_replace)!r}\n"
                f"unlink_targets = {list(fail_unlink)!r}\n"
                f"pause = {pause_replace!r}\n"
                f"edit_after_read = {edit_after_read!r}\n"
                "edited = False\n"
                "def read(path):\n"
                "    global edited\n"
                "    content = original_read(path)\n"
                "    if edit_after_read and not edited and str(path) == edit_after_read[0]:\n"
                "        edited = True\n"
                "        path.write_bytes(content + edit_after_read[1])\n"
                "    return content\n"
                "def replace(source, destination, *args, **kwargs):\n"
                "    if pause and pathlib.Path(destination).name == pause[0]:\n"
                "        pathlib.Path(pause[1]).touch()\n"
                "        deadline = time.monotonic() + 15\n"
                "        while not pathlib.Path(pause[2]).exists():\n"
                "            if time.monotonic() > deadline:\n"
                "                raise TimeoutError('Filesystem test rendezvous timed out')\n"
                "            time.sleep(0.02)\n"
                "    if pathlib.Path(destination).name in targets or str(destination) in targets:\n"
                "        raise PermissionError('Injected filesystem replace failure: ' + str(destination))\n"
                "    return original_replace(source, destination, *args, **kwargs)\n"
                "def unlink(path, *args, **kwargs):\n"
                "    if pathlib.Path(path).name in unlink_targets or str(path) in unlink_targets:\n"
                "        raise PermissionError('Injected filesystem unlink failure: ' + str(path))\n"
                "    return original_unlink(path, *args, **kwargs)\n"
                "os.replace = replace\n"
                "os.unlink = unlink\n"
                "pathlib.Path.read_bytes = read\n"
                "entry = sys.argv.pop(1)\n"
                "sys.path.insert(0, str(pathlib.Path(entry).parent))\n"
                "runpy.run_path(entry, run_name='__main__')\n", encoding="utf-8")
            command.insert(1, str(wrapper))
        command += ([action] if action else []) + ["--project", str(self.project), "--user-home", str(self.user_home),
                    "--codex-home", str(self.codex_home), "--bundle", str(self.bundle),
                    "--components", "handoff", "--json"]
        if codex:
            command += ["--codex", str(codex)]
        command += list(map(str, arguments))
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("CODEX_")}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        env.update(environment or {})
        return subprocess.run(command, cwd=self.directory, env=env, input=input,
                              capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_install_project_handoff_without_touching_project_instructions(self):
        self.assertIsNotNone(CODEX, "Native Codex required for installer integration tests")
        instructions = self.project / "AGENTS.md"
        instructions.write_text("# My instructions\nKeep this file.\n", encoding="utf-8")
        result = self.run_setup("install")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        deployed = self.project / ".agents/skills/handoff/SKILL.md"
        self.assertEqual(deployed.read_bytes(), (ROOT / "skills/handoff/SKILL.md").read_bytes())
        self.assertEqual(instructions.read_text(encoding="utf-8"), "# My instructions\nKeep this file.\n")
        self.assertEqual((self.project / "notes.txt").read_text(), "keep my project\n")
        self.assertFalse((self.project / ".feather/handoffs").exists())
        report = json.loads(self.run_setup("check").stdout)
        self.assertEqual(report["components"]["handoff"]["status"], "installed")

    def test_preview_does_not_create_any_installation_files(self):
        before = {p.relative_to(self.directory).as_posix(): p.read_bytes()
                  for p in self.directory.rglob("*") if p.is_file()}
        result = self.run_setup("install", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["dry_run"])
        after = {p.relative_to(self.directory).as_posix(): p.read_bytes()
                 for p in self.directory.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_reinstall_is_a_noop_including_installation_record(self):
        first = self.run_setup("install")
        self.assertEqual(first.returncode, 0, first.stderr)
        before = {p.relative_to(self.project).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.project.rglob("*") if p.is_file()}
        second = self.run_setup("install")
        self.assertEqual(second.returncode, 0, second.stderr)
        after = {p.relative_to(self.project).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(after, before)
        self.assertEqual(json.loads(second.stdout)["changes"], [])

    def test_all_destinations_are_checked_before_any_payload_is_written(self):
        extra = self.bundle / "assets/skills/handoff/zz-references/usage.md"
        extra.parent.mkdir()
        extra.write_text("reference", encoding="utf-8")
        self.write_manifest()
        existing = self.project / ".agents/skills/handoff/zz-references"
        existing.parent.mkdir(parents=True)
        existing.write_text("my unrelated file", encoding="utf-8")
        result = self.run_setup("install")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((existing.parent / "SKILL.md").exists())
        self.assertEqual(existing.read_text(encoding="utf-8"), "my unrelated file")
        self.assertFalse((self.project / ".feather/setup/state.json").exists())

    def test_state_write_failure_rolls_back_deployed_skill(self):
        result = self.run_setup("install", fail_replace=("state.json",))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.project / ".agents/skills/handoff/SKILL.md").exists())
        self.assertFalse((self.project / ".feather/setup/state.json").exists())
        report = json.loads(result.stderr)
        self.assertEqual(report["recovery"], "rolled_back")
        self.assertTrue(Path(report["backup"]).is_dir())
        self.assertEqual((self.project / "notes.txt").read_text(), "keep my project\n")

    def test_failed_rollback_identifies_remaining_files_and_original_backups(self):
        result = self.run_setup("install", fail_replace=("state.json",), fail_unlink=("SKILL.md",))
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stderr)
        self.assertEqual(report["recovery"], "incomplete")
        remaining = self.project / ".agents/skills/handoff/SKILL.md"
        self.assertTrue(remaining.exists())
        self.assertIn(str(remaining), [item["path"] for item in report["remaining"]])
        journal = json.loads((Path(report["backup"]) / "journal.json").read_text())
        self.assertEqual(journal["phase"], "recovery_required")

    def test_missing_codex_stops_without_creating_installation_directories(self):
        result = self.run_setup("install", codex=self.directory / "missing-codex.exe")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Install Codex first", json.loads(result.stderr)["error"])
        self.assertFalse((self.project / ".agents").exists())
        self.assertFalse((self.project / ".feather").exists())

    def test_modified_or_unowned_skill_is_preserved(self):
        target = self.project / ".agents/skills/handoff/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("my existing skill", encoding="utf-8")
        result = self.run_setup("install")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), "my existing skill")
        self.assertFalse((self.project / ".feather/setup/state.json").exists())

    def test_native_codex_discovers_the_deployed_project_handoff(self):
        override = self.project / "AGENTS.override.md"
        override.write_text("Native override probe.\n", encoding="utf-8")
        result = self.run_setup("install", "--entrance", "project")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.codex_home.mkdir(parents=True, exist_ok=True)
        (self.project / ".feather-root").touch()
        (self.codex_home / "config.toml").write_text('project_root_markers = [".feather-root"]\n', encoding="utf-8")
        environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("CODEX_")}
        environment.update(CODEX_HOME=str(self.codex_home), HOME=str(self.user_home), USERPROFILE=str(self.user_home))
        probe = subprocess.run([CODEX, "debug", "prompt-input", "Report loaded inputs only."],
                               cwd=self.project, env=environment, capture_output=True, text=True,
                               encoding="utf-8", timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        messages = json.loads(probe.stdout)
        rendered = render_messages(messages)
        self.assertIn("<!-- feather-setup:handoff:begin -->", rendered)
        self.assertIn("Native override probe.", rendered)
        self.assertEqual(skill_paths(rendered, "handoff"),
                         [(self.project / ".agents/skills/handoff/SKILL.md").resolve()])

    def test_packaged_installer_runs_without_python_on_path(self):
        if not os.environ.get("FEATHER_TEST_INSTALLER"):
            self.skipTest("Run this check against the standalone release")
        result = self.run_setup("install", environment={"PATH": "", "PYTHONHOME": str(self.directory / "no-python")})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.project / ".agents/skills/handoff/SKILL.md").is_file())

    def test_delegation_selection_preserves_model_and_parallel_preferences(self):
        self.add_delegation()
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        original = '# my settings\nmodel = "my-main-model"\nmodel_reasoning_effort = "high"\n[agents]\nmax_threads = 3\n'
        config.write_text(original, encoding="utf-8")
        result = self.run_setup("install", "--components", "delegation")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_text(encoding="utf-8"), original)
        for role in ["scout", "analyst", "mech-executor", "executor", "security-executor"]:
            self.assertEqual((self.project / f".codex/agents/{role}.toml").read_bytes(),
                             (ROOT / f"templates/{role}.toml").read_bytes())
        self.assertEqual((self.project / ".agents/skills/feather-delegation/SKILL.md").read_bytes(),
                         (ROOT / "templates/feather-delegation/SKILL.md").read_bytes())
        self.assertFalse((self.project / ".agents/skills/handoff").exists())
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_all_components_install_as_one_operation(self):
        self.add_delegation()
        result = self.run_setup("install", "--components", "all")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.run_setup("check", "--components", "all").stdout)
        self.assertEqual(set(report["components"]), {"handoff", "delegation"})
        self.assertTrue(all(component["status"] == "installed" for component in report["components"].values()))
        self.assertFalse((self.project / ".codex/config.toml").exists())

    def test_explicitly_disabled_agents_are_reported_without_overwriting_settings(self):
        self.add_delegation()
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text("# intentional\n[agents]\nenabled = false\n", encoding="utf-8")
        result = self.run_setup("install", "--components", "delegation")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agents.enabled", json.loads(result.stderr)["error"])
        self.assertEqual(config.read_text(encoding="utf-8"), "# intentional\n[agents]\nenabled = false\n")
        self.assertFalse((self.project / ".codex/agents").exists())

    def test_native_codex_registers_the_four_installed_project_roles(self):
        self.add_delegation()
        result = self.run_setup("install", "--components", "delegation")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.codex_home.mkdir(parents=True, exist_ok=True)
        (self.project / ".feather-root").touch()
        (self.codex_home / "config.toml").write_text(
            'project_root_markers = [".feather-root"]\n'
            f'[projects.{json.dumps(str(self.project))}]\ntrust_level = "trusted"\n', encoding="utf-8")
        request = capture_tools(CODEX, self.project, self.user_home, self.codex_home)
        registered = registered_tools(request)
        tools = json.dumps(registered, ensure_ascii=False)
        for role in ["scout", "analyst", "mech-executor", "executor", "security-executor"]:
            self.assertTrue(role in tools, f"Native tool registration missing {role}; registered types: {[item.get('name') for item in registered]}")

    def test_role_write_failure_rolls_back_the_other_selected_component(self):
        self.add_delegation()
        result = self.run_setup("install", "--components", "all", fail_replace=("executor.toml",))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["recovery"], "rolled_back")
        self.assertFalse((self.project / ".agents/skills/handoff/SKILL.md").exists())
        self.assertFalse((self.project / ".codex/agents/analyst.toml").exists())
        self.assertFalse((self.project / ".feather/setup/state.json").exists())

    def test_user_scope_uses_skill_home_independently_of_custom_codex_home(self):
        custom_home = self.directory / "custom-codex-home"
        result = self.run_setup("install", "--scope", "user", "--codex-home", custom_home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.user_home / ".agents/skills/handoff/SKILL.md").is_file())
        self.assertTrue((custom_home / "feather-setup/state.json").is_file())
        self.assertFalse((custom_home / "skills/handoff").exists())
        self.assertFalse((self.project / ".agents").exists())
        report = json.loads(self.run_setup("check", "--scope", "user", "--codex-home", custom_home).stdout)
        self.assertEqual(report["components"]["handoff"]["status"], "installed")

    def test_project_install_reuses_existing_user_skill_instead_of_duplicating(self):
        first = self.run_setup("install", "--scope", "user")
        self.assertEqual(first.returncode, 0, first.stderr)
        before = {p.relative_to(self.user_home).as_posix(): p.read_bytes()
                  for p in self.user_home.rglob("*") if p.is_file()}
        result = self.run_setup("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        component = json.loads(result.stdout)["components"]["handoff"]
        self.assertEqual(component["status"], "reused")
        self.assertEqual(component["scope"], "user")
        self.assertFalse((self.project / ".agents").exists())
        self.assertFalse((self.project / ".feather").exists())
        self.assertEqual({p.relative_to(self.user_home).as_posix(): p.read_bytes()
                          for p in self.user_home.rglob("*") if p.is_file()}, before)

    def test_nested_project_reuses_a_skill_at_the_repository_root(self):
        (self.project / ".git").mkdir()
        first = self.run_setup("install")
        self.assertEqual(first.returncode, 0, first.stderr)
        nested = self.project / "packages/service"
        nested.mkdir(parents=True)
        result = self.run_setup("install", "--project", nested)
        self.assertEqual(result.returncode, 0, result.stderr)
        component = json.loads(result.stdout)["components"]["handoff"]
        self.assertEqual(component["status"], "reused")
        self.assertEqual(component["project"], str(self.project))
        self.assertFalse((nested / ".agents").exists())

    def test_existing_record_cannot_be_retargeted_to_another_user_home(self):
        self.assertEqual(self.run_setup("install", "--scope", "user").returncode, 0)
        other_home = self.directory / "another-user"
        result = self.run_setup("install", "--scope", "user", "--user-home", other_home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("environment", json.loads(result.stderr)["error"])
        self.assertFalse(other_home.exists())

    def test_role_identity_collision_is_detected_even_with_another_filename(self):
        self.add_delegation()
        other = self.codex_home / "agents/my-custom-role.toml"
        other.parent.mkdir(parents=True)
        other.write_text('name = "scout"\ndescription = "my scout"\ndeveloper_instructions = "my rules"\n', encoding="utf-8")
        result = self.run_setup("install", "--components", "delegation")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scout", json.loads(result.stderr)["error"])
        self.assertFalse((self.project / ".codex/agents").exists())

    def test_entrance_uses_override_preserves_outside_bytes_and_repeats_cleanly(self):
        self.add_delegation()
        ordinary = self.project / "AGENTS.md"
        ordinary.write_bytes(b"ordinary instructions\r\n")
        override = self.project / "AGENTS.override.md"
        original = b"\xef\xbb\xbf# My override\r\nKeep exactly these bytes."
        override.write_bytes(original)
        result = self.run_setup("install", "--components", "all", "--entrance", "project")
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = override.read_bytes()
        self.assertTrue(installed.startswith(original))
        self.assertIn(b"handoff", installed)
        self.assertIn(b"`feather-delegation` skill", installed)
        self.assertEqual(ordinary.read_bytes(), b"ordinary instructions\r\n")
        result = self.run_setup("install", "--components", "all", "--entrance", "project")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(override.read_bytes(), installed)
        self.assertEqual(json.loads(result.stdout)["changes"], [])
        self.assertEqual(json.loads(result.stdout)["entrances"]["handoff"]["path"], str(override))

    def test_user_entrance_with_project_components_is_conditional_and_native_loaded(self):
        self.add_delegation()
        result = self.run_setup("install", "--components", "all", "--entrance", "user")
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = self.codex_home / "AGENTS.md"
        self.assertIn("only when", entry.read_text())
        self.assertFalse((self.user_home / ".agents/skills/handoff").exists())
        (self.project / ".feather-root").touch()
        (self.codex_home / "config.toml").write_text(
            'project_root_markers = [".feather-root"]\n'
            f'[projects.{json.dumps(str(self.project))}]\ntrust_level = "trusted"\n', encoding="utf-8")
        request = capture_tools(CODEX, self.project, self.user_home, self.codex_home)
        rendered = render_messages(request.get("input", []))
        self.assertIn("<!-- feather-setup:handoff:begin -->", rendered)
        self.assertIn("<!-- feather-setup:delegation:begin -->", rendered)
        self.assertIn("only when", rendered)
        other = self.directory / "other-project"
        other.mkdir()
        request = capture_tools(CODEX, other, self.user_home, self.codex_home)
        rendered = render_messages(request.get("input", []))
        self.assertIn("only when", rendered)
        self.assertEqual(skill_paths(rendered, "handoff"), [])

    def test_entrance_conflict_and_write_failure_leave_no_partial_install(self):
        target = self.project / "AGENTS.md"
        target.write_text("<!-- feather-setup:handoff:begin -->\nmy rules\n", encoding="utf-8")
        result = self.run_setup("install", "--entrance", "project")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.project / ".agents").exists())
        target.write_bytes(b"my rules\r\n")
        result = self.run_setup("install", "--entrance", "project", fail_replace=("AGENTS.md",))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["recovery"], "rolled_back")
        self.assertEqual(target.read_bytes(), b"my rules\r\n")
        self.assertFalse((self.project / ".agents/skills/handoff/SKILL.md").exists())

    def test_modified_managed_entrance_is_preserved(self):
        self.assertEqual(self.run_setup("install", "--entrance", "project").returncode, 0)
        target = self.project / "AGENTS.md"
        modified = target.read_bytes().replace(b"When the user", b"Only when the user")
        target.write_bytes(modified)
        result = self.run_setup("install", "--entrance", "project")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), modified)

    def test_entrance_and_component_scope_matrix(self):
        self.add_delegation()
        original_project, original_user, original_codex = self.project, self.user_home, self.codex_home
        for scope in ["project", "user"]:
            for entrance in ["project", "user"]:
                for component in ["handoff", "delegation", "all"]:
                    with self.subTest(scope=scope, entrance=entrance, component=component):
                        name = f"{scope}-{entrance}-{component}"
                        self.project = self.directory / name / "project"
                        self.project.mkdir(parents=True)
                        self.user_home = self.directory / name / "user"
                        self.codex_home = self.user_home / ".codex"
                        result = self.run_setup("install", "--scope", scope, "--entrance", entrance,
                                                "--components", component)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        root = self.project if entrance == "project" else self.codex_home
                        content = (root / "AGENTS.md").read_text()
                        for selected in (["handoff", "delegation"] if component == "all" else [component]):
                            self.assertIn(f"<!-- feather-setup:{selected}:begin -->", content)
        self.project, self.user_home, self.codex_home = original_project, original_user, original_codex

    def test_update_preserves_unselected_components_and_updates_entry_from_bundle(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--components", "all", "--entrance", "user").returncode, 0)
        skill = self.project / ".agents/skills/handoff/SKILL.md"
        original_skill = skill.read_bytes()
        role = self.bundle / "assets/templates/analyst.toml"
        role.write_bytes(role.read_bytes() + b"\n# new release\n")
        guidance = self.bundle / "assets/templates/entrances/delegation.md"
        guidance.write_bytes(guidance.read_bytes() + b"\nNew release guidance.\n")
        self.write_manifest("0.2.0")
        preview = self.run_setup("update", "--components", "delegation", "--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertNotIn(b"New release guidance", (self.codex_home / "AGENTS.md").read_bytes())
        result = self.run_setup("update", "--components", "delegation")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(skill.read_bytes(), original_skill)
        self.assertEqual((self.project / ".codex/agents/analyst.toml").read_bytes(), role.read_bytes())
        self.assertIn(b"New release guidance", (self.codex_home / "AGENTS.md").read_bytes())
        record = json.loads((self.project / ".feather/setup/state.json").read_text())
        self.assertEqual(record["components"]["delegation"]["version"], "0.2.0")
        self.assertEqual(record["components"]["handoff"]["version"], "0.1.0")
        repeat = self.run_setup("update", "--components", "delegation")
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(json.loads(repeat.stdout)["changes"], [])

    def test_update_conflicts_preserve_bytes_until_explicit_replace_with_backup(self):
        self.assertEqual(self.run_setup("install", "--entrance", "project").returncode, 0)
        skill = self.project / ".agents/skills/handoff/SKILL.md"
        customized = skill.read_bytes() + b"\nMy custom skill rule.\n"
        skill.write_bytes(customized)
        source = self.bundle / "assets/skills/handoff/SKILL.md"
        source.write_bytes(source.read_bytes() + b"\nNew release.\n")
        self.write_manifest("0.2.0")
        result = self.run_setup("update")
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stderr)
        self.assertIn("My custom skill rule", json.dumps(report["conflicts"]))
        self.assertEqual(skill.read_bytes(), customized)
        keep = self.run_setup("update", "--on-conflict", "keep")
        self.assertNotEqual(keep.returncode, 0)
        self.assertEqual(skill.read_bytes(), customized)
        result = self.run_setup("update", "--on-conflict", "replace")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(skill.read_bytes(), source.read_bytes())
        backup = Path(json.loads(result.stdout)["backup"])
        self.assertIn(customized, [p.read_bytes() for p in backup.glob("*.bin")])

    def test_update_modified_entrance_replaces_only_its_bounded_block(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--components", "all", "--entrance", "user").returncode, 0)
        target = self.codex_home / "AGENTS.md"
        target.write_bytes(b"outside prefix\r\n" + target.read_bytes().replace(b"When the user", b"My own rule: when the user") + b"outside suffix")
        modified = target.read_bytes()
        result = self.run_setup("update")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), modified)
        result = self.run_setup("update", "--on-conflict", "replace")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.read_bytes().startswith(b"outside prefix\r\n"))
        self.assertTrue(target.read_bytes().endswith(b"outside suffix"))
        self.assertNotIn(b"My own rule", target.read_bytes())
        self.assertIn(b"feather-setup:delegation:begin", target.read_bytes())

    def test_update_deletes_only_obsolete_owned_payload_and_rolls_back_all_changes(self):
        extra = self.bundle / "assets/skills/handoff/obsolete.md"
        extra.write_bytes(b"old auxiliary file")
        self.write_manifest()
        self.assertEqual(self.run_setup("install", "--entrance", "project").returncode, 0)
        extra.unlink()
        source = self.bundle / "assets/skills/handoff/SKILL.md"
        source.write_bytes(source.read_bytes() + b"\nNew release.\n")
        self.write_manifest("0.2.0")
        before = {p.relative_to(self.project): p.read_bytes() for p in self.project.rglob("*")
                  if p.is_file() and "backups" not in p.parts}
        result = self.run_setup("update", fail_replace=("state.json",))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["recovery"], "rolled_back")
        after = {p.relative_to(self.project): p.read_bytes() for p in self.project.rglob("*")
                 if p.is_file() and "backups" not in p.parts}
        self.assertEqual(after, before)
        result = self.run_setup("update")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.project / ".agents/skills/handoff/obsolete.md").exists())

    def test_native_codex_discovers_updated_user_roles_and_project_entrance(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--scope", "user", "--components", "delegation",
                                        "--entrance", "project").returncode, 0)
        role = self.bundle / "assets/templates/analyst.toml"
        text = role.read_text(encoding="utf-8")
        text = text.replace('description = "', 'description = "FeatherUpdateProbe ' , 1)
        role.write_text(text, encoding="utf-8")
        guidance = self.bundle / "assets/templates/entrances/delegation.md"
        guidance.write_bytes(guidance.read_bytes() + b"\nFeatherUpdateEntryProbe.\n")
        self.write_manifest("0.2.0")
        result = self.run_setup("update", "--scope", "user", "--components", "delegation")
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.project / ".feather-root").touch()
        (self.codex_home / "config.toml").write_text('project_root_markers = [".feather-root"]\n', encoding="utf-8")
        request = capture_tools(CODEX, self.project, self.user_home, self.codex_home)
        self.assertIn("FeatherUpdateProbe", json.dumps(request))
        self.assertIn("FeatherUpdateEntryProbe", json.dumps(request))

    def test_remove_only_selected_owned_files_and_entry_preserves_handoffs_and_other_data(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--components", "all", "--entrance", "user").returncode, 0)
        keep = {self.project / ".feather/handoffs/current.md": b"current work",
                self.project / ".feather/handoffs/history/old.md": b"history",
                self.project / ".agents/skills/handoff/my-notes.txt": b"my unrelated note"}
        for path, content in keep.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        entry = self.codex_home / "AGENTS.md"
        entry.write_bytes(b"my outside instructions\r\n" + entry.read_bytes())
        preview = self.run_setup("remove", "--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        skill = self.project / ".agents/skills/handoff/SKILL.md"
        self.assertTrue(skill.exists())
        result = self.run_setup("remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(skill.exists())
        self.assertTrue((self.project / ".codex/agents/analyst.toml").exists())
        self.assertNotIn(b"feather-setup:handoff:begin", entry.read_bytes())
        self.assertIn(b"feather-setup:delegation:begin", entry.read_bytes())
        for path, content in keep.items():
            self.assertEqual(path.read_bytes(), content)
        result = self.run_setup("remove", "--components", "all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(entry.read_bytes(), b"my outside instructions\r\n")
        skill.write_bytes(b"later unowned skill")
        repeat = self.run_setup("remove")
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(skill.read_bytes(), b"later unowned skill")

    def test_remove_conflicts_require_explicit_backup_and_failed_removal_rolls_back(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--components", "all", "--entrance", "project").returncode, 0)
        skill = self.project / ".agents/skills/handoff/SKILL.md"
        changed = skill.read_bytes() + b"\nuser customization\n"
        skill.write_bytes(changed)
        result = self.run_setup("remove", "--components", "all")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(skill.read_bytes(), changed)
        result = self.run_setup("remove", "--components", "all", "--on-conflict", "replace",
                                fail_unlink=("executor.toml",))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["recovery"], "rolled_back")
        self.assertEqual(skill.read_bytes(), changed)
        self.assertIn(b"feather-setup:handoff:begin", (self.project / "AGENTS.md").read_bytes())
        result = self.run_setup("remove", "--components", "all", "--on-conflict", "replace")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(skill.exists())
        self.assertFalse((self.project / "AGENTS.md").exists())
        backup = Path(json.loads(result.stdout)["backup"])
        self.assertIn(changed, [p.read_bytes() for p in backup.glob("*.bin")])

    def test_shared_user_entrance_survives_removal_of_one_project(self):
        self.assertEqual(self.run_setup("install", "--entrance", "user").returncode, 0)
        original_project = self.project
        self.project = self.directory / "second project"
        self.project.mkdir()
        self.assertEqual(self.run_setup("install", "--entrance", "user").returncode, 0)
        entry = self.codex_home / "AGENTS.md"
        self.assertEqual(entry.read_bytes().count(b"feather-setup:handoff:begin"), 1)
        result = self.run_setup("remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"feather-setup:handoff:begin", entry.read_bytes())
        self.project = original_project
        result = self.run_setup("remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(entry.exists())

    def test_remove_user_roles_preserves_user_preferences_and_project_data(self):
        self.add_delegation()
        original_notes = (self.project / "notes.txt").read_bytes()
        self.assertEqual(self.run_setup("install", "--scope", "user", "--components", "all",
                                        "--entrance", "project").returncode, 0)
        config = self.codex_home / "config.toml"
        config.write_bytes(b'# keep\nmodel = "my-choice"\n')
        role = self.codex_home / "agents/analyst.toml"
        customized = role.read_bytes() + b"\n# customized\n"
        role.write_bytes(customized)
        self.assertNotEqual(self.run_setup("remove", "--scope", "user", "--components", "all").returncode, 0)
        result = self.run_setup("remove", "--scope", "user", "--components", "all", "--on-conflict", "replace")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(role.exists())
        self.assertEqual(config.read_bytes(), b'# keep\nmodel = "my-choice"\n')
        backup = Path(json.loads(result.stdout)["backup"])
        self.assertIn(customized, [p.read_bytes() for p in backup.glob("*.bin")])
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertEqual((self.project / "notes.txt").read_bytes(), original_notes)

    def test_migration_moves_owned_components_both_directions_without_moving_entry_by_default(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--components", "all", "--entrance", "project").returncode, 0)
        entry = (self.project / "AGENTS.md").read_bytes()
        skill = (self.project / ".agents/skills/handoff/SKILL.md").read_bytes()
        result = self.run_setup("migrate", "--components", "all", "--from", "project", "--to", "user", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.user_home / ".agents/skills/handoff/SKILL.md").exists())
        result = self.run_setup("migrate", "--components", "all", "--from", "project", "--to", "user")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.user_home / ".agents/skills/handoff/SKILL.md").read_bytes(), skill)
        self.assertFalse((self.project / ".agents/skills/handoff/SKILL.md").exists())
        self.assertEqual((self.project / "AGENTS.md").read_bytes(), entry)
        result = self.run_setup("migrate", "--components", "all", "--from", "user", "--to", "project",
                                "--entrance", "user")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("other projects", json.loads(result.stdout)["impact"])
        self.assertEqual((self.project / ".agents/skills/handoff/SKILL.md").read_bytes(), skill)
        self.assertFalse((self.user_home / ".agents/skills/handoff/SKILL.md").exists())
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertIn(b"feather-setup:handoff:begin", (self.codex_home / "AGENTS.md").read_bytes())

    def test_migration_conflicting_source_or_destination_never_changes_either_scope(self):
        self.assertEqual(self.run_setup("install").returncode, 0)
        skill = self.project / ".agents/skills/handoff/SKILL.md"
        original = skill.read_bytes()
        skill.write_bytes(original + b"\ncustom source\n")
        result = self.run_setup("migrate", "--from", "project", "--to", "user")
        self.assertNotEqual(result.returncode, 0)
        target = self.user_home / ".agents/skills/handoff/SKILL.md"
        self.assertFalse(target.exists())
        skill.write_bytes(original)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"someone else's skill")
        result = self.run_setup("migrate", "--from", "project", "--to", "user")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(skill.read_bytes(), original)
        self.assertEqual(target.read_bytes(), b"someone else's skill")

    def test_migration_failure_restores_both_scopes_and_entrances(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--components", "all", "--entrance", "project").returncode, 0)
        data = self.project / ".feather/handoffs/progress.md"
        data.parent.mkdir(parents=True)
        data.write_bytes(b"keep progress")
        before = {p.relative_to(self.directory): p.read_bytes() for p in self.directory.rglob("*")
                  if p.is_file() and "backups" not in p.parts}
        source_analyst = str(self.project / ".codex/agents/analyst.toml")
        for fail_replace, fail_unlink in [(('analyst.toml',), ()), ((), (source_analyst,)), (('state.json',), ())]:
            with self.subTest(replace=fail_replace, unlink=fail_unlink):
                result = self.run_setup("migrate", "--components", "all", "--from", "project", "--to", "user",
                                        "--entrance", "user", fail_replace=fail_replace, fail_unlink=fail_unlink)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(json.loads(result.stderr)["recovery"], "rolled_back")
                after = {p.relative_to(self.directory): p.read_bytes() for p in self.directory.rglob("*")
                         if p.is_file() and "backups" not in p.parts and p.name != "filesystem_fault.py"}
                self.assertEqual(after, before)

    def test_migration_keeps_source_version_when_a_newer_bundle_is_used(self):
        self.assertEqual(self.run_setup("install").returncode, 0)
        skill = self.project / ".agents/skills/handoff/SKILL.md"
        original = skill.read_bytes()
        asset = self.bundle / "assets/skills/handoff/SKILL.md"
        asset.write_bytes(original + b"\nThis release is newer.\n")
        self.write_manifest("0.2.0")
        result = self.run_setup("migrate", "--from", "project", "--to", "user")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.user_home / ".agents/skills/handoff/SKILL.md").read_bytes(), original)
        record = json.loads((self.codex_home / "feather-setup/state.json").read_text())
        self.assertEqual(record["components"]["handoff"]["version"], "0.1.0")

    def test_migration_reports_incomplete_recovery_when_destination_cleanup_also_fails(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--components", "all").returncode, 0)
        result = self.run_setup("migrate", "--components", "all", "--from", "project", "--to", "user",
                                fail_unlink=("analyst.toml",))
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stderr)
        self.assertEqual(report["recovery"], "incomplete")
        self.assertTrue(report["remaining"])
        self.assertTrue(Path(report["backup"]).exists())
        self.assertTrue((self.project / ".codex/agents/analyst.toml").exists())

    def test_native_codex_discovers_migrated_roles_in_each_direction(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--components", "delegation", "--entrance", "user").returncode, 0)
        (self.project / ".feather-root").touch()
        (self.codex_home / "config.toml").write_text(
            'project_root_markers = [".feather-root"]\n'
            f'[projects.{json.dumps(str(self.project))}]\ntrust_level = "trusted"\n', encoding="utf-8")
        for source, destination in [("project", "user"), ("user", "project")]:
            result = self.run_setup("migrate", "--components", "delegation", "--from", source, "--to", destination)
            self.assertEqual(result.returncode, 0, result.stderr)
            request = capture_tools(CODEX, self.project, self.user_home, self.codex_home)
            registered = registered_tools(request)
            for role in ["scout", "analyst", "mech-executor", "executor", "security-executor"]:
                self.assertIn(role, json.dumps(registered))
            self.assertIn("feather-setup:delegation:begin", json.dumps(request))

    def test_interactive_install_and_cancel_match_explicit_options(self):
        self.add_delegation()
        # Paths and component choice are supplied; the guide asks only for operation, scope, entrance and apply.
        result = self.run_setup(None, "--components", "all", input="install\nproject\nuser\nno\n")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertLess(result.stderr.index('"action": "check"'), result.stderr.index("Operation"))
        self.assertIn('"scope": "project"', result.stderr[:result.stderr.index("Operation")])
        self.assertIn('"scope": "user"', result.stderr[:result.stderr.index("Operation")])
        self.assertFalse((self.project / ".agents").exists())
        self.assertFalse((self.codex_home / "AGENTS.md").exists())
        result = self.run_setup(None, "--components", "all", input="install\nproject\nuser\nyes\n")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue((self.project / ".agents/skills/handoff/SKILL.md").exists())
        entry = (self.codex_home / "AGENTS.md").read_bytes()
        result = self.run_setup("install", "--components", "all", "--scope", "project", "--entrance", "user")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["changes"], [])
        self.assertEqual((self.codex_home / "AGENTS.md").read_bytes(), entry)

    def test_interactive_preflight_checks_healthy_user_after_corrupt_project(self):
        state = self.project / ".feather/setup/state.json"
        state.parent.mkdir(parents=True)
        corrupted = b"{invalid project installation record"
        state.write_bytes(corrupted)

        result = self.run_setup(None, input="check\nuser\n")
        direct = self.run_setup("check", "--scope", "user")
        self.assertEqual(result.returncode, direct.returncode, result.stderr + result.stdout)
        preflight = result.stderr[:result.stderr.index("Operation")]
        self.assertLess(preflight.index('"scope": "project"'), preflight.index('"scope": "user"'))
        self.assertIn('"status": "error"', preflight)
        self.assertIn('"status": "attention-required"', preflight[preflight.index('"scope": "user"'):])
        self.assertEqual(json.loads(result.stdout)["components"], json.loads(direct.stdout)["components"])
        self.assertEqual(json.loads(result.stdout)["scope"], "user")
        self.assertEqual(state.read_bytes(), corrupted)

    def test_interactive_install_ignores_corrupt_unrelated_user_state(self):
        self.add_delegation()
        state = self.codex_home / "feather-setup/state.json"
        state.parent.mkdir(parents=True)
        corrupted = b"{invalid user installation record"
        state.write_bytes(corrupted)

        result = self.run_setup(None, "--components", "delegation", input="install\nproject\nnone\nyes\n")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('"scope": "user"', result.stderr[:result.stderr.index("Operation")])
        self.assertIn('"status": "error"', result.stderr[:result.stderr.index("Operation")])
        self.assertEqual(json.loads(result.stdout)["scope"], "project")
        self.assertTrue((self.project / ".codex/agents/executor.toml").is_file())
        self.assertEqual(state.read_bytes(), corrupted)

    def test_interactive_selected_corrupt_state_fails_without_writes(self):
        state = self.project / ".feather/setup/state.json"
        state.parent.mkdir(parents=True)
        corrupted = b"{invalid project installation record"
        state.write_bytes(corrupted)

        result = self.run_setup(None, input="install\nproject\nnone\nyes\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"status": "error"', result.stderr[:result.stderr.index("Operation")])
        self.assertIn('"error":', result.stderr[result.stderr.index("Operation"):])
        self.assertEqual(state.read_bytes(), corrupted)
        self.assertFalse((self.project / ".agents/skills/handoff/SKILL.md").exists())

    def test_interactive_invalid_project_or_bundle_stops_before_choices(self):
        wrong_project = self.directory / "project-file"
        wrong_project.write_text("not a directory", encoding="utf-8")
        for options in [("--project", wrong_project), ("--bundle", self.directory / "missing-bundle")]:
            with self.subTest(options=options):
                result = self.run_setup(None, *options, input="install\nproject\nnone\nyes\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Operation (", result.stderr)
                self.assertFalse((self.project / ".agents/skills/handoff/SKILL.md").exists())

    def test_interactive_update_conflict_keep_replace_and_remove_use_the_same_engine(self):
        self.assertEqual(self.run_setup("install", "--entrance", "project").returncode, 0)
        target = self.project / ".agents/skills/handoff/SKILL.md"
        modified = target.read_bytes() + b"\nlocal edit\n"
        target.write_bytes(modified)
        result = self.run_setup(None, input="update\nproject\nkeep\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "preserved")
        self.assertEqual(target.read_bytes(), modified)
        result = self.run_setup(None, input="update\nproject\nreplace\nyes\n")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotEqual(target.read_bytes(), modified)
        result = self.run_setup(None, input="check\nproject\n")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["components"]["handoff"]["status"], "installed")
        result = self.run_setup(None, input="remove\nproject\nyes\n")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(target.exists())
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_interactive_existing_scope_can_reuse_or_explicitly_migrate(self):
        self.assertEqual(self.run_setup("install", "--scope", "user").returncode, 0)
        target = self.project / ".agents/skills/handoff/SKILL.md"
        result = self.run_setup(None, input="install\nproject\nnone\nreuse\nyes\n")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(target.exists())
        self.assertEqual(json.loads(result.stdout)["components"]["handoff"]["status"], "reused")
        result = self.run_setup(None, input="install\nproject\nnone\nmigrate\nyes\n")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(target.exists())
        result = self.run_setup(None, input="migrate\nproject\nuser\nnone\nyes\n")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(target.exists())

    def test_check_reports_runtime_settings_without_changing_configurations(self):
        self.add_delegation()
        installed = self.run_setup("install", "--components", "all", "--scope", "user")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        config = self.project / ".codex/config.toml"
        config.parent.mkdir(parents=True)
        config.write_text('[agents]\nenabled = false\n', encoding="utf-8")
        before = {path: path.read_bytes() for root in [self.project, self.user_home]
                  for path in root.rglob("*") if path.is_file()}
        checked = self.run_setup("check", "--components", "all", "--scope", "user")
        self.assertEqual(checked.returncode, 1, checked.stderr)
        report = json.loads(checked.stdout)
        self.assertEqual(report["components"]["delegation"]["status"], "installed")
        self.assertEqual(report["runtime"]["agents"]["status"], "disabled")
        self.assertEqual(Path(report["runtime"]["agents"]["source"]), config)
        self.assertEqual(report["runtime"]["session"]["status"], "unconfirmed")
        self.assertEqual(before, {path: path.read_bytes() for root in [self.project, self.user_home]
                                  for path in root.rglob("*") if path.is_file()})
        # Checking from the project also diagnoses the reused user installation.
        reused = json.loads(self.run_setup("check", "--components", "all").stdout)
        self.assertEqual(reused["components"]["delegation"]["status"], "reused")
        self.assertEqual(reused["runtime"]["agents"]["status"], "disabled")
        (self.codex_home / "config.toml").write_text('[agents]\nenabled = false\n', encoding="utf-8")
        config.write_text('[agents]\nenabled = true\n', encoding="utf-8")
        checked = self.run_setup("check", "--components", "all")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertTrue(json.loads(checked.stdout)["runtime"]["agents"]["enabled"])
        config.write_text('[agents]\nenabled = "true"\n', encoding="utf-8")
        checked = self.run_setup("check", "--components", "all")
        self.assertEqual(checked.returncode, 1)
        self.assertEqual(json.loads(checked.stdout)["runtime"]["agents"]["status"], "invalid")

    def test_check_keeps_file_evidence_when_codex_is_unavailable(self):
        self.assertEqual(self.run_setup("install").returncode, 0)
        checked = self.run_setup("check", codex=self.directory / "missing-codex.exe")
        self.assertEqual(checked.returncode, 1, checked.stderr)
        report = json.loads(checked.stdout)
        self.assertEqual(report["components"]["handoff"]["status"], "installed")
        self.assertEqual(report["runtime"]["codex"]["status"], "unavailable")
        self.assertNotIn("agents", report["runtime"])

    def test_check_diagnoses_locked_reused_roles_and_identity_collisions(self):
        self.add_delegation()
        self.assertEqual(self.run_setup("install", "--components", "all", "--scope", "user").returncode, 0)
        role = self.codex_home / "agents/scout.toml"
        original = role.read_bytes()
        role.write_bytes(b'model = "custom-model"\n' + original)
        checked = self.run_setup("check", "--components", "all")
        self.assertEqual(checked.returncode, 1, checked.stderr)
        report = json.loads(checked.stdout)
        self.assertEqual(report["components"]["delegation"]["status"], "reused")
        self.assertEqual(report["runtime"]["roles"]["status"], "conflict")
        self.assertIn("locks dispatch settings", " ".join(report["runtime"]["roles"]["issues"]))
        role.write_bytes(original)
        (role.parent / "duplicate.toml").write_bytes(original)
        checked = self.run_setup("check", "--components", "all")
        self.assertEqual(checked.returncode, 1, checked.stderr)
        report = json.loads(checked.stdout)
        self.assertEqual(report["components"]["delegation"]["status"], "conflict")
        self.assertIn("duplicate.toml", report["components"]["delegation"]["message"])
        self.assertEqual(report["components"]["handoff"]["status"], "reused")

    def test_check_distinguishes_modified_missing_and_unowned_files_without_writes(self):
        self.assertEqual(self.run_setup("install", "--entrance", "user").returncode, 0)
        target = self.project / ".agents/skills/handoff/SKILL.md"
        target.write_bytes(target.read_bytes() + b"\nmodified\n")
        before = {p.relative_to(self.directory): p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        result = self.run_setup("check")
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["components"]["handoff"]["status"], "conflict")
        self.assertEqual(report["entrances"]["handoff"]["path"], str(self.codex_home / "AGENTS.md"))
        self.assertEqual({p.relative_to(self.directory): p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}, before)
        target.unlink()
        report = json.loads(self.run_setup("check").stdout)
        self.assertEqual(report["components"]["handoff"]["status"], "missing")

    def test_overlapping_installers_cannot_commit_competing_ownership_records(self):
        if os.environ.get("FEATHER_TEST_INSTALLER"):
            self.skipTest("Source CLI filesystem scheduling adapter")
        ready, release = self.directory / "ready", self.directory / "release"
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.run_setup, "install", pause_replace=("SKILL.md", str(ready), str(release)))
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), "First installer did not reach the filesystem rendezvous")
                second = self.run_setup("install")
                self.assertNotEqual(second.returncode, 0)
                self.assertIn("overlapping", json.loads(second.stderr)["error"])
            finally:
                release.touch()
            result = first.result(timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_setup("check").returncode, 0)

    def test_interactive_replacement_does_not_overwrite_edits_made_after_preview(self):
        self.assertEqual(self.run_setup("install").returncode, 0)
        target = self.project / ".agents/skills/handoff/SKILL.md"
        target.write_bytes(target.read_bytes() + b"\nfirst local edit\n")
        executable = os.environ.get("FEATHER_TEST_INSTALLER")
        command = [executable] if executable else [sys.executable, str(ROOT / "scripts/feather_setup.py")]
        command += ["update", "--interactive", "--project", str(self.project), "--user-home", str(self.user_home),
                    "--codex-home", str(self.codex_home), "--bundle", str(self.bundle), "--codex", str(CODEX),
                    "--scope", "project", "--components", "handoff", "--on-conflict", "replace", "--json"]
        process = subprocess.Popen(command, cwd=self.directory, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8")

        def wait_for_confirmation():
            observed = ""
            while "Apply these changes" not in observed:
                char = process.stderr.read(1)
                if not char:
                    raise AssertionError("Installer exited before showing preview: " + observed)
                observed += char

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                ready = pool.submit(wait_for_confirmation)
                try:
                    ready.result(timeout=15)
                    second_edit = target.read_bytes() + b"\nedit made while reviewing\n"
                    target.write_bytes(second_edit)
                    stdout, stderr = process.communicate("yes\n", timeout=20)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
            self.assertNotEqual(process.returncode, 0, stdout)
            self.assertIn("changed after preview", stderr)
            self.assertEqual(target.read_bytes(), second_edit)
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()

    def test_invalid_bundle_never_creates_a_partial_install(self):
        for kind in ["checksum", "incomplete", "traversal", "case-alias"]:
            with self.subTest(kind=kind):
                self.write_manifest()
                path = self.bundle / "bundle.json"
                manifest = json.loads(path.read_text())
                source = "assets/skills/handoff/SKILL.md"
                if kind == "checksum":
                    manifest["files"][source] = "0" * 64
                elif kind == "incomplete":
                    manifest["components"]["handoff"]["files"] = {}
                elif kind == "traversal":
                    manifest["components"]["handoff"]["files"][source] = "../escaped.md"
                else:
                    alias = "assets/skills/handoff/alias.md"
                    (self.bundle / alias).write_bytes((self.bundle / source).read_bytes())
                    manifest["files"][alias] = manifest["files"][source]
                    manifest["components"]["handoff"]["files"][alias] = ".agents/skills/handoff/skill.md"
                path.write_text(json.dumps(manifest))
                result = self.run_setup("install")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.project / ".agents").exists())
                self.assertFalse((self.project / ".feather/setup/state.json").exists())

    def test_recreated_empty_user_instructions_are_preserved_on_later_removal(self):
        self.assertEqual(self.run_setup("install", "--entrance", "project").returncode, 0)
        self.assertEqual(self.run_setup("remove").returncode, 0)
        target = self.project / "AGENTS.md"
        target.write_bytes(b"")
        self.assertEqual(self.run_setup("install", "--entrance", "project").returncode, 0)
        self.assertEqual(self.run_setup("remove").returncode, 0)
        self.assertEqual(target.read_bytes(), b"")

    def test_ancestor_project_settings_are_checked_before_nested_role_installation(self):
        self.add_delegation()
        (self.project / ".git").mkdir()
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        config.write_bytes(b"[agents]\nenabled = false\n")
        nested = self.project / "packages/service"
        nested.mkdir(parents=True)
        result = self.run_setup("install", "--project", nested, "--components", "delegation")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agents.enabled", result.stderr)
        self.assertFalse((nested / ".codex").exists())

    def test_check_reports_a_later_override_shadowing_the_managed_entry(self):
        self.assertEqual(self.run_setup("install", "--entrance", "project").returncode, 0)
        override = self.project / "AGENTS.override.md"
        override.write_bytes(b"new higher-priority instructions")
        result = self.run_setup("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["entrances"]["handoff"]["status"], "shadowed")
        result = self.run_setup("update")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(override.read_bytes(), b"new higher-priority instructions")

    def test_launch_without_arguments_guides_every_required_choice(self):
        self.add_delegation()
        executable = os.environ.get("FEATHER_TEST_INSTALLER")
        command = [executable] if executable else [sys.executable, str(ROOT / "scripts/feather_setup.py")]
        environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("CODEX_")}
        environment.update(HOME=str(self.user_home), USERPROFILE=str(self.user_home), PYTHONUTF8="1",
                           PATH=str(Path(CODEX).parent) + os.pathsep + os.environ.get("PATH", ""))
        result = subprocess.run(command, cwd=self.bundle, env=environment,
                                input=f"{self.project}\ninstall\nall\nproject\nnone\nyes\n",
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Feather: install", result.stdout)
        self.assertTrue((self.project / ".codex/agents/analyst.toml").exists())
        self.assertTrue((self.project / ".agents/skills/handoff/SKILL.md").exists())
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_editor_save_during_entrance_planning_is_preserved(self):
        entry = self.project / "AGENTS.md"
        entry.write_bytes(b"original user instructions\n")
        concurrent = b"editor added these outside instructions\n"
        result = self.run_setup("install", "--entrance", "project", edit_after_read=(str(entry), concurrent))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(entry.read_bytes(), b"original user instructions\n" + concurrent)
        self.assertFalse((self.project / ".agents/skills/handoff/SKILL.md").exists())

    def test_editor_save_after_component_validation_is_not_force_replaced(self):
        self.assertEqual(self.run_setup("install").returncode, 0)
        skill = self.project / ".agents/skills/handoff/SKILL.md"
        original = skill.read_bytes()
        asset = self.bundle / "assets/skills/handoff/SKILL.md"
        asset.write_bytes(original + b"\nnew release\n")
        self.write_manifest("0.2.0")
        concurrent = b"\neditor added this local rule\n"
        result = self.run_setup("update", "--on-conflict", "replace", edit_after_read=(str(skill), concurrent))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(skill.read_bytes(), original + concurrent)

    def test_same_skill_name_in_another_directory_is_not_duplicated(self):
        alias = self.project / ".agents/skills/group/renamed-handoff/SKILL.md"
        alias.parent.mkdir(parents=True)
        for name in ["handoff", '"feather\\u002dhandoff"', ">-\n  handoff"]:
            with self.subTest(name=name):
                content = f"---\nname: {name}\ndescription: Existing handoff skill\n---\nMy own skill.\n".encode()
                alias.write_bytes(content)
                result = self.run_setup("install")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(alias.read_bytes(), content)
                self.assertFalse((self.project / ".agents/skills/handoff/SKILL.md").exists())
        self.codex_home.mkdir(parents=True)
        (self.project / ".feather-root").touch()
        (self.codex_home / "config.toml").write_text('project_root_markers = [".feather-root"]\n')
        request = capture_tools(CODEX, self.project, self.user_home, self.codex_home)
        self.assertEqual(skill_paths(render_messages(request.get("input", [])), "group/renamed-handoff"), [alias.resolve()])

    def test_migration_preserves_source_aliases_without_creating_duplicates(self):
        self.add_delegation()
        for source, destination in [("user", "project"), ("project", "user")]:
            self.assertEqual(self.run_setup("install", "--components", "all", "--scope", source).returncode, 0)
            root = self.user_home if source == "user" else self.project
            for component, relative, content in [
                ("handoff", ".agents/skills/renamed/SKILL.md", b"---\nname: handoff\ndescription: Alias\n---\n"),
                ("delegation", ".codex/agents/renamed.toml", b'name = "scout"\ndescription = "Alias"\ndeveloper_instructions = "Read"\n'),
            ]:
                with self.subTest(source=source, component=component):
                    alias = root / relative
                    alias.parent.mkdir(parents=True, exist_ok=True)
                    alias.write_bytes(content)
                    before = {str(p): p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
                    result = self.run_setup("migrate", "--components", component, "--from", source, "--to", destination)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("already declared", result.stderr)
                    self.assertEqual({str(p): p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}, before)
                    alias.unlink()
            self.assertEqual(self.run_setup("remove", "--components", "all", "--scope", source).returncode, 0)

    def test_native_codex_discovers_user_roles_and_skill(self):
        if os.name == "nt":
            profile = os.environ.get("FEATHER_TEST_WINDOWS_PROFILE")
            if not profile:
                self.skipTest("Windows Codex uses the OS profile, not HOME overrides; run the explicit temporary-profile-skill probe")
            self.user_home = Path(profile).resolve(strict=True)
            target = self.user_home / ".agents/skills/handoff/SKILL.md"
            if target.parent.exists():
                self.skipTest("Existing profile skill is preserved; use a clean Windows test profile")
            expected = (ROOT / "skills/handoff/SKILL.md").read_bytes()

            def cleanup_profile_skill():
                if target.exists():
                    if target.is_symlink() or target.read_bytes() != expected:
                        raise AssertionError(f"Profile probe changed concurrently; preserved {target}")
                    target.unlink()
                if target.parent.exists():
                    target.parent.rmdir()

            self.addCleanup(cleanup_profile_skill)
        self.add_delegation()
        result = self.run_setup("install", "--scope", "user", "--components", "all", "--entrance", "user")
        self.assertEqual(result.returncode, 0, result.stderr)
        request = capture_tools(CODEX, self.project, self.user_home, self.codex_home)
        registered = registered_tools(request)
        tools = json.dumps(registered, ensure_ascii=False)
        for role in ["scout", "analyst", "mech-executor", "executor", "security-executor"]:
            self.assertTrue(role in tools, f"User-scope role was not registered: {role}")
        rendered = render_messages(request.get("input", []))
        self.assertIn("<!-- feather-setup:handoff:begin -->", rendered)
        self.assertEqual(skill_paths(rendered, "handoff"),
                         [(self.user_home / ".agents/skills/handoff/SKILL.md").resolve()])
        (self.project / ".feather-root").touch()
        (self.codex_home / "config.toml").write_text(
            'project_root_markers = [".feather-root"]\n'
            f'[projects.{json.dumps(str(self.project))}]\ntrust_level = "trusted"\n', encoding="utf-8")
        for source, destination, expected_root in [("user", "project", self.project),
                                                    ("project", "user", self.user_home)]:
            result = self.run_setup("migrate", "--components", "all", "--from", source, "--to", destination)
            self.assertEqual(result.returncode, 0, result.stderr)
            request = capture_tools(CODEX, self.project, self.user_home, self.codex_home)
            rendered = render_messages(request.get("input", []))
            self.assertEqual(skill_paths(rendered, "handoff"),
                             [(expected_root / ".agents/skills/handoff/SKILL.md").resolve()])
            self.assertIn("feather-setup:handoff:begin", rendered)


if __name__ == "__main__":
    unittest.main()
