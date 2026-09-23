"""Command-line boundary shared by source and packaged executables."""
import argparse
import json
import io
import os
from pathlib import Path
import sys

from . import VERSION
from .bundle import Bundle
from .environment import Environment
from .installer import execute
from .transaction import TransactionError
from .conflicts import ConflictError
from .migration import migrate
from . import interactive
from .reporting import show


def main(argv: list[str] | None = None, handoff_provider: Path | None = None,
         default_entrance: bool = False) -> int:
    # Frozen Python ignores PYTHONUTF8; the CLI's redirected JSON must still be UTF-8 on Windows.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Install selected Feather capabilities from an offline bundle.",
                                     allow_abbrev=False)
    parser.add_argument("action", nargs="?", choices=["install", "check", "update", "remove", "migrate"])
    parser.add_argument("--version", action="version", version=f"feather-setup {VERSION}")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--scope", choices=["project", "user"], default="project")
    parser.add_argument("--user-home", type=Path, default=Path.home())
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--bundle", type=Path, default=Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd())
    parser.add_argument("--codex")
    parser.add_argument("--components", nargs="+", choices=["all", "handoff", "delegation"], default=["all"])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--entrance", choices=["none", "project", "user"], default="none")
    parser.add_argument("--on-conflict", choices=["fail", "keep", "replace"], default="fail")
    parser.add_argument("--from", dest="source_scope", choices=["project", "user"])
    parser.add_argument("--to", dest="target_scope", choices=["project", "user"])
    parser.add_argument("--interactive", action="store_true", help="Guide missing choices and preview before applying")
    arguments = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(arguments)
    try:
        guided = args.action is None or args.interactive
        if guided:
            def preflight() -> None:
                user_home = args.user_home.resolve()
                codex_home = args.codex_home or Path(os.environ.get("CODEX_HOME", user_home / ".codex"))
                project = args.project.resolve(strict=True)
                if not project.is_dir():
                    raise ValueError(f"Project directory is not a directory: {project}")
                codex_home = codex_home.resolve()
                bundle = Bundle.read(args.bundle.resolve())
                print("Installed state before choosing an operation:", file=sys.stderr)
                for scope in ("project", "user"):
                    environment = Environment(project, user_home, codex_home, scope)
                    try:
                        report = execute("check", environment, bundle, ["all"], args.codex,
                                         handoff_provider=handoff_provider)
                        report.pop("_plan_id")
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        report = {"action": "check", "project": str(project), "scope": scope,
                                  "status": "error", "error": str(error), "changes": []}
                    show(report, args.json, sys.stderr)
            interactive.choose(args, arguments, preflight)
        if args.action != "migrate" and (args.source_scope is not None or args.target_scope is not None):
            raise ValueError("--from and --to belong to migrate; choose the migration operation explicitly")
        if args.action in {"check", "remove"} and args.entrance != "none":
            raise ValueError("Check/remove use the recorded entrance location; --entrance selects a location for install/update/migrate")
        user_home = args.user_home.resolve()
        codex_home = args.codex_home or Path(os.environ.get("CODEX_HOME", user_home / ".codex"))
        environment = Environment(args.project.resolve(strict=True), user_home, codex_home.resolve(), args.scope)
        bundle = Bundle.read(args.bundle.resolve())
        approved_plan = None
        def operation(dry_run: bool) -> dict:
            nonlocal approved_plan
            if args.action == "migrate":
                if args.on_conflict == "replace":
                    raise ValueError("Migration preserves source bytes; resolve customizations with update before migrating")
                report = migrate(environment, bundle, args.components, args.source_scope, args.target_scope,
                                 args.codex, dry_run, args.entrance, approved_plan if not dry_run else None,
                                 handoff_provider)
            else:
                report = execute(args.action, environment, bundle, args.components, args.codex,
                                 dry_run, args.entrance, args.on_conflict, approved_plan if not dry_run else None,
                                 handoff_provider, default_entrance)
            plan_id = report.pop("_plan_id")
            if dry_run:
                approved_plan = plan_id
            return report

        report, code = interactive.run(args, operation) if guided else (operation(args.dry_run), 0)
        show(report, args.json)
        return 1 if report.get("status") == "attention-required" else code
    except (TransactionError, ConflictError) as error:
        print(json.dumps(error.details, ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error), "next_step": "Correct the reported path, environment or conflict and retry --dry-run; no success is claimed."}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print(json.dumps({"status": "cancelled", "changes": []}))
        return 0
