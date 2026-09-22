"""Resume-baseline trials; artifact checks remain separate from native behavior."""
import hashlib
import json
import subprocess
import sys

from handoff_trials import HANDOFF_DIR, WORK, PENDING, handoff_fields


SCENARIOS = {
    "handoff-snapshot-read": {
        "fixture": "handoff", "roles": [], "writes": [],
        "prompt": "Use $feather-handoff to read config-audit and report the saved goal, progress, next step and constraints. Only read the handoff; keep all files unchanged.",
        "review": "Read the saved work, report saved evidence as historical, and do not run compare, tests or next steps. Inspect native commands and source hashes; final artifacts alone do not prove read-only behavior.",
    },
    "handoff-snapshot-resume": {
        "fixture": "handoff", "roles": [], "writes": [WORK, "readiness.txt"],
        "prompt": "Use $feather-handoff to resume config-audit. Preserve source files and keep the timeout decision pending.",
        "review": "Read the full work, run compare, see settings.toml changed, inspect current /ready and write readiness.txt. Update progress without treating the old claimed test pass as current verification. Keep timeout unresolved and do not archive. Inspect native tool operations for compare-before-action and source preservation.",
    },
    "handoff-snapshot-partial": {
        "fixture": "handoff", "roles": [], "writes": [WORK, "readiness.txt"],
        "prompt": "Use $feather-handoff to resume config-audit. Preserve source files, keep timeout pending, and retain the unresolved evidence.bin verification constraint while completing independent work.",
        "review": "Compare reports partial because evidence.bin had an unknown baseline. Distinguish that from settings.toml's known change; verify /ready and write readiness.txt without claiming all sources or tests are verified. Preserve the evidence.bin constraint and leave the handoff unfinished. Native operations must show no guessing or implicit archival.",
    },
}


def prepare(trial, scenario):
    workspace = trial / "workspace"
    subprocess.run(["git", "-C", str(workspace), "init", "--quiet", "--initial-branch=main"], check=True, capture_output=True)
    (workspace / ".gitignore").write_text("/.feather/handoffs/\n", encoding="utf-8")
    old = (workspace / "settings.toml").read_bytes().replace(b"/ready", b"/legacy")
    value = {"schema_version": 1, "captured_at": "2026-09-12T10:00:00+08:00",
             "git": {"state": "available", "head": None, "branch": "main"},
             "files": [{"path": "settings.toml", "state": "present", "sha256": hashlib.sha256(old).hexdigest()}]}
    record = PENDING.replace("尚未核對 readiness", "上次 readiness = /legacy；歷史測試聲明尚待核實")
    record = record.replace("下一步：核對 readiness", "下一步：核對現在 readiness，寫入 readiness.txt；之後等待 timeout 決定")
    record += "驗證：歷史紀錄聲稱舊內容已通過測試；本 session 尚未驗證。\n"
    if scenario.endswith("partial"):
        value["files"].insert(0, {"path": "evidence.bin", "state": "unknown", "reason": "unreadable"})
        record = record.replace("注意：", "注意：evidence.bin 的歷史驗證仍不明，不可視為已驗證；")
        (workspace / "evidence.bin").write_bytes(b"current bytes do not establish the old baseline")
    record += "\n## 檔案基準\n```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n"
    (workspace / HANDOFF_DIR).mkdir(parents=True, exist_ok=True)
    (workspace / WORK).write_text(record, encoding="utf-8")


def verify(trial, scenario):
    answer = trial / "answer.md"
    if not answer.is_file() or not answer.read_text(encoding="utf-8").strip():
        raise ValueError("Native final answer is required; offline fixture checks are not model behavior")
    if scenario.endswith("read"):
        return
    workspace = trial / "workspace"
    path = workspace / WORK
    if not path.is_file():
        raise ValueError("Pending timeout must retain the active handoff")
    content = path.read_text(encoding="utf-8")
    fields = handoff_fields(content)
    if fields["狀態"] == "完成" or "/ready" not in fields["進度"] or "timeout" not in content:
        raise ValueError("Resume must record current readiness while preserving the pending timeout")
    result = workspace / "readiness.txt"
    if not result.is_file() or result.read_text(encoding="utf-8").strip() != "/ready":
        raise ValueError("Resume must write current /ready rather than stale /legacy")
    if scenario.endswith("partial") and "evidence.bin" not in content:
        raise ValueError("Partial evidence constraint must survive resumption")
    helper = trial / "home/skills/feather-handoff/scripts/handoff.py"
    read = subprocess.run([sys.executable, "-B", str(helper), "--project", str(workspace), "read", "--work", "config-audit.md"],
                          capture_output=True, text=True, encoding="utf-8", timeout=15)
    if read.returncode or json.loads(read.stdout).get("snapshot_state") != "available":
        raise ValueError("Resume must retain a valid baseline section")
