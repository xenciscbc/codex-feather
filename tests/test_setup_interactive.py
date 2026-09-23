"""Verify the guided entry inspects the chosen project before requesting mutations."""
import argparse
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from setup_installer import interactive
from setup_installer.reporting import show


class SetupInteractiveTest(unittest.TestCase):
    def arguments(self, **overrides):
        values = dict(project=Path("initial"), action=None, components=["all"],
                      scope="project", entrance="none", source_scope=None, target_scope=None)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_selected_project_is_inspected_before_operation_choice(self):
        args = self.arguments()
        events = []

        def answer(prompt, default, choices=None):
            events.append(prompt)
            if prompt == "Project directory":
                return "selected-project"
            if prompt == "Operation":
                return "check"
            return default

        def inspect():
            self.assertEqual(args.project, Path("selected-project"))
            self.assertIsNone(args.action)
            events.append("inspected")

        with patch.object(interactive, "ask", side_effect=answer):
            interactive.choose(args, [], inspect)
        self.assertLess(events.index("Project directory"), events.index("inspected"))
        self.assertLess(events.index("inspected"), events.index("Operation"))
        self.assertEqual(args.action, "check")

    def test_explicit_component_and_operation_are_not_reasked_or_broadened(self):
        args = self.arguments(action="remove", project=Path("chosen"), components=["handoff"], scope="user")
        supplied = ["remove", "--project=chosen", "--components", "handoff", "--scope", "user"]
        events = []
        with patch.object(interactive, "ask", side_effect=AssertionError("Unexpected repeated question")):
            interactive.choose(args, supplied, lambda: events.append("inspected"))
        self.assertEqual(events, ["inspected"])
        self.assertEqual(args.components, ["handoff"])
        self.assertEqual(args.scope, "user")

    def test_eof_after_inspection_does_not_select_an_operation(self):
        args = self.arguments()
        inspected = []
        with patch.object(sys, "stdin", io.StringIO("")), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(EOFError):
                interactive.choose(args, ["--project", "initial"], lambda: inspected.append(True))
        self.assertEqual(inspected, [True])
        self.assertIsNone(args.action)

    def test_human_status_distinguishes_available_skill_from_missing_guidance(self):
        output = io.StringIO()
        show({"action": "check", "components": {"handoff": {
            "status": "available", "guidance": "missing",
            "provider": {"kind": "plugin", "source": "/plugin/skills/handoff/SKILL.md",
                         "session": "unconfirmed"},
        }}}, stream=output)
        report = output.getvalue()
        self.assertIn("available", report)
        self.assertIn("/plugin/skills/handoff/SKILL.md", report)
        self.assertIn("Maintenance guidance: missing", report)
        self.assertIn("Session loading: unconfirmed", report)

    def test_human_preflight_error_identifies_scope_and_reason(self):
        output = io.StringIO()
        show({"action": "check", "scope": "user", "status": "error",
              "error": "Invalid installation record", "changes": []}, stream=output)
        report = output.getvalue()
        self.assertIn("Component scope: user", report)
        self.assertIn("Error: Invalid installation record", report)
        self.assertIn("Status: error", report)


if __name__ == "__main__":
    unittest.main()
