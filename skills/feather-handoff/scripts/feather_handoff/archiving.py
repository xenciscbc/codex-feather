"""Save a completed work body to shared history before removing its source."""
from pathlib import Path

from .history import HistoryDocument, HistoryEntry, parse_history
from .records import summary
from .storage import HandoffError, Snapshot, Store, create_file, read_file, replace_file, require_current


HISTORY_HEADER = b"# \xe4\xba\xa4\xe6\x8e\xa5\xe6\xad\xb7\xe5\x8f\xb2\n\n"


def _input_version(raw: object) -> str:
    if not isinstance(raw, dict) or set(raw) != {"version"} or not isinstance(raw["version"], str):
        raise HandoffError("input", "Archive input must be a JSON object containing only version")
    return raw["version"]


def work_body(snapshot: Snapshot, title: str) -> bytes:
    start = 3 if snapshot.data.startswith(b"\xef\xbb\xbf") else 0
    line_end = snapshot.data.find(b"\n", start)
    if line_end < 0:
        raise HandoffError("format", "Completed work must have a title line followed by its body")
    try:
        title_line = snapshot.data[start:line_end].decode("utf-8").removesuffix("\r")
    except UnicodeError as error:
        raise HandoffError("format", f"Invalid UTF-8 title: {error}") from error
    if title_line != f"# {title}":
        raise HandoffError("format", "The first line must be the work title")
    return snapshot.data[line_end + 1:]


def _matching(document: HistoryDocument, title: str, completed: str) -> list[HistoryEntry]:
    return [entry for entry in document.entries
            if entry.title == title and entry.completed == completed]


def same_body(entry: HistoryEntry, body: bytes, document: HistoryDocument) -> bool:
    """Compare an archived body, allowing only a newline that frames a following entry."""
    if entry.body_bytes == body:
        return True
    if body.endswith(b"\n") or entry.body_bytes != body + b"\n":
        return False
    return any(candidate.byte_start == entry.byte_end for candidate in document.entries
               if candidate is not entry)


def _validated_document(snapshot: Snapshot) -> HistoryDocument:
    document = parse_history(snapshot, "history.md")
    if document.issues:
        raise HandoffError("history-format", "History has ambiguous or invalid entry boundaries; existing data was preserved")
    return document


def _candidate(existing: Snapshot | None, entry_data: bytes) -> bytes:
    if existing is None:
        return HISTORY_HEADER + entry_data
    separator = b"" if existing.data.endswith(b"\n") else b"\n"
    return existing.data + separator + entry_data


def _pending(work: Snapshot, history_path: Path, code: str, message: str,
             identity: str, title: str, completed: str, history: Snapshot | None,
             appended: bool | None = None) -> dict:
    return {"status": "partial", "complete": False, "archived": False, "code": code,
            "message": message, "recovery": "retry-archive", "id": identity,
            "title": title, "completed": completed, "work_version": work.version,
            "history_version": history.version if history is not None else None,
            "history_appended": appended,
            "work_path": str(work.path), "history_path": str(history_path),
            "work_present": work.path.exists(), "history_present": history_path.exists(),
            "pending": [str(work.path)] if work.path.exists() else []}


def archive_work(store: Store, name: str, raw: object) -> dict:
    store.require_write_root()
    expected = _input_version(raw)
    work = read_file(store.work_path(name))
    if expected != work.version:
        raise HandoffError("conflict", "Source changed or version missing; read the completed work again")
    item = summary(work)
    if item["problems"]:
        raise HandoffError("format", "; ".join(item["problems"]))
    if item["status"] != "完成":
        raise HandoffError("completed", "Only a completed work can be archived")
    title, completed = item["title"], item["updated"]
    body = work_body(work, title)
    marker = f"## {title} · 完成：{completed}\n".encode("utf-8")
    entry_data = marker + body
    history_path = store.directory / "history.md"

    existing = None
    try:
        existing = read_file(history_path)
    except FileNotFoundError:
        pass
    if existing is not None:
        document = _validated_document(existing)
        matches = _matching(document, title, completed)
        if len(matches) > 1:
            raise HandoffError("conflict", f"Duplicate completion identity in {history_path}; all data was preserved")
        if matches:
            if not same_body(matches[0], body, document):
                raise HandoffError("conflict", f"Completion identity has a different body in {history_path}; all data was preserved")
            saved = existing
            appended = False
            identity = matches[0].identity
        else:
            candidate = _candidate(existing, entry_data)
            preview = _validated_document(Snapshot(history_path, candidate))
            intended = _matching(preview, title, completed)
            if (len(preview.entries) != len(document.entries) + 1 or len(intended) != 1
                    or intended[0].body_bytes != body or not intended[0].boundary_known):
                raise HandoffError("history-format", "Generated entry cannot be separated exactly; existing data was preserved")
            identity = intended[0].identity
            try:
                saved = replace_file(existing, candidate)
            except (OSError, ValueError) as error:
                observed = None
                try:
                    observed = read_file(history_path)
                except (OSError, ValueError):
                    pass
                return _pending(work, history_path, "history-save-failed", str(error),
                                identity, title, completed, observed)
            appended = True
    else:
        candidate = _candidate(None, entry_data)
        preview = _validated_document(Snapshot(history_path, candidate))
        intended = _matching(preview, title, completed)
        if (len(preview.entries) != 1 or len(intended) != 1
                or intended[0].body_bytes != body or not intended[0].boundary_known):
            raise HandoffError("history-format", "Generated entry cannot be separated exactly; no history was created")
        identity = intended[0].identity
        try:
            saved = create_file(history_path, candidate)
        except (OSError, ValueError) as error:
            observed = None
            try:
                observed = read_file(history_path)
            except (OSError, ValueError):
                pass
            return _pending(work, history_path, "history-save-failed", str(error),
                            identity, title, completed, observed)
        appended = True

    try:
        verified = _validated_document(read_file(history_path))
    except (OSError, ValueError) as error:
        return _pending(work, history_path, "history-verify-failed", str(error), identity,
                        title, completed, saved, appended)
    matches = _matching(verified, title, completed)
    if len(matches) != 1 or not same_body(matches[0], body, verified):
        return _pending(work, history_path, "history-verify-failed",
                        "Saved history did not contain exactly the completed body", identity,
                        title, completed, verified.snapshot, appended)
    try:
        require_current(work)
        work.path.unlink()
        if work.path.exists():
            raise OSError(f"Completed work still exists after removal: {work.path}")
    except (OSError, ValueError) as error:
        return _pending(work, history_path, "pending-removal", str(error), identity,
                        title, completed, verified.snapshot, appended)
    return {"status": "ok", "complete": True, "archived": True, "id": identity,
            "title": title, "completed": completed, "work_version": work.version,
            "history_version": verified.snapshot.version, "history_appended": appended,
            "work_path": str(work.path), "history_path": str(history_path),
            "work_present": False, "history_present": True, "pending": []}
