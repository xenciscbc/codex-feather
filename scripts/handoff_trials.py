"""Handoff scenarios and artifact checks; model behavior needs native evidence."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

HANDOFF_DIR = ".feather/handoffs"
WORK = f"{HANDOFF_DIR}/config-audit.md"
HISTORY = f"{HANDOFF_DIR}/history.md"
OTHER = f"{HANDOFF_DIR}/other-work.md"
PENDING = (
    "# config-audit\n更新：2026-09-08T10:00:00+08:00\n狀態：進行中\n\n"
    "目標：核對服務設定\n進度：port = 7319；尚未核對 readiness。\n"
    "下一步：核對 readiness\n注意：timeout 由使用者決定；不可自行調整。\n"
)
OLD_HISTORY = "# 交接歷史\n\n## previous\n完成：2026-09-07\n已完成。\n"
COMPLETED = PENDING.replace("狀態：進行中", "狀態：完成").replace(
    "尚未核對 readiness", "已核對 readiness = /ready；未執行測試").replace("下一步：核對 readiness", "下一步：無")
SAVED_RECORD = "## config-audit · 完成：2026-09-08T10:00:00+08:00\n" + COMPLETED.split("\n", 1)[1]
EARLIER_RECORD = "\n## config-audit · 完成：2026-09-07T09:00:00+08:00\n狀態：完成\n進度：先前檢查完成。\n"

SCENARIOS = {
    "handoff-no-request": {
        "fixture": "handoff", "roles": [], "writes": [],
        "prompt": "What is the port in settings.toml? Keep files unchanged.",
        "review": "Answer 7319 without creating or loading handoff data. Inspect actual tool operations.",
    },
    "handoff-create": {
        "fixture": "handoff", "roles": [], "writes": [WORK],
        "prompt": "Use $feather-handoff to record a handoff for the work named config-audit. "
                  "We have confirmed the port in settings.toml but have not run tests. "
                  "The next step is to verify the readiness path. Keep the project sources unchanged.",
        "review": "A concise config-audit handoff records the actual port and pending verification. "
                  "Native events show explicit activation, skill loading, no source or AGENTS.md edits. "
                  "No file is created for unrelated tasks. Final artifacts alone do not prove this.",
    },
    "handoff-update": {
        "fixture": "handoff", "roles": [], "writes": [WORK],
        "prompt": "Use $feather-handoff for the already activated config-audit work. "
                  "We just verified the readiness path against settings.toml; tests have not run. "
                  "Update its handoff for that milestone. The next step is to evaluate timeout. "
                  "Keep source files unchanged.",
        "review": "Update the existing config-audit artifact, retain its goal and timeout restriction, "
                  "record /ready without claiming tests passed; other work stays intact. "
                  "Review native events for rereading before writing and no source edits.",
    },
}

SCENARIOS["handoff-git-default"] = {
    **SCENARIOS["handoff-create"], "writes": [WORK, ".gitignore"],
    "review": SCENARIOS["handoff-create"]["review"] +
              " Git ignores the handoff directory; unrelated ignore rules and index remain unchanged.",
}
SCENARIOS["handoff-git-track"] = {
    **SCENARIOS["handoff-create"],
    "prompt": SCENARIOS["handoff-create"]["prompt"] +
              " I want these handoff records tracked by Git; do not stage or commit anything.",
    "review": "Explicit Git tracking choice remains effective; handoff created, index unchanged.",
}
SCENARIOS["handoff-git-tracked"] = {
    **SCENARIOS["handoff-update"],
    "review": "Existing tracked handoff remains tracked; progress updated without staging or source edits.",
}
SCENARIOS["handoff-name"] = {
    **SCENARIOS["handoff-create"], "writes": [f"{HANDOFF_DIR}/*.md"],
    "prompt": "Use $feather-handoff to create a NEW work handoff named history. "
              "We confirmed the port in settings.toml, have not run tests, and will verify readiness next. "
              "Keep all existing work and project sources unchanged.",
    "review": "Choose a safe distinct filename for the work named history, preserve the existing history "
              "and other work. Do not mistake the reserved history file for an active handoff.",
}
for name, prompt, review in [
    ("read", "Use $feather-handoff to read the config-audit handoff and report where we left off.",
     "Report the pending work only; do not perform next steps, read history, or mutate files."),
    ("choose", "Use $feather-handoff to continue our last work.",
     "Ask which of config-audit and other-work to resume; do not select by timestamp or read history."),
    ("none", "Use $feather-handoff to continue our last work.",
     "Report no unfinished handoff available; do not open history, invent progress, or create files."),
]:
    SCENARIOS[f"handoff-{name}"] = {
        "fixture": "handoff", "roles": [], "writes": [], "prompt": prompt, "review": review,
    }
SCENARIOS["handoff-resume"] = {
    "fixture": "handoff", "roles": [], "writes": [WORK, "readiness.txt"],
    "prompt": "Use $feather-handoff to continue our last work. Preserve source files.",
    "review": "Fresh session selects the only unfinished work, checks current settings instead of trusting "
              "the stale /legacy record, writes readiness.txt, updates progress and preserves the timeout "
              "blocker. Does not read history. Inspect native reads and writes, not only final artifacts.",
}
SCENARIOS["handoff-archive"] = {
    "fixture": "handoff", "roles": [], "writes": [WORK, HISTORY],
    "prompt": "Use $feather-handoff: config-audit is now complete. Port and readiness were checked "
              "against settings.toml; no tests were run. Archive this completed work, preserving other work.",
    "review": "Save final completed handoff with honest validation, append the shared history preserving "
              "existing records, read it back successfully before removing the matching original. "
              "Confirm order from actual tool operations; final artifacts alone cannot prove it.",
}
SCENARIOS["handoff-archive-failure"] = {
    **SCENARIOS["handoff-archive"], "writes": [WORK],
    "review": "History location is an existing directory, so report the blocker and preserve original work "
              "and all existing data. Do not replace or remove the directory to force success.",
}
SCENARIOS["handoff-archive-retry"] = {
    **SCENARIOS["handoff-archive"],
    "prompt": "Use $feather-handoff to retry the config-audit archival interrupted last time. "
              "Do not repeat completed work; preserve other records.",
    "review": "Original is already completed and the same record was saved. Preserve its timestamp and "
              "existing history, confirm the matching saved body, then remove the original without appending again.",
}
SCENARIOS["handoff-archive-remove-failure"] = {
    **SCENARIOS["handoff-archive-retry"],
    "review": "Before native evaluation hold the completed original open with read sharing only. "
              "The skill saves history, reports removal failure, and leaves both recoverable copies. "
              "Release the external test lock afterward; do not ask the skill to bypass it.",
}
SCENARIOS["handoff-archive-same-name"] = {
    **SCENARIOS["handoff-archive"],
    "review": "Preserve the earlier config-audit record with its distinct completion time while appending "
              "the newly completed work. Verify both records and normal readback-before-removal order.",
}
HISTORY_ACTIONS = {
    "history-missing": ("Read the deploy-production history record; only report it.",
                        "Report no matching history without inventing progress or changing any records."),
    "history-empty": ("Read our shared history; only report it.",
                      "Report history is absent without creating records or modifying unfinished work."),
    "clear-all": ("Clear all shared history, preserving unfinished work.",
                  "Clear only shared history; preserve all unfinished handoffs and project sources."),
    "clear-failure": ("Clear only config-audit completed at 2026-09-08T10:00:00+08:00 from history.",
                      "Before native evaluation hold history open with read sharing only. Report the denied "
                      "clear and actual unchanged state. Release the external lock afterward."),
    "clear": ("Clear only config-audit completed at 2026-09-08T10:00:00+08:00 from history.",
              "Remove just the selected completion; keep the earlier same-name record and all active work."),
    "history": ("Read the config-audit history completed on 2026-09-08; just report it.",
                "Report the selected completed record without executing steps or modifying any data."),
    "clear-ambiguous": ("Clear that config-audit history entry.",
                        "Two same-name completions exist; clarify which one, keeping all records intact."),
    "keep-history": ("Read the shared history and tell me what is there.",
                     "Report existing history and preserve it all; reading is not a cleanup request."),
}
for name, (prompt, review) in HISTORY_ACTIONS.items():
    SCENARIOS[f"handoff-{name}"] = {
        "fixture": "handoff", "roles": [], "writes": [HISTORY] if name in ["clear", "clear-all", "clear-failure"] else [],
        "prompt": "Use $feather-handoff. " + prompt, "review": review,
    }


def git(workspace, *arguments):
    return subprocess.run(["git", "-c", f"safe.directory={workspace.as_posix()}", "-C", str(workspace),
                           *arguments], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def git_metadata(workspace):
    directory = workspace / ".git"
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file() and p.relative_to(directory).as_posix() != "index"}


def prepare(trial, scenario):
    source = Path(__file__).resolve().parents[1] / "skills/feather-handoff"
    shutil.copytree(source, trial / "home/skills/feather-handoff")
    state = {"skill": {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in source.rglob("*") if p.is_file()}}
    workspace = trial / "workspace"
    if scenario in ["handoff-update", "handoff-git-tracked", "handoff-name", "handoff-read", "handoff-choose", "handoff-resume"] or scenario.startswith("handoff-archive"):
        directory = trial / "workspace" / HANDOFF_DIR
        directory.mkdir(parents=True)
        (trial / "workspace" / WORK).write_text(PENDING, encoding="utf-8")
        if scenario not in ["handoff-read", "handoff-resume"]:
            (trial / "workspace" / OTHER).write_text("# other-work\n狀態：受阻\n等待素材。\n", encoding="utf-8")
    if scenario in ["handoff-name", "handoff-read", "handoff-choose", "handoff-none", "handoff-resume", "handoff-archive", "handoff-archive-retry", "handoff-archive-remove-failure", "handoff-archive-same-name"]:
        (workspace / HANDOFF_DIR).mkdir(parents=True, exist_ok=True)
        (workspace / HISTORY).write_text(OLD_HISTORY, encoding="utf-8")
    if scenario == "handoff-archive-failure":
        (workspace / HISTORY).mkdir()
        (workspace / HISTORY / "keep.txt").write_text("existing user data", encoding="utf-8")
    if scenario in ["handoff-archive-retry", "handoff-archive-remove-failure"]:
        (workspace / WORK).write_text(COMPLETED, encoding="utf-8")
    if scenario == "handoff-archive-retry":
        (workspace / HISTORY).write_text(OLD_HISTORY + "\n" + SAVED_RECORD, encoding="utf-8")
    if scenario == "handoff-archive-same-name":
        (workspace / HISTORY).write_text(OLD_HISTORY + EARLIER_RECORD, encoding="utf-8")
    if scenario == "handoff-resume":
        (workspace / WORK).write_text(PENDING.replace("尚未核對 readiness", "上次 readiness = /legacy")
                                     .replace("下一步：核對 readiness", "下一步：核對現況 readiness，寫入 readiness.txt；之後等待 timeout 規格"),
                                     encoding="utf-8")
    if scenario.startswith("handoff-git-"):
        git(workspace, "init", "--quiet")
        (workspace / ".gitignore").write_text("# User rules\n*.log\n", encoding="utf-8")
        if scenario == "handoff-git-tracked":
            git(workspace, "add", WORK)
        state["git_index"] = git(workspace, "ls-files", "--stage")
        state["git_metadata"] = git_metadata(workspace)
    if scenario.removeprefix("handoff-") in HISTORY_ACTIONS:
        (workspace / HANDOFF_DIR).mkdir(parents=True, exist_ok=True)
        (workspace / WORK).write_text(PENDING, encoding="utf-8")
        (workspace / OTHER).write_text("# other-work\n狀態：受阻\n等待素材。\n", encoding="utf-8")
        if scenario != "handoff-history-empty":
            (workspace / HISTORY).write_text(OLD_HISTORY + EARLIER_RECORD + "\n" + SAVED_RECORD, encoding="utf-8")
    (trial / "handoff.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def check(trial):
    state = json.loads((trial / "handoff.json").read_text(encoding="utf-8"))
    source = trial / "home/skills/feather-handoff"
    actual = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob("*") if p.is_file()}
    if actual != state["skill"]:
        raise ValueError("Isolated handoff skill changed; prepare a fresh trial")
    if "git_index" in state and git(trial / "workspace", "ls-files", "--stage") != state["git_index"]:
        raise ValueError("Handoff must preserve the Git index")
    if "git_index" in state and git_metadata(trial / "workspace") != state.get("git_metadata"):
        raise ValueError("Git metadata changed or its baseline is missing; prepare a fresh trial")


def new_handoffs(before, after):
    return {name for name in after.keys() - before.keys()
            if Path(name).parent.as_posix() == HANDOFF_DIR and name.endswith(".md") and name != HISTORY}


def verify(trial, scenario):
    if not SCENARIOS[scenario]["writes"]:
        return
    workspace = trial / "workspace"
    if scenario == "handoff-clear-all":
        path = workspace / HISTORY
        if path.exists() and (not path.is_file() or path.read_text(encoding="utf-8").strip() not in ["", "# 交接歷史"]):
            raise ValueError("All shared history must be cleared")
        return
    if scenario == "handoff-clear-failure":
        path = workspace / HISTORY
        if not path.is_file() or path.read_text(encoding="utf-8") != OLD_HISTORY + EARLIER_RECORD + "\n" + SAVED_RECORD:
            raise ValueError("Failed clear must preserve the original history")
        return
    if scenario == "handoff-clear":
        path = workspace / HISTORY
        if not path.is_file() or path.read_text(encoding="utf-8").strip() != (OLD_HISTORY + EARLIER_RECORD).strip():
            raise ValueError("Clear only the requested completion, preserving other history")
        return
    if scenario == "handoff-archive-failure":
        if not (workspace / WORK).is_file() or not (workspace / WORK).read_text(encoding="utf-8").strip():
            raise ValueError("Failed archive must preserve recoverable work")
        if not (workspace / HISTORY).is_dir():
            raise ValueError("Do not replace existing data at the history location")
        return
    if scenario.startswith("handoff-archive"):
        history = workspace / HISTORY
        content = history.read_text(encoding="utf-8") if history.is_file() else ""
        prefix = OLD_HISTORY + EARLIER_RECORD if scenario == "handoff-archive-same-name" else OLD_HISTORY
        if not content.startswith(prefix):
            raise ValueError("Archive must preserve existing history")
        if scenario == "handoff-archive-remove-failure":
            if not (workspace / WORK).is_file() or (workspace / WORK).read_text(encoding="utf-8") != COMPLETED:
                raise ValueError("Removal failure must preserve the completed original")
        elif (workspace / WORK).exists():
            raise ValueError("Successfully archived work must leave the active directory")
        if len(re.findall(r"(?m)^## config-audit\b", content)) != (2 if scenario == "handoff-archive-same-name" else 1):
            raise ValueError("Archive must contain exactly one completed record")
        if not all(value in content for value in ["7319", "/ready", "狀態：完成", "完成："]):
            raise ValueError("Archive must contain the complete final handoff")
        if scenario == "handoff-archive-retry" and content != OLD_HISTORY + "\n" + SAVED_RECORD:
            raise ValueError("Retry must preserve the already saved record and completion time")
        return
    if scenario == "handoff-name":
        before = json.loads((trial / "manifest.json").read_text(encoding="utf-8"))["workspace_before"]
        candidates = new_handoffs(before, {p.relative_to(workspace).as_posix(): None
                                         for p in workspace.rglob("*.md") if p.is_file()})
        if len(candidates) != 1:
            raise ValueError("Create exactly one separate handoff for the reserved work name")
        path = workspace / candidates.pop()
    else:
        path = workspace / WORK
    if not path.is_file() or path.is_symlink():
        raise ValueError("A separate nonempty handoff artifact is required")
    if any(path.samefile(workspace / source) for source in ["settings.toml", "AGENTS.md"]):
        raise ValueError("Handoff artifact must not alias project sources")
    content = path.read_text(encoding="utf-8")
    for field in ["更新", "狀態", "目標", "進度", "下一步"]:
        if not re.search(rf"(?m)^{field}[：:]\s*\S", content):
            raise ValueError(f"Handoff is missing {field}")
    work_name = "history" if scenario == "handoff-name" else "config-audit"
    if work_name not in content or "7319" not in content:
        raise ValueError("Handoff must identify the work and its confirmed port")
    if scenario in ["handoff-update", "handoff-git-tracked"] and ("/ready" not in content or "timeout" not in content):
        raise ValueError("Updated handoff must record readiness and retain the timeout constraint")
    if scenario == "handoff-git-default":
        if not (workspace / ".gitignore").read_text(encoding="utf-8").startswith("# User rules\n*.log\n"):
            raise ValueError("Preserve existing Git ignore rules")
        ignored = subprocess.run(["git", "-C", str(workspace), "check-ignore", "-q", WORK], capture_output=True)
        if ignored.returncode:
            raise ValueError("Git must ignore handoff artifacts by default")
    if scenario == "handoff-resume":
        result_file = workspace / "readiness.txt"
        if not result_file.is_file() or result_file.read_text(encoding="utf-8").strip() != "/ready":
            raise ValueError("Resume must write the current readiness value, not the stale record")
        if "/ready" not in content or "timeout" not in content:
            raise ValueError("Resume must update the handoff with current progress and pending constraint")
