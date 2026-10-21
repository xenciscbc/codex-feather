"""Respect existing Git tracking choices when recording handoffs."""
import subprocess

from .storage import (HandoffError, Store, check_path, create_file, lazy_fetch_guard, read_file, replace_file,
                      run_git)


RULE = "/.feather/handoffs/"
# A Git comment: records an explicit track choice without unignoring anything.
MARKER = "# cc-feather: track /.feather/handoffs/"


def rule_line(line: str) -> str:
    """A .gitignore line as Git reads it: leading whitespace is part of the pattern, trailing spaces are not."""
    return line.rstrip("\r\n").rstrip(" ")


def git(store: Store, *arguments: str, no_lazy_fetch: bool = False) -> subprocess.CompletedProcess:
    return run_git(store.project, *arguments, no_lazy_fetch=no_lazy_fetch)


def object_reads(store: Store) -> bool:
    """The promisor-remote check before the first command that can read objects and before any write to the rules.

    Returns whether those commands carry --no-lazy-fetch; raises promisor-remote or promisor-unknown when none may
    run, and git-unavailable when Git could not be run, like the first probe."""
    try:
        return lazy_fetch_guard(store.project)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HandoffError("git-unavailable", f"Git could not be run or did not respond: {error}") from None


def ensure_tracking(store: Store, work: str, choice: str) -> str:
    try:
        probe = git(store, "rev-parse", "--is-inside-work-tree")
    except (OSError, subprocess.TimeoutExpired) as error:
        # Without a Git answer the ignore rule cannot be applied; the save reports a partial tracking failure.
        raise HandoffError("git-unavailable", f"Git could not be run or did not respond: {error}") from None
    if probe.returncode and "not a git repository" not in probe.stderr.lower():
        raise HandoffError("git", probe.stderr.strip() or "Git tracking could not be checked")
    if probe.stdout.strip() != "true":
        return "non-git"
    relative = f".feather/handoffs/{work}"
    path = store.project / ".gitignore"
    check_path(path)
    original = read_file(path) if path.exists() else None
    content = original.data.decode("utf-8") if original else ""
    newline = "\r\n" if "\r\n" in content else "\n"
    marked = any(rule_line(line) == MARKER for line in content.splitlines())
    if choice == "default" and marked:
        # Reads no object and writes nothing, so it needs no promisor-remote check.
        return "existing-rule"
    lazy = object_reads(store)
    if choice == "track":
        changed = "".join(line for line in content.splitlines(keepends=True) if rule_line(line) != RULE)
        if not marked:
            changed += (newline if changed and not changed.endswith("\n") else "") + MARKER + newline
        if changed != content:
            if original:
                replace_file(original, changed.encode("utf-8"))
            else:
                create_file(path, changed.encode("utf-8"))
        ignored = git(store, "check-ignore", "-q", "--", relative, no_lazy_fetch=lazy)
        if ignored.returncode == 0:
            raise HandoffError("tracking-blocked", f"Work saved, but broader Git rules still ignore {relative}; user decision needed")
        if ignored.returncode not in {0, 1}:
            raise HandoffError("git", ignored.stderr.strip())
        return "track"
    tracked = git(store, "ls-files", "--", ".feather/handoffs/", no_lazy_fetch=lazy)
    if tracked.returncode:
        raise HandoffError("git", tracked.stderr.strip())
    if tracked.stdout.strip():
        return "existing-tracking"
    ignored = git(store, "check-ignore", "-v", "--", relative, no_lazy_fetch=lazy)
    if ignored.returncode not in {0, 1}:
        raise HandoffError("git", ignored.stderr.strip())
    if ignored.stdout.strip():
        # Verbose check-ignore also reports a matching explicit unignore rule.
        return "existing-rule"
    changed = content + (newline if content and not content.endswith("\n") else "") + RULE + newline
    if original:
        replace_file(original, changed.encode("utf-8"))
    else:
        create_file(path, changed.encode("utf-8"))
    return "ignored"
