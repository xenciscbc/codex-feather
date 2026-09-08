"""Present user edits as reviewable differences without guessing ownership."""
import difflib
from pathlib import Path
from typing import Any


class ConflictError(ValueError):
    def __init__(self, path: Path, expected: bytes | None, current: bytes | None,
                 proposed: bytes | None, owned: bool = True):
        def difference(left, right, before, after):
            return "".join(difflib.unified_diff((left or b"").decode("utf-8", "replace").splitlines(True),
                                               (right or b"").decode("utf-8", "replace").splitlines(True),
                                               fromfile=before, tofile=after))
        super().__init__(f"Conflict: {path}; {'managed content was modified' if owned else 'content is not owned by Feather'}")
        self.details: dict[str, Any] = {"error": str(self), "status": "preserved", "conflicts": [{
            "path": str(path), "owned": owned,
            "local_diff": difference(expected, current, "last-installed", "current"),
            "proposed_diff": difference(current, proposed, "current", "proposed")}],
            "next_step": ("Keep the current files, or review the differences and retry with --on-conflict replace; "
                          "replacement saves a transaction backup." if owned else
                          "Move or rename the unowned content yourself, or choose another scope. It cannot be force-adopted.")}
