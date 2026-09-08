"""Plan filesystem changes before applying any installation writes."""
from dataclasses import dataclass
import json
import hashlib
import os
from pathlib import Path
import stat
import tempfile
from typing import Any
import uuid
from .locking import destinations


def validate_regular(path: Path) -> bool:
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise ValueError(f"Refusing linked installation destination: {part}")
        if not part.exists():
            continue
        info = part.stat()
        if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise ValueError(f"Refusing reparse-point destination: {part}")
        if part != path and not part.is_dir():
            raise ValueError(f"Destination parent is not a directory: {part}")
    if not path.exists():
        return False
    if not path.is_file() or path.stat().st_nlink > 1:
        raise ValueError(f"Destination is not an independent regular file: {path}")
    return True


def read_regular(path: Path) -> bytes | None:
    return path.read_bytes() if validate_regular(path) else None


@dataclass(frozen=True)
class Change:
    path: Path
    before: bytes | None
    after: bytes | None
    mode: int


class TransactionError(OSError):
    def __init__(self, cause: BaseException, backup: Path, remaining: list[dict]):
        super().__init__(str(cause))
        self.details = {"error": str(cause), "backup": str(backup),
                        "recovery": "incomplete" if remaining else "rolled_back", "remaining": remaining,
                        "next_step": "Inspect journal.json and the original-content backups before retrying."}


def atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".feather-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Plan:
    def __init__(self):
        self.changes: list[Change] = []
        self.baselines: dict[Path, tuple[bytes | None, int]] = {}

    def _baseline(self, path: Path) -> tuple[bytes | None, int]:
        if path not in self.baselines:
            before = read_regular(path)
            mode = stat.S_IMODE(path.stat().st_mode) if before is not None else 0o600
            self.baselines[path] = (before, mode)
        return self.baselines[path]

    def add(self, path: Path, content: bytes | None) -> None:
        self.changes = [change for change in self.changes if change.path != path]
        before, mode = self._baseline(path)
        if before != content:
            self.changes.append(Change(path, before, content, mode))

    def read(self, path: Path) -> bytes | None:
        for change in self.changes:
            if change.path == path:
                return change.after
        return self._baseline(path)[0]

    def summary(self) -> list[dict]:
        return [{"path": str(change.path), "action": "remove" if change.after is None else "write"}
                for change in self.changes]

    def fingerprint(self) -> str:
        snapshot = [{"path": str(change.path), "mode": change.mode,
                     "before": hashlib.sha256(change.before).hexdigest() if change.before is not None else None,
                     "after": hashlib.sha256(change.after).hexdigest() if change.after is not None else None}
                    for change in self.changes]
        return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()

    def require_preview(self, expected: str | None) -> None:
        if expected is not None and self.fingerprint() != expected:
            raise ValueError("The operation changed after preview. No changes were applied; preview again before confirming.")

    def apply(self, backup_root: Path) -> Path | None:
        if not self.changes:
            return None
        with destinations([change.path for change in self.changes]):
            return self._apply_locked(backup_root)

    def _apply_locked(self, backup_root: Path) -> Path:
        for change in self.changes:
            if read_regular(change.path) != change.before:
                raise ValueError(f"Changed since preview: {change.path}")
        backup = backup_root / uuid.uuid4().hex
        journal_path = backup / "journal.json"
        read_regular(journal_path)
        backup.mkdir(parents=True, mode=0o700)
        journal: dict[str, Any] = {"format": 1, "phase": "prepared", "changes": []}
        for index, change in enumerate(self.changes):
            saved = f"{index:04}.bin" if change.before is not None else None
            if saved is not None and change.before is not None:
                atomic_write(backup / saved, change.before)
            journal["changes"].append({"path": str(change.path), "before": saved, "mode": change.mode})
        atomic_write(journal_path, (json.dumps(journal, indent=2) + "\n").encode())
        applied: list[Change] = []
        created: list[Path] = []
        try:
            for change in self.changes:
                if read_regular(change.path) != change.before:
                    raise ValueError(f"Changed during installation: {change.path}")
                absent = []
                parent = change.path.parent
                while not parent.exists():
                    absent.append(parent)
                    parent = parent.parent
                for directory in reversed(absent):
                    directory.mkdir(mode=0o700)
                    created.append(directory)
                if change.after is None:
                    change.path.unlink()
                else:
                    atomic_write(change.path, change.after, change.mode)
                applied.append(change)
                if read_regular(change.path) != change.after:
                    raise OSError(f"Written destination could not be verified: {change.path}")
            journal["phase"] = "committed"
            atomic_write(journal_path, (json.dumps(journal, indent=2) + "\n").encode())
            return backup
        except (Exception, KeyboardInterrupt) as cause:
            remaining = []
            for change in reversed(applied):
                try:
                    if read_regular(change.path) != change.after:
                        raise ValueError("Content changed after write; refusing to overwrite concurrent changes")
                    if change.before is None:
                        change.path.unlink()
                    else:
                        atomic_write(change.path, change.before, change.mode)
                except (OSError, ValueError) as error:
                    remaining.append({"path": str(change.path), "error": str(error)})
            for directory in reversed(created):
                try:
                    directory.rmdir()
                except OSError:
                    pass  # Keep nonempty directories, including any recoverable content.
            journal["phase"] = "recovery_required" if remaining else "rolled_back"
            journal["remaining"] = remaining
            try:
                atomic_write(journal_path, (json.dumps(journal, indent=2) + "\n").encode())
            except OSError as error:
                remaining.append({"path": str(journal_path), "error": str(error)})
            raise TransactionError(cause, backup, remaining) from cause
