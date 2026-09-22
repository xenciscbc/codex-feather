"""Bounded read-only observations of explicitly selected project sources."""
from datetime import datetime
import hashlib
import os
from pathlib import Path
import stat
import subprocess

from . import baseline
from .storage import HandoffError, Store, check_path, read_file, git_environment


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def source_info(project: Path, name: str):
    path = project / baseline.source_name(name)
    check_path(path)
    # Ancestors were checked before resolving, so a missing leaf is not a link.
    if not path.resolve().is_relative_to(project):
        raise HandoffError("unsafe-path", "Source escapes project")
    try:
        info = path.stat()
    except FileNotFoundError:
        return path, None
    if not stat.S_ISREG(info.st_mode):
        raise HandoffError("not-file", "Source is not a regular file")
    return path, info


def unknown(name: str, reason: str) -> dict:
    return {"path": name, "state": "unknown", "reason": reason}


def observe(project: Path, name: str, budget: list[int]):
    for attempt in range(2):
        try:
            path, before = source_info(project, name)
            if before is None:
                return {"path": name, "state": "missing"}, None
            if before.st_size > baseline.MAX_FILE_BYTES:
                return unknown(name, "file-limit"), None
            if before.st_size > budget[0]:
                return unknown(name, "total-limit"), None
            digest = hashlib.sha256()
            count = 0
            with path.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                if signature(before) != signature(opened):
                    raise HandoffError("changed", "Source changed while opening")
                while count < before.st_size:
                    chunk = handle.read(min(1024 * 1024, before.st_size - count))
                    if not chunk:
                        break
                    budget[0] -= len(chunk)
                    count += len(chunk)
                    digest.update(chunk)
                after_read = os.fstat(handle.fileno())
            _, after = source_info(project, name)
            if (after is None or count != before.st_size or signature(before) != signature(after_read)
                    or signature(before) != signature(after)):
                raise HandoffError("changed", "Source changed during read")
            return {"path": name, "state": "present", "sha256": digest.hexdigest()}, signature(after)
        except (OSError, ValueError) as error:
            reason = getattr(error, "code", "unreadable")
            if reason == "changed" and attempt == 0:
                continue
            return unknown(name, reason), None


def git_observation(project: Path) -> dict:
    env = git_environment()

    def run(*args):
        return subprocess.run(["git", "-C", str(project), *args], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=5, env=env)

    try:
        probe = run("rev-parse", "--is-inside-work-tree")
        if probe.returncode:
            if "not a git repository" in probe.stderr.lower():
                return {"state": "not-repository"}
            return {"state": "unknown", "reason": "git-error"}
        if probe.stdout.strip() != "true":
            return {"state": "unknown", "reason": "not-worktree"}
        branch = run("symbolic-ref", "--quiet", "HEAD")
        if branch.returncode not in (0, 1):
            return {"state": "unknown", "reason": "git-error"}
        head = run("rev-parse", "--verify", "--quiet", "HEAD")
        if head.returncode:
            if head.returncode != 1 or branch.returncode != 0:
                return {"state": "unknown", "reason": "git-error"}
            unborn = run("show-ref", "--verify", "--quiet", branch.stdout.strip())
            if unborn.returncode != 1:
                return {"state": "unknown", "reason": "git-error"}
        return {"state": "available", "head": head.stdout.strip() if head.returncode == 0 else None,
                "branch": branch.stdout.strip().removeprefix("refs/heads/") if branch.returncode == 0 else None}
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "unknown", "reason": "git-unavailable"}


def capture(store: Store, payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"paths"}:
        raise HandoffError("snapshot-input", "Expected JSON {paths: [...]}")
    paths = baseline.paths_input(payload["paths"])
    git_before = git_observation(store.project)
    budget = [baseline.MAX_TOTAL_BYTES]
    observed = [observe(store.project, name, budget) for name in paths]
    files = [item for item, _ in observed]
    identities = {}
    for index, (item, saved_signature) in enumerate(observed):
        if item["state"] == "unknown":
            continue
        try:
            _, current = source_info(store.project, item["path"])
            current_signature = signature(current) if current else None
            if current_signature != saved_signature:
                files[index] = unknown(item["path"], "changed")
            if current_signature:
                identity = current_signature[:2]
                if identity in identities:
                    previous = identities[identity]
                    files[previous] = unknown(files[previous]["path"], "duplicate-source")
                    files[index] = unknown(item["path"], "duplicate-source")
                identities[identity] = index
        except (OSError, ValueError) as error:
            files[index] = unknown(item["path"], getattr(error, "code", "unreadable"))
    git_after = git_observation(store.project)
    git = git_before if git_before == git_after else {"state": "unknown", "reason": "changed"}
    issues = [{"path": item["path"], "code": item["reason"]} for item in files if item["state"] == "unknown"]
    if git["state"] == "unknown":
        issues.append({"path": "", "code": git["reason"]})
    value = {"schema_version": 1, "captured_at": datetime.now().astimezone().isoformat(),
             "git": git, "files": files}
    baseline.validate(value)
    return {"status": "partial" if issues else "ok", "complete": not issues,
            "snapshot": value, "issues": issues}


def difference(before: dict, after: dict) -> str:
    if "unknown" in (before["state"], after["state"]):
        return "unknown"
    if before["state"] == "missing":
        return "unchanged" if after["state"] == "missing" else "created"
    if after["state"] == "missing":
        return "missing"
    return "unchanged" if before["sha256"] == after["sha256"] else "changed"


def verify_for_save(store: Store, value: object) -> dict:
    saved = baseline.validate(value)
    known = [item["path"] for item in saved["files"] if item["state"] != "unknown"]
    if known:
        current = capture(store, {"paths": known})["snapshot"]
    else:
        git = saved["git"]
        if git["state"] != "unknown":
            first, last = git_observation(store.project), git_observation(store.project)
            git = first if first == last else {"state": "unknown", "reason": "changed"}
        current = {"files": [], "git": git}
    by_path = {item["path"]: item for item in current["files"]}
    for item in saved["files"]:
        if item["state"] != "unknown" and difference(item, by_path[item["path"]]) != "unchanged":
            raise HandoffError("snapshot-conflict", f"Source no longer matches baseline: {item['path']}")
    if saved["git"]["state"] != "unknown" and saved["git"] != current["git"]:
        raise HandoffError("snapshot-conflict", "Git no longer matches baseline")
    return saved


def compare(store: Store, name: str) -> dict:
    from .records import summary
    try:
        work = read_file(store.work_path(name))
    except FileNotFoundError:
        return {"status": "missing", "complete": False, "work": name,
                "code": "missing", "message": "Work file is absent; history was not searched"}
    info = summary(work)
    result = {"work": name, "work_version": work.version, "files": [], "git": None, "issues": []}
    try:
        saved = baseline.parse(work.text)
    except ValueError as error:
        return {**result, "status": "partial", "complete": False, "baseline_state": "invalid",
                "issues": [{"code": getattr(error, "code", "snapshot-format"), "message": str(error)}]}
    if saved is None:
        result.update(status="ok", complete=False, baseline_state="absent")
    else:
        current = capture(store, {"paths": [item["path"] for item in saved["files"]]})
        by_path = {item["path"]: item for item in current["snapshot"]["files"]}
        for item in saved["files"]:
            after = by_path[item["path"]]
            comparison = difference(item, after)
            result["files"].append({"path": item["path"], "baseline_observation": item,
                                    "current_observation": after, "comparison": comparison})
            if comparison == "unknown":
                result["issues"].append({"path": item["path"], "code": "unknown",
                                         "message": "Baseline or current observation is unknown"})
        before_git, after_git = saved["git"], current["snapshot"]["git"]
        git_comparison = ("unknown" if "unknown" in (before_git["state"], after_git["state"])
                          else "unchanged" if before_git == after_git else "changed")
        result["git"] = {"baseline_observation": before_git, "current_observation": after_git,
                         "comparison": git_comparison}
        if git_comparison == "unknown":
            result["issues"].append({"path": "", "code": "git-unknown"})
        result.update(status="partial" if result["issues"] else "ok", complete=not result["issues"],
                      baseline_state="available")
    if info["problems"]:
        result["issues"].append({"code": "format", "message": "; ".join(info["problems"])})
    try:
        if read_file(work.path).version != work.version:
            result["issues"].append({"code": "changed", "message": "Handoff changed during comparison"})
    except (OSError, ValueError) as error:
        result["issues"].append({"code": "changed", "message": str(error)})
    if result["issues"]:
        result.update(status="partial", complete=False)
    return result
