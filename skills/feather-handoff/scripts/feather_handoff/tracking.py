"""Respect existing Git tracking choices when recording handoffs."""
import subprocess

from .storage import HandoffError, Store, check_path, create_file, read_file, replace_file, git_environment


RULE = "/.feather/handoffs/"


def git(store: Store, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", f"safe.directory={store.project.as_posix()}", "-C",
                           str(store.project), *arguments], capture_output=True, text=True,
                          encoding="utf-8", timeout=5, env=git_environment())


def ensure_tracking(store: Store, work: str, choice: str) -> str:
    try:
        if git(store, "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
            return "non-git"
    except (OSError, subprocess.TimeoutExpired):
        return "not-checked"
    relative = f".feather/handoffs/{work}"
    path = store.project / ".gitignore"
    check_path(path)
    original = read_file(path) if path.exists() else None
    content = original.data.decode("utf-8") if original else ""
    if choice == "track":
        changed = "".join(line for line in content.splitlines(keepends=True) if line.strip() != RULE)
        if original and changed != content:
            replace_file(original, changed.encode("utf-8"))
        ignored = git(store, "check-ignore", "-q", "--", relative)
        if ignored.returncode == 0:
            raise HandoffError("tracking-blocked", f"Work saved, but broader Git rules still ignore {relative}; user decision needed")
        if ignored.returncode not in {0, 1}:
            raise HandoffError("git", ignored.stderr.strip())
        return "track"
    tracked = git(store, "ls-files", "--", ".feather/handoffs/")
    if tracked.returncode:
        raise HandoffError("git", tracked.stderr.strip())
    if tracked.stdout.strip():
        return "existing-tracking"
    ignored = git(store, "check-ignore", "-v", "--", relative)
    if ignored.returncode not in {0, 1}:
        raise HandoffError("git", ignored.stderr.strip())
    if ignored.stdout.strip():
        # Verbose check-ignore also reports a matching explicit unignore rule.
        return "existing-rule"
    newline = "\r\n" if "\r\n" in content else "\n"
    changed = content + (newline if content and not content.endswith("\n") else "") + RULE + newline
    if original:
        replace_file(original, changed.encode("utf-8"))
    else:
        create_file(path, changed.encode("utf-8"))
    return "ignored"
