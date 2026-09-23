"""Ask for missing choices, preview the same operation, then apply explicit consent."""
import argparse
import json
from pathlib import Path
import sys
from typing import Callable

from .conflicts import ConflictError
from .reporting import show


def ask(prompt: str, default: str, choices: list[str] | None = None) -> str:
    while True:
        options = f" ({'/'.join(choices)})" if choices else ""
        print(f"{prompt}{options} [{default}]: ", file=sys.stderr, end="", flush=True)
        line = sys.stdin.readline()
        if not line:
            raise EOFError("Input ended; no changes were applied")
        value = line.strip() or default
        if choices is None or value in choices:
            return value
        print("Choose one of the listed values.", file=sys.stderr)


def choose(args: argparse.Namespace, supplied: list[str], preflight: Callable[[], None] | None = None) -> None:
    def missing(flag: str) -> bool:
        return not any(value == flag or value.startswith(flag + "=") for value in supplied)

    if missing("--project"):
        args.project = Path(ask("Project directory", str(args.project)))
    if preflight is not None:
        preflight()
    if args.action is None:
        args.action = ask("Operation", "install", ["install", "check", "update", "remove", "migrate"])
    if missing("--components"):
        args.components = [ask("Components", "all", ["all", "delegation", "handoff"])]
    if args.action == "migrate":
        if missing("--from"):
            args.source_scope = ask("Source scope", "project", ["project", "user"])
        if missing("--to"):
            args.target_scope = ask("Destination scope", "user" if args.source_scope == "project" else "project",
                                    ["project", "user"])
    elif missing("--scope"):
        args.scope = ask("Component scope", "project", ["project", "user"])
    if args.action in {"install", "migrate"} and missing("--entrance"):
        prompt = "Entrance scope (none preserves existing entrance placement)" if args.action == "migrate" else "Entrance scope"
        args.entrance = ask(prompt, "none", ["none", "project", "user"])


def run(args: argparse.Namespace, operation: Callable[[bool], dict]) -> tuple[dict, int]:
    try:
        preview = operation(True)
    except ConflictError as error:
        print(json.dumps(error.details, ensure_ascii=False, indent=2), file=sys.stderr)
        can_replace = all(item["owned"] for item in error.details["conflicts"]) and args.action not in {"migrate", "check"}
        choice = ask("Resolve conflict", "keep", ["keep", "replace", "cancel"] if can_replace else ["keep", "cancel"])
        if choice != "replace":
            return {"status": "preserved" if choice == "keep" else "cancelled", "changes": []}, 1 if choice == "keep" else 0
        args.on_conflict = "replace"
        preview = operation(True)
    reused = [record for record in preview.get("components", {}).values() if record.get("status") == "reused"] if isinstance(preview.get("components"), dict) else []
    if args.action == "install" and reused:
        show(preview, args.json, sys.stderr)
        choice = ask("Existing capability", "reuse", ["reuse", "migrate", "cancel"])
        if choice == "cancel":
            return {"status": "cancelled", "changes": []}, 0
        if choice == "migrate":
            scopes = {item["scope"] for item in reused}
            if len(scopes) != 1 or args.scope in scopes:
                raise ValueError("This source is in an ancestor project; run an explicit migration using its original project directory")
            args.action, args.source_scope, args.target_scope = "migrate", scopes.pop(), args.scope
            preview = operation(True)
    print("Planned operation:", file=sys.stderr)
    show(preview, args.json, sys.stderr)
    if args.dry_run or args.action == "check":
        return preview, 0
    if ask("Apply these changes", "no", ["yes", "no"]) != "yes":
        return {"status": "cancelled", "changes": []}, 0
    return operation(False), 0
