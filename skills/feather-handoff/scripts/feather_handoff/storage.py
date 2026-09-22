"""Project containment and content snapshots shared by public operations."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import secrets


class HandoffError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def git_environment() -> dict[str, str]:
    """Keep a parent Git process from redirecting the explicitly selected project."""
    environment = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE"):
        environment.pop(key, None)
    environment.update(GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    return environment


def check_path(path: Path) -> None:
    """Check existing ancestors before following any target, including junctions."""
    for part in reversed([path, *path.parents]):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise HandoffError("unsafe-path", f"Link/reparse path is not supported: {part}")
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise HandoffError("unsafe-path", f"Ancestor is not a directory: {part}")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise HandoffError("unsafe-path", f"Hard-linked file is not supported: {part}")


def project_root(value: str) -> Path:
    path = Path(os.path.abspath(value))
    check_path(path)
    if not path.is_dir():
        raise HandoffError("project", f"Project directory does not exist: {path}")
    try:
        result = subprocess.run(
            ["git", "-C", str(path),
             "rev-parse", "--show-toplevel"], capture_output=True, text=True,
            encoding="utf-8", timeout=5, env=git_environment(),
        )
        if result.returncode == 0:
            path = Path(result.stdout.strip())
            check_path(path)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return path.resolve()


def legal_name(name: str) -> None:
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)),
                *(f"LPT{n}" for n in range(1, 10))}
    if (not name or name in {".", ".."} or name.rstrip(" .") != name
            or any(c in name for c in '/\\:<>"|?*') or any(ord(c) < 32 for c in name)
            or name.split(".")[0].upper() in reserved):
        raise HandoffError("unsafe-name", f"Invalid filename: {name!r}")


@dataclass(frozen=True)
class Snapshot:
    path: Path
    data: bytes

    @property
    def version(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def text(self) -> str:
        return self.data.decode("utf-8-sig")


def read_file(path: Path) -> Snapshot:
    check_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise HandoffError("not-file", f"Not a regular file: {path}")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise HandoffError("changed", f"File changed while opening: {path}")
        data = handle.read()
        after_read = os.fstat(handle.fileno())
    check_path(path)
    after = path.stat()
    signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if signature(before) != signature(after_read) or signature(before) != signature(after):
        raise HandoffError("changed", f"File changed during read: {path}")
    return Snapshot(path, data)


def create_file(path: Path, data: bytes) -> Snapshot:
    check_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    check_path(path)
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise HandoffError("exists", f"Existing data preserved: {path}") from None
    saved = read_file(path)
    if saved.data != data:
        raise HandoffError("changed", f"Saved file differs; preserve and inspect {path}")
    return saved


def require_current(snapshot: Snapshot) -> None:
    if read_file(snapshot.path).version != snapshot.version:
        raise HandoffError("conflict", f"Source changed; reread before writing: {snapshot.path}")


def replace_file(snapshot: Snapshot, data: bytes) -> Snapshot:
    require_current(snapshot)
    if data == snapshot.data:
        return snapshot
    temporary: Path | None = None
    try:
        # Windows tempfile may retry PermissionError up to TMP_MAX even when a
        # sandbox denies writes. Only actual name collisions warrant a retry.
        for _ in range(3):
            candidate = snapshot.path.parent / f".feather-{secrets.token_hex(16)}.tmp"
            try:
                descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
            except FileExistsError:
                continue
            temporary = candidate
            break
        else:
            raise HandoffError("temporary-conflict", "Temporary name collisions; source preserved, retry later")
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(snapshot.path.stat().st_mode))
        require_current(snapshot)
        os.replace(temporary, snapshot.path)
        temporary = None
        saved = read_file(snapshot.path)
        if saved.data != data:
            raise HandoffError("changed", f"Saved file differs; preserve and inspect {snapshot.path}")
        return saved
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Store:
    def __init__(self, project: str):
        self.project = project_root(project)
        self.directory = self.project / ".feather" / "handoffs"
        check_path(self.directory)

    def work_path(self, name: str) -> Path:
        legal_name(name)
        if not name.lower().endswith(".md") or name.lower() == "history.md":
            raise HandoffError("unsafe-name", "Work must be a direct Markdown file other than history.md")
        path = self.directory / name
        check_path(path)
        return path

    def work_paths(self) -> list[Path]:
        check_path(self.directory)
        if not self.directory.exists():
            return []
        if not self.directory.is_dir():
            raise HandoffError("not-directory", f"Not a handoff directory: {self.directory}")
        return sorted((p for p in self.directory.iterdir()
                       if p.suffix.lower() == ".md" and p.name.lower() != "history.md"),
                      key=lambda p: p.name)
