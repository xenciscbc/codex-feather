"""Read shared and explicitly selected sealed history without modifying it."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
import hashlib
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .storage import Snapshot, Store, check_path, read_file, require_current


HEADING = re.compile(r"(?m)^##[ \t]+([^\r\n]+)\r?$")
MODERN = re.compile(r"^(.+) · 完成[：:](.+)$")
LEGACY_COMPLETED = re.compile(r"^(?:[ \t]*\r?\n)?完成[：:][ \t]*([^\r\n]+)\r?$", re.MULTILINE)
LEGACY_STATUS = re.compile(r"^(?:[ \t]*\r?\n)?狀態[：:][ \t]*完成[ \t]*\r?$", re.MULTILINE)


@dataclass(frozen=True)
class HistoryEntry:
    title: str
    completed: str | None
    source: str
    body: str
    content: str
    identity: str
    document_version: str
    start: int
    end: int
    body_start: int
    byte_start: int
    byte_end: int
    byte_body_start: int
    content_bytes: bytes
    body_bytes: bytes
    boundary_known: bool
    problems: tuple[str, ...]

    def public(self) -> dict:
        return {"title": self.title, "completed": self.completed, "source": self.source,
                "body": self.body, "content": self.content, "id": self.identity,
                "document_version": self.document_version,
                "boundary_known": self.boundary_known, "problems": list(self.problems)}


@dataclass(frozen=True)
class HistoryDocument:
    snapshot: Snapshot
    source: str
    entries: tuple[HistoryEntry, ...]
    issues: tuple[dict, ...]


@dataclass(frozen=True)
class _Start:
    start: int
    body_start: int
    title: str
    completed: str | None
    boundary_known: bool


def _body_start(text: str, heading_end: int) -> int:
    return heading_end + 1 if text[heading_end:heading_end + 1] == "\n" else heading_end


def _byte_offset(text: str, character_offset: int, bom: int) -> int:
    return bom + len(text[:character_offset].encode("utf-8"))


def _completion(value: str | None) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, "Legacy entry has no completion identity"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, "Invalid completion timestamp"
    if parsed.utcoffset() is None:
        return parsed, "Completion timestamp has no timezone; date conversion is ambiguous"
    return parsed, None


def parse_history(snapshot: Snapshot, source: str | None = None) -> HistoryDocument:
    """Parse exact entry spans; uncertain legacy boundaries are explicitly marked."""
    text = snapshot.text
    source = source or snapshot.path.name
    reliable = []
    legacy_status = []
    for heading in HEADING.finditer(text):
        label = heading.group(1).strip()
        body_start = _body_start(text, heading.end())
        modern = MODERN.fullmatch(label)
        if modern:
            reliable.append(_Start(heading.start(), body_start, modern.group(1).strip(),
                                   modern.group(2).strip(), True))
            continue
        completed = LEGACY_COMPLETED.match(text[body_start:])
        if completed:
            reliable.append(_Start(heading.start(), body_start, label,
                                   completed.group(1).strip(), True))
        elif LEGACY_STATUS.match(text[body_start:]):
            legacy_status.append(_Start(heading.start(), body_start, label, None, False))

    starts = sorted([*reliable, *legacy_status] if reliable else legacy_status,
                    key=lambda item: item.start)
    issues = []
    if starts:
        prefix = text[:starts[0].start]
        if not re.fullmatch(r"\s*(?:#[^\r\n]*(?:\r?\n|$))?\s*", prefix):
            issues.append({"source": source, "code": "boundary",
                           "message": "Content before the first recognizable history entry has unknown boundaries"})
    elif not re.fullmatch(r"\s*(?:#[^\r\n]*(?:\r?\n|$))?\s*", text):
        issues.append({"source": source, "code": "format",
                       "message": "No recognizable history entry boundaries"})

    bom = 3 if snapshot.data.startswith(b"\xef\xbb\xbf") else 0
    entries = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start if index + 1 < len(starts) else len(text)
        _, problem = _completion(start.completed)
        problems = []
        uncertain = [candidate.title for candidate in legacy_status
                     if reliable and start.start < candidate.start <= end]
        boundary_known = start.boundary_known and not uncertain
        if not start.boundary_known:
            problems.append("Legacy status-only entry has ambiguous boundaries")
        if uncertain:
            problems.append("Possible legacy entry boundary inside this record: " + ", ".join(uncertain))
        if problem:
            problems.append(problem)
        identity_material = (f"feather-history-v1\0{start.title}\0{start.completed}"
                             if start.completed is not None else
                             f"feather-history-ambiguous-v1\0{source}\0{start.start}\0{text[start.start:end]}")
        identity = hashlib.sha256(identity_material.encode("utf-8")).hexdigest()
        byte_start = _byte_offset(text, start.start, bom)
        byte_body_start = _byte_offset(text, start.body_start, bom)
        byte_end = _byte_offset(text, end, bom)
        entry = HistoryEntry(
            title=start.title, completed=start.completed, source=source,
            body=text[start.body_start:end], content=text[start.start:end], identity=identity,
            document_version=snapshot.version, start=start.start, end=end,
            body_start=start.body_start, byte_start=byte_start, byte_end=byte_end,
            byte_body_start=byte_body_start, content_bytes=snapshot.data[byte_start:byte_end],
            body_bytes=snapshot.data[byte_body_start:byte_end], boundary_known=boundary_known,
            problems=tuple(problems),
        )
        entries.append(entry)
        for message in problems:
            issues.append({"source": source, "id": identity, "code": "format", "message": message})
    return HistoryDocument(snapshot, source, tuple(entries), tuple(issues))


def _zone(value: str) -> tzinfo:
    if value == "UTC":
        return timezone.utc
    offset = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if offset:
        hours, minutes = int(offset.group(2)), int(offset.group(3))
        if hours > 23 or minutes > 59:
            raise ValueError(f"Unsupported timezone offset: {value}")
        delta = timedelta(hours=hours, minutes=minutes)
        return timezone(delta if offset.group(1) == "+" else -delta)
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"Unsupported timezone {value!r}; use UTC, ±HH:MM, or an available IANA zone") from error


def _date(value: str | None, name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Invalid {name}: {value!r}; expected YYYY-MM-DD") from error


def _matches(entry: HistoryEntry, work: str | None, date_from: date | None,
             date_to: date | None, keyword: str | None, zone: tzinfo) -> bool:
    if work is not None and entry.title.casefold() != work.casefold():
        return False
    if keyword is not None and keyword.casefold() not in entry.content.casefold():
        return False
    if date_from is not None or date_to is not None:
        completed, _ = _completion(entry.completed)
        if completed is None:
            return False
        local_date = (completed.astimezone(zone).date() if completed.utcoffset() is not None
                      else completed.date())
        if date_from is not None and local_date < date_from:
            return False
        if date_to is not None and local_date > date_to:
            return False
    return True


def query_history(store: Store, work: str | None = None, date_from: str | None = None,
                  date_to: str | None = None, keyword: str | None = None,
                  timezone: str = "UTC", include_sealed: bool = False) -> dict:
    try:
        zone = _zone(timezone)
        lower = _date(date_from, "from-date")
        upper = _date(date_to, "to-date")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("from-date must not be later than to-date")
    except ValueError as error:
        return {"status": "error", "complete": False, "timezone": timezone,
                "entries": [], "issues": [], "code": "query", "message": str(error)}

    sources: list[tuple[Path, str]] = []
    issues = []
    available = False
    history = store.directory / "history.md"
    try:
        check_path(history)
        if history.exists():
            available = True
            sources.append((history, "history.md"))
    except (OSError, ValueError) as error:
        issues.append({"source": "history.md", "code": getattr(error, "code", "io"), "message": str(error)})

    if include_sealed:
        archive = store.directory / "archive"
        try:
            check_path(archive)
            if archive.exists():
                if not archive.is_dir():
                    raise ValueError(f"Not an archive directory: {archive}")
                paths = sorted((path for path in archive.iterdir() if path.suffix.lower() == ".md"),
                               key=lambda path: path.name)
                available = True
                sources.extend((path, f"archive/{path.name}") for path in paths)
        except (OSError, ValueError) as error:
            issues.append({"source": "archive", "code": getattr(error, "code", "io"), "message": str(error)})

    entries: list[dict] = []
    documents = []
    snapshots = []
    for path, source in sources:
        try:
            document = parse_history(read_file(path), source)
            snapshots.append(document.snapshot)
            documents.append({"source": source, "version": document.snapshot.version})
            issues.extend(document.issues)
            entries.extend(entry.public() for entry in document.entries
                           if _matches(entry, work, lower, upper, keyword, zone))
        except (OSError, UnicodeError, ValueError) as error:
            issues.append({"source": source, "code": getattr(error, "code", "io"), "message": str(error)})

    for snapshot in snapshots:
        try:
            require_current(snapshot)
        except (OSError, ValueError) as error:
            issues.append({"source": str(snapshot.path), "code": "changed", "message": str(error)})

    status = "partial" if issues else ("ok" if available else "missing")
    return {"status": status, "complete": not issues, "timezone": timezone,
            "entries": entries, "issues": issues, "documents": documents}
