"""Read human-editable handoffs without turning summaries into authority."""
import re
from datetime import datetime

from .storage import Snapshot, Store, read_file
from .baseline import parse as parse_baseline


FIELDS = {"updated": "更新", "status": "狀態", "goal": "目標", "progress": "進度",
          "next": "下一步", "notes": "注意", "environment": "環境", "verification": "驗證", "decision": "決策"}
REQUIRED = ("updated", "status", "goal", "progress", "next")
STATUSES = {"進行中", "受阻", "完成"}


def valid_time(value: str) -> bool:
    try:
        return datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


def summary(snapshot: Snapshot) -> dict:
    text = snapshot.text
    title = re.search(r"(?m)^# (.+)$", text)
    remainder = text[title.end():] if title else text
    section = re.search(r"(?m)^#{1,6} ", remainder)
    header = remainder[:section.start()] if section else remainder
    fields = {}
    problems = []
    for key, label in FIELDS.items():
        matches = re.findall(rf"(?m)^{label}[：:][ \t]*([^\r\n]*)", header)
        fields[key] = matches[0].strip() if len(matches) == 1 else ""
        if len(matches) > 1 or (key in REQUIRED and not fields[key]):
            problems.append(f"Expected one nonempty {label} field" if key in REQUIRED else f"Duplicate {label} field")
    if not title:
        problems.append("Missing work title")
    elif title.start() != 0:
        problems.append("Work title must be the first line; preceding content needs review")
    if fields["status"] not in STATUSES:
        problems.append("Invalid status")
    if not valid_time(fields["updated"]):
        problems.append("Invalid ISO timestamp with timezone")
    try:
        baseline_state = "available" if parse_baseline(text) is not None else "absent"
    except ValueError as error:
        baseline_state = "invalid"
        problems.append(str(error))
    return {"work": snapshot.path.name, "title": title.group(1).strip() if title else snapshot.path.stem,
            **fields, "progress": fields["progress"][:240], "progress_truncated": len(fields["progress"]) > 240,
            "version": snapshot.version, "problems": problems, "snapshot_state": baseline_state,
            "record_status": "格式待確認" if problems else
            ("完成待歸檔" if fields["status"] == "完成" else fields["status"])}


def list_work(store: Store) -> dict:
    paths = store.work_paths()
    items = []
    issues = []
    versions = {}
    for path in paths:
        try:
            item = summary(read_file(path))
            versions[path] = item["version"]
            items.append(item)
            if item["problems"]:
                issues.append({"work": path.name, "code": "format", "message": "; ".join(item["problems"])})
        except (OSError, UnicodeError, ValueError) as error:
            issues.append({"work": path.name, "code": getattr(error, "code", "io"), "message": str(error)})
    try:
        if store.work_paths() != paths:
            issues.append({"work": "", "code": "changed", "message": "Work directory changed during listing"})
        for path, version in versions.items():
            if read_file(path).version != version:
                issues.append({"work": path.name, "code": "changed", "message": "Work changed during listing"})
    except (OSError, ValueError) as error:
        issues.append({"work": "", "code": "changed", "message": str(error)})
    return {"status": "partial" if issues else ("ok" if store.directory.exists() else "missing"),
            "complete": not issues, "items": items, "issues": issues}


def read_work(store: Store, name: str) -> dict:
    snapshot = read_file(store.work_path(name))
    item = summary(snapshot)
    return {**item, "work_status": item["status"], "status": "partial" if item["problems"] else "ok",
            "complete": not item["problems"], "content": snapshot.text}
