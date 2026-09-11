"""Validated handoff mutations; content decisions remain with the user and Agent."""
from datetime import datetime
import re

from .records import FIELDS, REQUIRED, STATUSES, read_work, summary, valid_time
from .storage import HandoffError, Snapshot, Store, create_file, read_file, replace_file
from .tracking import ensure_tracking


def input_object(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise HandoffError("input", "Input must be a JSON object")
    return payload


def text_value(value: object, name: str, multiline: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise HandoffError("input", f"{name} must be text without NUL")
    if not multiline and ("\n" in value or "\r" in value):
        raise HandoffError("input", f"{name} must be a single line; use details for longer content")
    return value


def validated_fields(payload: dict, create: bool) -> dict[str, str]:
    values = input_object(payload.get("fields", {}))
    if set(values) - set(FIELDS):
        raise HandoffError("input", f"Unknown fields: {sorted(set(values) - set(FIELDS))}")
    fields = {key: text_value(value, key) for key, value in values.items()}
    if create:
        fields.setdefault("status", "進行中")
    fields.setdefault("updated", datetime.now().astimezone().isoformat(timespec="microseconds"))
    for key in REQUIRED:
        if (create or key in fields) and not fields.get(key, "").strip():
            raise HandoffError("input", f"Missing or empty {key}")
    if "status" in fields and fields["status"] not in STATUSES:
        raise HandoffError("input", "Status must be 進行中, 受阻, or 完成")
    if not valid_time(fields["updated"]):
        raise HandoffError("input", "updated must be an ISO datetime with timezone")
    return fields


def create_work(store: Store, name: str, raw: object) -> dict:
    payload = input_object(raw)
    if set(payload) - {"title", "fields", "details", "tracking", "defer_history"}:
        raise HandoffError("input", "Unknown create options")
    path = store.work_path(name)
    title = text_value(payload.get("title", path.stem), "title").strip()
    if not title:
        raise HandoffError("input", "Title must not be empty")
    fields = validated_fields(payload, create=True)
    tracking = payload.get("tracking", "default")
    if not isinstance(tracking, str) or tracking not in {"default", "track"}:
        raise HandoffError("input", "tracking must be default or track")
    content = f"# {title}\n" + "\n".join(f"{label}：{fields[key]}" for key, label in FIELDS.items() if key in fields) + "\n"
    if "details" in payload:
        content += "\n## 詳細紀錄\n" + text_value(payload["details"], "details", multiline=True).rstrip("\n") + "\n"
    create_file(path, content.encode("utf-8"))
    tracked = ensure_tracking(store, name, tracking)
    return finish_save(store, name, tracked, payload)


def update_work(store: Store, name: str, raw: object) -> dict:
    payload = input_object(raw)
    if set(payload) - {"version", "fields", "details", "title", "replacement", "tracking", "defer_history"}:
        raise HandoffError("input", "Unknown update options")
    original = read_file(store.work_path(name))
    if payload.get("version") != original.version:
        raise HandoffError("conflict", "Source changed or version missing; read the work again")
    if summary(original)["status"] == "完成":
        raise HandoffError("completed", "Completed identity is retained; use archive to retry archival")
    content = original.text
    newline = "\r\n" if "\r\n" in content else "\n"
    if "replacement" in payload:
        if set(payload) - {"version", "replacement", "tracking", "defer_history"}:
            raise HandoffError("input", "replacement cannot be combined with partial edits")
        content = text_value(payload["replacement"], "replacement", multiline=True)
    else:
        fields = validated_fields(payload, create=False)
        title = re.search(r"(?m)^# ([^\r\n]+)", content)
        if not title:
            raise HandoffError("format", "Missing title requires an explicit reviewed replacement")
        if "title" in payload:
            value = text_value(payload["title"], "title").strip()
            if not value:
                raise HandoffError("input", "Title must not be empty")
            content = content[:title.start(1)] + value + content[title.end(1):]
            title = re.search(r"(?m)^# ([^\r\n]+)", content)
            assert title is not None
        section = re.search(r"(?m)^#{1,6} ", content[title.end():])
        end = title.end() + section.start() if section else len(content)
        header, tail = content[:end], content[end:]
        for key, value in fields.items():
            expression = rf"(?m)^{FIELDS[key]}[：:][^\r\n]*"
            matches = list(re.finditer(expression, header))
            if len(matches) > 1:
                raise HandoffError("format", f"Duplicate {FIELDS[key]} requires an explicit reviewed replacement")
            line = f"{FIELDS[key]}：{value}"
            if matches:
                match = matches[0]
                if not re.split("[：:]", match.group(), maxsplit=1)[1].strip():
                    raise HandoffError("format", f"Empty or multiline {FIELDS[key]} requires an explicit reviewed replacement")
                header = header[:match.start()] + line + header[match.end():]
            else:
                header = header.rstrip("\r\n") + newline + line + newline + newline
        content = header + tail
        if "details" in payload:
            details = text_value(payload["details"], "details", multiline=True)
            heading = re.search(r"(?m)^## 詳細紀錄[ \t]*\r?$", content)
            if heading:
                following = re.search(r"(?m)^## (?!詳細紀錄)", content[heading.end():])
                boundary = heading.end() + following.start() if following else len(content)
                content = content[:heading.end()] + newline + details.rstrip("\r\n") + newline + content[boundary:]
            else:
                content = content.rstrip("\r\n") + newline * 2 + "## 詳細紀錄" + newline + details.rstrip("\r\n") + newline
    data = content.encode("utf-8")
    if original.data.startswith(b"\xef\xbb\xbf"):
        data = b"\xef\xbb\xbf" + data
    problems = summary(Snapshot(original.path, data))["problems"]
    if problems:
        raise HandoffError("format", "; ".join(problems))
    tracking = payload.get("tracking", "default")
    if not isinstance(tracking, str) or tracking not in {"default", "track"}:
        raise HandoffError("input", "tracking must be default or track")
    replace_file(original, data)
    tracked = ensure_tracking(store, name, tracking)
    return finish_save(store, name, tracked, payload)


def finish_save(store: Store, name: str, tracked: str, payload: dict) -> dict:
    result = {**read_work(store, name), "tracking": tracked}
    if result["work_status"] == "完成":
        if payload.get("defer_history"):
            return {**result, "status": "partial", "complete": False, "code": "deferred",
                    "message": "Completed work saved; shared history deferred for coordinated retry"}
        from .archiving import archive_work
        return {**archive_work(store, name, {"version": result["version"]}), "tracking": tracked}
    return result
