"""Versioned source observations embedded in a human-editable handoff."""
from datetime import datetime
import json
import os
import re

from .storage import HandoffError, legal_name

MAX_FILES = 256
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
HEADING = "## 檔案基準"


def source_name(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise HandoffError("snapshot-path", "Source must be a project-relative POSIX path")
    parts = value.split("/")
    for part in parts:
        legal_name(part)
    lowered = [part.casefold() for part in parts]
    if ".git" in lowered or any(lowered[i:i + 2] == [".feather", "handoffs"] for i in range(len(parts))):
        raise HandoffError("snapshot-path", "Git metadata and handoff sources are excluded")
    return value


def paths_input(values: object) -> list[str]:
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_FILES:
        raise HandoffError("snapshot-input", f"Select 1 to {MAX_FILES} source paths")
    paths = [source_name(value) for value in values]
    if len({os.path.normcase(p) for p in paths}) != len(paths):
        raise HandoffError("snapshot-input", "Duplicate source paths")
    return sorted(paths)


def validate(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"schema_version", "captured_at", "git", "files"}:
        raise HandoffError("snapshot-format", "Invalid snapshot fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise HandoffError("snapshot-version", "Unsupported snapshot schema_version")
    try:
        if datetime.fromisoformat(value["captured_at"]).utcoffset() is None:
            raise ValueError()
    except (TypeError, ValueError):
        raise HandoffError("snapshot-format", "Snapshot time needs a timezone") from None
    git = value["git"]
    if not isinstance(git, dict):
        raise HandoffError("snapshot-format", "Invalid Git observation")
    if git.get("state") == "available":
        if set(git) != {"state", "head", "branch"} or (git["head"] is not None and
                (not isinstance(git["head"], str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", git["head"]))):
            raise HandoffError("snapshot-format", "Invalid Git identity")
        if git["branch"] is not None and (not isinstance(git["branch"], str) or not git["branch"] or
                                           any(ord(c) < 32 for c in git["branch"])):
            raise HandoffError("snapshot-format", "Invalid branch")
    elif git.get("state") == "not-repository":
        if set(git) != {"state"}:
            raise HandoffError("snapshot-format", "Invalid non-repository observation")
    elif git.get("state") == "unknown":
        if set(git) != {"state", "reason"} or not isinstance(git["reason"], str) or not git["reason"]:
            raise HandoffError("snapshot-format", "Unknown Git observation needs a reason")
    else:
        raise HandoffError("snapshot-format", "Invalid Git state")
    files = value["files"]
    if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
        raise HandoffError("snapshot-format", "Invalid source observations")
    paths_input([item.get("path") for item in files])
    for item in files:
        state = item.get("state")
        extra = {"sha256"} if state == "present" else {"reason"} if state == "unknown" else set()
        if not isinstance(state, str) or state not in {"present", "missing", "unknown"} or set(item) != {"path", "state"} | extra:
            raise HandoffError("snapshot-format", "Invalid source observation fields")
        if state == "present" and (not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
            raise HandoffError("snapshot-format", "Invalid SHA-256")
        if state == "unknown" and (not isinstance(item["reason"], str) or not item["reason"]):
            raise HandoffError("snapshot-format", "Unknown source needs a reason")
    return value


def headings(text: str) -> list[tuple[int, int, str]]:
    """Markdown headings outside fenced examples; offsets preserve original bytes-as-text."""
    result = []
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", stripped)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= fence[1] and not match[2].strip():
                fence = None
        elif match and (match[1][0] != "`" or "`" not in match[2]):
            fence = (match[1][0], len(match[1]))
        elif re.match(r"^#{1,6} ", stripped):
            result.append((offset, offset + len(line), stripped))
        offset += len(line)
    return result


def section(text: str, title: str = HEADING) -> tuple[int, int, int] | None:
    items = headings(text)
    found = [i for i, item in enumerate(items)
             if (item[2].rstrip(" \t") if title == "## 詳細紀錄" else item[2]) == title]
    if len(found) > 1:
        raise HandoffError("snapshot-format", f"Duplicate {title} sections")
    if not found:
        return None
    index = found[0]
    start, body, _ = items[index]
    end = next((item[0] for item in items[index + 1:] if re.match(r"^#{1,2} ", item[2])), len(text))
    return start, body, end


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise HandoffError("snapshot-format", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse(text: str) -> dict | None:
    span = section(text)
    if span is None:
        return None
    body = text[span[1]:span[2]].strip()
    match = re.fullmatch(r"```json\r?\n(.*?)\r?\n```", body, flags=re.S)
    if not match:
        raise HandoffError("snapshot-format", "Snapshot section needs one json fence")
    try:
        return validate(json.loads(match[1], object_pairs_hook=unique_object))
    except (ValueError, TypeError) as error:
        raise HandoffError(getattr(error, "code", "snapshot-format"), str(error)) from None


def put(text: str, value: dict) -> str:
    validate(value)
    newline = "\r\n" if "\r\n" in text else "\n"
    value = {**value, "files": sorted(value["files"], key=lambda item: item["path"])}
    block = HEADING + "\n```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n"
    block = block.replace("\n", newline)
    span = section(text)
    if span:
        return text[:span[0]] + block + text[span[2]:]
    return text.rstrip("\r\n") + newline * 2 + block
