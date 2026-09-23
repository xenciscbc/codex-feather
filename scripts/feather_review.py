"""Inspect or persist Feather automatic review policy; session toggles never call this tool."""
import argparse
import io
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=["show", "preview", "apply"])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--scope", choices=["project", "user"], required=True)
    parser.add_argument("--user-home", type=Path, default=Path.home())
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--review-mode", choices=["off", "auto"])
    parser.add_argument("--expected-plan")
    args = parser.parse_args()
    try:
        from setup_installer.environment import Environment
        from setup_installer.review_settings import run
        from setup_installer.transaction import TransactionError
    except ImportError as error:
        print(json.dumps({"error": f"Installer dependency unavailable: {error}"}))
        return 1
    try:
        user_home = args.user_home.resolve()
        codex_home = (args.codex_home or Path(os.environ.get("CODEX_HOME", user_home / ".codex"))).resolve()
        environment = Environment(args.project.resolve(strict=True), user_home, codex_home, args.scope)
        print(json.dumps(run(args.action, environment, args.review_mode, args.expected_plan), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        detail = error.details if isinstance(error, TransactionError) else {"error": str(error)}
        print(json.dumps(detail, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
