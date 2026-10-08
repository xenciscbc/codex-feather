"""Validated handoff mutations; content decisions remain with the user and Agent."""
from datetime import datetime
import re
import subprocess

from .archiving import _matching, check_archivable
from .history import parse_history
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
    for key, value in fields.items():
        # A blank optional value would save an empty field that later partial updates refuse.
        if not value.strip():
            raise HandoffError("input", f"{key} ({FIELDS[key]}) must not be blank; omit it instead")
    if "status" in fields and fields["status"] not in STATUSES:
        raise HandoffError("input", "Status must be 進行中, 受阻, or 完成")
    if not valid_time(fields["updated"]):
        raise HandoffError("input", "updated must be an ISO datetime with timezone")
    return fields


def placed_sections(text: str, start: int = 0) -> list[tuple[int, str]]:
    """Fence-aware level-1/2 headings at or after start, with offsets relative to start."""
    return [(offset - start, line) for offset, _, line in baseline.headings(text)
            if offset >= start and baseline.level(line) <= 2]


def sections(text: str, start: int = 0) -> list[str]:
    """Fence-aware level-1/2 headings at or after start; each one ends a managed section."""
    return [line for _, line in placed_sections(text, start)]


FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def swallowed_sections(span: str) -> tuple[list[str], str | None]:
    """Level-1/2 heading lines that code fences hide in existing details, and why replacing them would drop sections.

    Uses the fence rules of baseline.headings. A self-contained fenced example may hide headings; an opener left
    open at the end of the span, or a hiding fence that also holds a same-character opener with an info string
    (such as a managed ```json block), shows an unbalanced opener that swallowed later sections."""
    hidden, fence, held, inner, reason = [], None, [], False, None
    for line in span.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        match = FENCE.match(stripped)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= fence[1] and not match[2].strip():
                if held and inner:
                    reason = reason or "fenced-block"
                hidden += held
                fence, held, inner = None, [], False
            elif match and match[1][0] == fence[0] and match[2].strip() and (fence[0] != "`" or "`" not in match[2]):
                inner = True
            elif 0 < baseline.level(stripped) <= 2:
                held.append(stripped)
        elif match and (match[1][0] != "`" or "`" not in match[2]):
            fence = (match[1][0], len(match[1]))
    if fence:
        if held and inner:
            reason = reason or "fenced-block"
        hidden += held
        reason = "open-fence" if hidden else reason
    return hidden, reason if hidden else None


def details_warnings(details: str) -> list[str]:
    return [f"details heading '{line}' starts a separate section; later details updates replace only text before it"
            for line in sections(details)]


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
    warnings = []
    if "details" in payload:
        details = re.sub(r"\r\n|\r", "\n", text_value(payload["details"], "details", multiline=True)).rstrip("\n")
        warnings = details_warnings(details)
        content += "\n## 詳細紀錄\n" + details + "\n"
    if "snapshot" in payload:
        # A second managed section in details must not be silently replaced.
        if baseline.section(content) is not None:
            raise HandoffError("snapshot-format", "Snapshot supplied both in details and payload")
        content = baseline.put(content, baseline.validate(payload["snapshot"]))
    new_baseline = baseline.parse(content)
    if new_baseline is not None:
        verify_for_save(store, new_baseline)
    data = content.encode("utf-8")
    if fields["status"] == "完成":
        check_archivable(Snapshot(path, data))
    create_file(path, data)
    result = finish_save(store, name, tracking, payload)
    if warnings:
        result["warnings"] = warnings
    return result


def update_work(store: Store, name: str, raw: object) -> dict:
    store.require_write_root()
    payload = input_object(raw)
    if set(payload) - {"version", "fields", "details", "title", "replacement", "tracking", "defer_history", "snapshot"}:
        raise HandoffError("input", "Unknown update options")
    original = read_file(store.work_path(name))
    if payload.get("version") != original.version:
        raise HandoffError("conflict", "Source changed or version missing; read the work again")
    before = summary(original)
    if before["status"] == "完成" and (
            "replacement" not in payload or set(payload) - {"version", "replacement", "tracking", "defer_history"}):
        raise HandoffError("completed", "Completed identity is retained; use archive to retry archival, or a reviewed "
                           "replacement keeping title, 更新 and 狀態：完成 when archive reports a body format problem")
    content = original.text
    newline = "\r\n" if "\r\n" in content else "\n"
    warnings = siblings = None
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
            details = re.sub(r"\r\n|\r|\n", newline, text_value(payload["details"], "details", multiline=True))
            if "snapshot" in payload and baseline.section(details) is not None:
                raise HandoffError("snapshot-format", "Snapshot supplied both in details and payload")
            try:
                details_span = baseline.section(content, "## 詳細紀錄")
            except ValueError as error:
                raise HandoffError("format", str(error)) from None
            warnings = details_warnings(details)
            if details_span:
                # Replacing details whose unbalanced fence already swallowed later sections would drop them.
                hidden, reason = swallowed_sections(content[details_span[1]:details_span[2]])
                if reason:
                    listed = ", ".join(hidden)
                    cause = (f"leave a code fence open over {listed}" if reason == "open-fence"
                             else f"hide {listed} inside a code fence that also holds a fenced block")
                    raise HandoffError("details-format", f"existing details {cause}; "
                                       "repair them with a reviewed replacement")
                prefix = content[:details_span[1]]
                if not prefix.endswith("\n"):
                    prefix += newline
                # Sibling sections after the managed span must survive unchanged (and stay visible).
                # The tail is copied verbatim, so each heading keeps its offset within it; a fence
                # change that re-interprets the tail moves them even when the heading texts repeat.
                siblings = placed_sections(content, details_span[2])
                inserted = prefix + details.rstrip("\r\n") + newline
                content = inserted + content[details_span[2]:]
                visible = placed_sections(content, len(inserted))
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
    after = summary(Snapshot(original.path, data))
    if before["status"] == "完成":
        if (after["title"], after["updated"], after["status"]) != (before["title"], before["updated"], "完成"):
            raise HandoffError("completed", "A completed work replacement must keep its title, 更新 and 狀態：完成")
        try:
            history = parse_history(read_file(store.directory / "history.md"))
        except FileNotFoundError:
            history = None
        if history is not None and _matching(history, before["title"], before["updated"]):
            raise HandoffError("completed", "History already holds this completion identity; use archive to retry archival")
    if after["status"] == "完成":
        check_archivable(Snapshot(original.path, data))
    if siblings is not None and visible != siblings:
        raise HandoffError("details-format", f"this details text would hide or change existing sections "
                           f"({', '.join(line for _, line in siblings)}); close the code fence or use ### headings")
    tracking = payload.get("tracking", "default")
    if not isinstance(tracking, str) or tracking not in {"default", "track"}:
        raise HandoffError("input", "tracking must be default or track")
    replace_file(original, data)
    result = finish_save(store, name, tracking, payload)
    if siblings is not None:
        result["preserved_sections"] = [line for _, line in siblings]
    if warnings:
        result["warnings"] = warnings
    return result


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
        if result["work_status"] == "完成":
            # A completed work refuses normal updates; archive retries it and applies the same tracking choice.
            recovery = ("Completed work was saved but not archived because tracking failed; inspect the reported "
                        "work and resolve the Git rules, then run archive with "
                        f'{{"version": "<current version>", "tracking": "{tracking}"}}. '
                        "Do not repeat create or update.")
        else:
            recovery = ("Work was saved before tracking failed; inspect the reported work and Git rules, "
                        "then retry update with the current version. Do not repeat create.")
        return {**observed, "status": "partial", "complete": False, "code": "tracking-failed",
                "cause_code": getattr(error, "code", "io"), "message": str(error), "state": state,
                "work": name, "work_path": str(store.directory / name), "saved_version": result["version"],
                "tracking": "error", "recovery": recovery}
    if result["work_status"] == "完成":
        if payload.get("defer_history"):
            return {**result, "status": "partial", "complete": False, "code": "deferred",
                    "message": "Completed work saved; shared history deferred for coordinated retry"}
        from .archiving import archive_work
        try:
            # Tracking was applied above; archive_work must not run it a second time.
            archived = archive_work(store, name, {"version": result["version"]}, apply_tracking=False)
        except (OSError, ValueError) as error:
            observed = {}
            try:
                observed = read_work(store, name)
            except (OSError, ValueError):
                pass
            return {**observed, "status": "partial", "complete": False, "code": "archive-failed",
                    "cause_code": getattr(error, "code", "io"), "message": str(error), "work": name,
                    "work_path": str(store.directory / name), "saved_version": result["version"],
                    "tracking": result["tracking"], "recovery": "retry-archive"}
        return {**archived, "tracking": result["tracking"]}
    return result
