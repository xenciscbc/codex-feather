"""Versioned operations on explicitly selected complete history entries."""
from .history import HistoryDocument, HistoryEntry, parse_history
from .storage import HandoffError, Store, check_path, create_file, legal_name, read_file, replace_file, require_current
from .writing import input_object


def history_path(store: Store, source: object):
    if source == "history.md":
        path = store.directory / "history.md"
    elif isinstance(source, str) and source.startswith("archive/"):
        name = source[len("archive/"):]
        legal_name(name)
        if not name.lower().endswith(".md"):
            raise HandoffError("scope", "Sealed source must be Markdown")
        path = store.directory / "archive" / name
    else:
        raise HandoffError("scope", "Source must be history.md or explicit archive/<batch>.md")
    check_path(path)
    return path


def selection(document: HistoryDocument, raw: object) -> list[HistoryEntry]:
    if (not isinstance(raw, list) or not raw or
            any(not isinstance(item, str) for item in raw) or len(set(raw)) != len(raw)):
        raise HandoffError("selection", "ids must be a nonempty list of distinct queried identities")
    if document.issues or any(not e.boundary_known for e in document.entries):
        raise HandoffError("format", "Uncertain history boundaries; preserve and clarify before mutation")
    entries = [entry for entry in document.entries if entry.identity in raw]
    if len(entries) != len(raw) or len({e.identity for e in entries}) != len(raw):
        raise HandoffError("selection", "Selected identities missing or ambiguous; reread without expanding scope")
    return entries


def remainder(document: HistoryDocument, entries: list[HistoryEntry]) -> bytes:
    data = document.snapshot.data
    for entry in sorted(entries, key=lambda item: item.byte_start, reverse=True):
        data = data[:entry.byte_start] + data[entry.byte_end:]
    return data


def clear_history(store: Store, raw: object) -> dict:
    payload = input_object(raw)
    if set(payload) - {"source", "version", "ids"}:
        raise HandoffError("input", "Unknown clear options")
    source = payload.get("source", "history.md")
    original = read_file(history_path(store, source))
    if payload.get("version") != original.version:
        raise HandoffError("conflict", "History changed or version missing; query and reconcile original selection")
    document = parse_history(original)
    entries = selection(document, payload.get("ids"))
    expected = remainder(document, entries)
    try:
        saved = replace_file(original, expected)
    except (OSError, ValueError) as error:
        observed = None
        try:
            observed = read_file(original.path)
        except (OSError, ValueError):
            pass
        state = ("unreadable" if observed is None else "unchanged" if observed.data == original.data
                 else "selection-removed" if observed.data == expected else "changed")
        return {"status": "partial", "complete": False, "code": getattr(error, "code", "clear-failed"),
                "message": str(error), "source": source, "source_path": str(original.path), "state": state,
                "source_version": observed.version if observed else None, "ids": payload["ids"],
                "recovery": "Preserve the source; query and reconcile these exact identities before retrying"}
    return {"status": "ok", "complete": True, "source": source,
            "removed": [e.identity for e in entries], "version": saved.version}


def check_pending(store: Store, entries: list[HistoryEntry]) -> None:
    from .archiving import work_body
    from .records import summary
    paths = store.work_paths()
    snapshots = []
    for path in paths:
        try:
            snapshot = read_file(path)
            item = summary(snapshot)
            if item["problems"]:
                raise HandoffError("pending-archive", f"Cannot exclude unfinished archival for {path}")
            snapshots.append(snapshot)
            for entry in entries:
                if (item["status"] == "完成" and item["title"] == entry.title
                        and item["updated"] == entry.completed):
                    body = work_body(snapshot, item["title"])
                    if entry.body_bytes not in (body, body + b"\n"):
                        raise HandoffError("conflict", f"Completed work and history differ: {path}")
                    raise HandoffError("pending-archive", f"Retry archival before sealing: {path}")
        except (OSError, UnicodeError) as error:
            raise HandoffError("pending-archive", f"Cannot exclude unfinished archival for {path}: {error}") from error
    if paths != store.work_paths():
        raise HandoffError("pending-archive", "Work directory changed; repeat pending archival check")
    for snapshot in snapshots:
        require_current(snapshot)


def seal_history(store: Store, raw: object) -> dict:
    payload = input_object(raw)
    if set(payload) - {"version", "ids", "destination", "destination_version"}:
        raise HandoffError("input", "Unknown seal options")
    name = payload.get("destination")
    if not isinstance(name, str):
        raise HandoffError("input", "destination must be a legal Markdown basename")
    destination = history_path(store, "archive/" + name)
    original = read_file(history_path(store, "history.md"))
    if payload.get("version") != original.version:
        raise HandoffError("conflict", "History changed; query and reconcile the original selection")
    document = parse_history(original)
    existing = read_file(destination) if destination.exists() else None
    if "destination_version" in payload:
        if existing is None or payload["destination_version"] != existing.version:
            raise HandoffError("conflict", "Retry destination missing or changed")
        target_document = parse_history(existing)
        target_entries = selection(target_document, payload.get("ids"))
        if len(target_entries) != len(target_document.entries):
            raise HandoffError("selection", "Retry must identify every entry in the original destination")
        # Missing source entries may already have moved. Never substitute another identity.
        remaining_ids = [e.identity for e in document.entries if e.identity in payload["ids"]]
        if document.issues:
            raise HandoffError("format", "Uncertain source boundaries; preserve retry copies")
        entries = selection(document, remaining_ids) if remaining_ids else []
        by_id = {e.identity: e for e in target_entries}
        if any(e.content_bytes != by_id[e.identity].content_bytes for e in entries):
            raise HandoffError("conflict", "Source differs from retry destination")
        candidate = existing.data
    else:
        entries = selection(document, payload.get("ids"))
        target_entries = entries
        candidate = "# 交接歷史\n\n".encode("utf-8") + b"".join(e.content_bytes for e in entries)
        if existing is not None and existing.data != candidate:
            raise HandoffError("conflict", f"Different destination preserved: {destination}")
    check_pending(store, target_entries)
    saved = existing
    try:
        if saved is None:
            saved = create_file(destination, candidate)
        require_current(saved)
        if read_file(destination).data != candidate:
            raise HandoffError("conflict", "Destination verification failed")
        check_pending(store, target_entries)
        source = replace_file(original, remainder(document, entries))
        require_current(saved)
        require_current(source)
    except (OSError, ValueError) as error:
        return {"status": "partial", "complete": False, "code": getattr(error, "code", "seal-failed"),
                "message": str(error), "source": "history.md", "destination": str(destination),
                "destination_version": saved.version if saved else None,
                "ids": payload["ids"], "recovery": "Preserve copies; query source version and retry the same destination and identities"}
    return {"status": "ok", "complete": True, "source": "history.md", "version": source.version,
            "destination": str(destination), "destination_version": saved.version,
            "sealed": [e.identity for e in target_entries]}
