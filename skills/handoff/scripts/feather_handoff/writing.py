"""Validated handoff mutations; content decisions remain with the user and Agent."""
from datetime import datetime
import re
import subprocess

from .records import FIELDS, REQUIRED, STATUSES, read_work, summary, valid_time
from .storage import HandoffError, Snapshot, Store, create_file, read_file, replace_file
from .tracking import ensure_tracking
from . import baseline
from .observations import verify_for_save


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
    store.require_write_root()
    payload = input_object(raw)
    if set(payload) - {"title", "fields", "details", "tracking", "defer_history", "snapshot"}:
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
    if "snapshot" in payload:
        # A second managed section in details must not be silently replaced.
        if baseline.section(content) is not None:
            raise HandoffError("snapshot-format", "Snapshot supplied both in details and payload")
        content = baseline.put(content, baseline.validate(payload["snapshot"]))
    new_baseline = baseline.parse(content)
    if new_baseline is not None:
        verify_for_save(store, new_baseline)
    create_file(path, content.encode("utf-8"))
    return finish_save(store, name, tracking, payload)


def update_work(store: Store, name: str, raw: object) -> dict:
    store.require_write_root()
    payload = input_object(raw)
    if set(payload) - {"version", "fields", "details", "title", "replacement", "tracking", "defer_history", "snapshot"}:
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
        baseline.parse(content)  # Preserve ambiguous managed content for explicit repair.
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
            if "snapshot" in payload and baseline.section(details) is not None:
                raise HandoffError("snapshot-format", "Snapshot supplied both in details and payload")
            try:
                details_span = baseline.section(content, "## 詳細紀錄")
            except ValueError as error:
                raise HandoffError("format", str(error)) from None
            if details_span:
                prefix = content[:details_span[1]]
                if not prefix.endswith("\n"):
                    prefix += newline
                content = prefix + details.rstrip("\r\n") + newline + content[details_span[2]:]
            else:
                content = content.rstrip("\r\n") + newline * 2 + "## 詳細紀錄" + newline + details.rstrip("\r\n") + newline
        if "snapshot" in payload:
            content = baseline.put(content, baseline.validate(payload["snapshot"]))
    new_baseline = baseline.parse(content)
    try:
        old_baseline = baseline.parse(original.text)
    except ValueError:
        old_baseline = None  # An explicit replacement may repair an invalid section.
    if old_baseline is not None and new_baseline is None:
        raise HandoffError("snapshot-format", "Removing an existing baseline is not supported")
    if new_baseline is not None and ("snapshot" in payload or new_baseline != old_baseline):
        verify_for_save(store, new_baseline)
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
    return finish_save(store, name, tracking, payload)


def finish_save(store: Store, name: str, tracking: str, payload: dict) -> dict:
    result = read_work(store, name)
    try:
        result["tracking"] = ensure_tracking(store, name, tracking)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        observed = {}
        state = "unreadable"
        try:
            observed = read_work(store, name)
            state = "saved" if observed["version"] == result["version"] else "changed"
        except FileNotFoundError:
            state = "missing"
        except (OSError, ValueError):
            pass
        return {**observed, "status": "partial", "complete": False, "code": "tracking-failed",
                "cause_code": getattr(error, "code", "io"), "message": str(error), "state": state,
                "work": name, "work_path": str(store.directory / name), "saved_version": result["version"],
                "tracking": "error",
                "recovery": "Work was saved before tracking failed; inspect the reported work and Git rules, then retry update with the current version or archive completed work. Do not repeat create."}
    if result["work_status"] == "完成":
        if payload.get("defer_history"):
            return {**result, "status": "partial", "complete": False, "code": "deferred",
                    "message": "Completed work saved; shared history deferred for coordinated retry"}
        from .archiving import archive_work
        return {**archive_work(store, name, {"version": result["version"]}), "tracking": result["tracking"]}
    return result
