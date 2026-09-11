"""Read-only Python runtime discovery for the handoff tool."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


PYTHON_MINIMUM = (3, 11)


def inspect_python() -> dict:
    """Find a PATH Python without assuming the installer executable is one."""
    incompatible = []
    for command in ("python", "python3", "py"):
        found = shutil.which(command)
        if not found:
            continue
        path = Path(found).resolve()
        if ((os.name == "nt" and "microsoft\\windowsapps" in str(path).casefold())
                or (getattr(sys, "frozen", False) and path == Path(sys.executable).resolve())):
            continue
        try:
            probe = subprocess.run([str(path), *(["-3"] if command == "py" else []), "--version"], stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            continue
        match = re.search(r"\bPython\s+(\d+)\.(\d+)(?:\.(\d+))?\b", probe.stdout + "\n" + probe.stderr)
        if probe.returncode != 0 or not match:
            continue
        version = tuple(map(int, match.groups(default="0")))
        detail = {"command": command, "arguments": ["-3"] if command == "py" else [], "path": str(path), "version": match.group(0)[7:]}
        if version[:2] >= PYTHON_MINIMUM:
            return {"status": "available", **detail}
        incompatible.append((version, detail))
    if incompatible:
        _, detail = max(incompatible, key=lambda item: item[0])
        return {"status": "incompatible", **detail,
                "message": "Python 3.11 or newer is required; Feather does not install it automatically."}
    return {"status": "missing", "message": "Python 3.11 or newer was not found on PATH; Feather does not install it automatically."}
