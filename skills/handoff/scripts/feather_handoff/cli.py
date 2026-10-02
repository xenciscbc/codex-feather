"""Stable JSON output around the public command boundary."""
import argparse
import json
import os
from pathlib import Path
import sys

from .records import list_work, read_work
from .storage import HandoffError, Store
from .baseline import unique_object


def error_code(error: Exception, store: Store | None, command: str | None) -> str:
    """A missing file is not-found only within the selected project; any other missing file is an I/O failure."""
    if not isinstance(error, FileNotFoundError):
        return getattr(error, "code", "io")
    name = error.filename
    if name is None:
        return "not-found" if command in {"read", "archive", "compare"} else "io"
    if store is None or not isinstance(name, (str, bytes, os.PathLike)):
        return "io"
    target = Path(os.path.normcase(os.path.abspath(os.fsdecode(name))))
    return "not-found" if target.is_relative_to(os.path.normcase(str(store.project))) else "io"


def input_payload():
    try:
        return json.loads(sys.stdin.buffer.read().decode("utf-8-sig"), object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise HandoffError("input", f"Input must be valid UTF-8 JSON: {type(error).__name__}") from None
    except HandoffError as error:  # unique_object's duplicate key is an input problem here, not a snapshot one
        raise HandoffError("input", str(error)) from None


class Parser(argparse.ArgumentParser):
    """Usage errors use the JSON contract; --help stays plain text."""

    def error(self, message):
        raise HandoffError("usage", f"{self.prog}: {message}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # The root options are accepted before or after the command; suppressed defaults keep either spelling.
    root_options = Parser(add_help=False)
    root_options.add_argument("--project", default=argparse.SUPPRESS, help="Existing project directory (required)")
    root_options.add_argument("--exact-root", action="store_true", default=argparse.SUPPRESS,
                              help="Use --project as the confirmed root without Git discovery")
    parser = Parser(description="Feather handoff files (Python 3.11+)", parents=[root_options])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", parents=[root_options])
    commands.add_parser("snapshot", parents=[root_options], help="Read source observations: JSON {paths: [...]} on stdin")
    compare_command = commands.add_parser("compare", parents=[root_options],
                                          help="Compare a work baseline without modifying files")
    compare_command.add_argument("--work", required=True)
    read = commands.add_parser("read", parents=[root_options])
    read.add_argument("--work", required=True)
    create = commands.add_parser("create", parents=[root_options], help="JSON {title, fields, details?} on stdin")
    create.add_argument("--work", required=True)
    update = commands.add_parser("update", parents=[root_options], help="JSON {version, fields?, details?} on stdin")
    update.add_argument("--work", required=True)
    archive = commands.add_parser("archive", parents=[root_options], help="Retry completed work: JSON {version} on stdin")
    archive.add_argument("--work", required=True)
    commands.add_parser("clear", parents=[root_options], help="JSON {source, version, ids} on stdin")
    commands.add_parser("seal", parents=[root_options], help="JSON {version, ids, destination} on stdin")
    history = commands.add_parser("history", parents=[root_options])
    history.add_argument("--work")
    history.add_argument("--from-date")
    history.add_argument("--to-date")
    history.add_argument("--keyword")
    history.add_argument("--timezone", default="UTC")
    history.add_argument("--include-sealed", action="store_true")
    args = store = None
    try:
        args = parser.parse_args()
        if not hasattr(args, "project"):
            parser.error("the following arguments are required: --project")
        store = Store(args.project, exact_root=getattr(args, "exact_root", False))
        if args.command == "snapshot":
            from .observations import capture
            result = capture(store, input_payload())
        elif args.command == "compare":
            from .observations import compare
            result = compare(store, args.work)
        elif args.command in {"create", "update"}:
            from .writing import create_work, update_work
            payload = input_payload()
            action = create_work if args.command == "create" else update_work
            result = action(store, args.work, payload)
        elif args.command == "archive":
            from .archiving import archive_work
            result = archive_work(store, args.work, input_payload())
        elif args.command == "clear":
            from .history_mutations import clear_history
            result = clear_history(store, input_payload())
        elif args.command == "seal":
            from .history_mutations import seal_history
            result = seal_history(store, input_payload())
        elif args.command == "history":
            from .history import query_history
            result = query_history(store, work=args.work, date_from=args.from_date,
                                   date_to=args.to_date, keyword=args.keyword,
                                   timezone=args.timezone, include_sealed=args.include_sealed)
        else:
            result = list_work(store) if args.command == "list" else read_work(store, args.work)
    except (OSError, UnicodeError, ValueError) as error:
        code = error_code(error, store, getattr(args, "command", None))
        result = {"status": "error", "complete": False, "code": code, "message": str(error)}
    except Exception as error:
        result = {"status": "error", "complete": False, "code": "internal",
                  "message": f"{type(error).__name__}: {error}"}
    if store is not None:
        result["root"] = store.root
        if store.root["state"] == "uncertain" and result["status"] != "error":
            result.update(operation_status=result["status"], status="partial", complete=False)
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result["status"] in {"error", "partial"} or (
        getattr(args, "command", None) == "compare" and result["status"] == "missing") else 0
