"""Render the operation result for people or automation."""
import json
import sys
from typing import TextIO


def show(report: dict, structured: bool = False, stream: TextIO | None = None) -> None:
    stream = stream or sys.stdout
    if structured:
        print(json.dumps(report, ensure_ascii=False, indent=2), file=stream)
        return
    label = report.get("action", report.get("status", "Feather"))
    print(f"Feather: {label}" + (" (preview)" if report.get("dry_run") else ""), file=stream)
    if report.get("project"):
        print(f"Project: {report['project']}", file=stream)
    if report.get("scope"):
        print(f"Component scope: {report['scope']}", file=stream)
    if report.get("from"):
        print(f"Component scope: {report['from']} -> {report['to']}", file=stream)
    if report.get("impact"):
        print(report["impact"], file=stream)
    components = report.get("components", {})
    for name in components:
        detail = components[name] if isinstance(components, dict) else {}
        print(f"  {name}: {detail.get('status', label)}", file=stream)
        if detail.get("status") == "reused":
            for path in detail["paths"]:
                print(f"    using {path}", file=stream)
    for name, entry in report.get("entrances", {}).items():
        print(f"  {name} entrance ({entry['scope']}): {entry['path']} [{entry['status']}]", file=stream)
    for change in report.get("changes", []):
        print(f"  {change['action'].upper()} {change['path']}", file=stream)
    if not report.get("changes") and label != "check":
        print("No file changes.", file=stream)
    if report.get("status"):
        print(f"Status: {report['status']}", file=stream)
    if report.get("backup"):
        print(f"Backup: {report['backup']}", file=stream)
    if report.get("entrances"):
        print("Codex document limits, deeper instructions and project trust still affect loading.", file=stream)
