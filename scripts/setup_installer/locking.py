"""Serialize overlapping installer writes; OS locks release when the process exits."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
import sys


@contextmanager
def destinations(paths: list[Path]):
    # Persistent empty lock files avoid unlink/recreate races between waiting installers.
    from .transaction import validate_regular

    namespace = str(os.getuid()) if hasattr(os, "getuid") else hashlib.sha256(str(Path.home()).encode()).hexdigest()[:16]
    root = Path(tempfile.gettempdir()) / f"feather-setup-locks-{namespace}"
    validate_regular(root / "guard")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    handles = []
    try:
        for name in sorted({hashlib.sha256(os.path.normcase(str(path.absolute())).encode()).hexdigest() for path in paths}):
            lock = root / name
            validate_regular(lock)
            stream = lock.open("a+b")
            handles.append(stream)
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            try:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError("Another feather-setup operation is writing overlapping destinations; retry after it finishes") from error
        yield
    finally:
        for stream in reversed(handles):
            stream.close()
