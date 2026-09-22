"""Stable JSON output around the public command boundary."""
import argparse
import json
import sys

from .records import list_work, read_work
from .storage import HandoffError, Store
from .baseline import unique_object


def input_payload():
    return json.loads(sys.stdin.buffer.read().decode("utf-8-sig"), object_pairs_hook=unique_object)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Feather handoff files (Python 3.11+)")
    parser.add_argument("--project", required=True, help="Existing project directory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("snapshot", help="Read source observations: JSON {paths: [...]} on stdin")
    compare_command = commands.add_parser("compare", help="Compare a work baseline without modifying files")
    compare_command.add_argument("--work", required=True)
    read = commands.add_parser("read")
    read.add_argument("--work", required=True)
    create = commands.add_parser("create", help="JSON {title, fields, details?} on stdin")
    create.add_argument("--work", required=True)
    update = commands.add_parser("update", help="JSON {version, fields?, details?} on stdin")
    update.add_argument("--work", required=True)
    archive = commands.add_parser("archive", help="Retry completed work: JSON {version} on stdin")
    archive.add_argument("--work", required=True)
    commands.add_parser("clear", help="JSON {source, version, ids} on stdin")
    commands.add_parser("seal", help="JSON {version, ids, destination} on stdin")
    history = commands.add_parser("history")
    history.add_argument("--work")
    history.add_argument("--from-date")
    history.add_argument("--to-date")
    history.add_argument("--keyword")
    history.add_argument("--timezone", default="UTC")
    history.add_argument("--include-sealed", action="store_true")
    args = parser.parse_args()
    try:
        store = Store(args.project)
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
        result = {"status": "error", "complete": False,
                  "code": getattr(error, "code", "io"), "message": str(error)}
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result["status"] in {"error", "partial"} or (args.command == "compare" and result["status"] == "missing") else 0
