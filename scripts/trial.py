"""Isolated Feather trials. Python 3.11+, standard library only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib
from scenarios import ROLES, SCENARIOS, EXECUTOR_CHECK, RETURN_CONTRACT_CHECK
import handoff_trials
import claude_memory_trials
import claude_memory_link_trials
import snapshot_trials

HANDOFF_FAMILIES = (handoff_trials, claude_memory_trials, claude_memory_link_trials, snapshot_trials)
HANDOFF_SCENARIOS = {name: family for family in HANDOFF_FAMILIES for name in family.SCENARIOS}
SCENARIOS = {**SCENARIOS, **{name: family.SCENARIOS[name] for name, family in HANDOFF_SCENARIOS.items()}}

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"role": "scout", "model": "gpt-6-luna", "reasoning": "low"}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def hashes(directory, exclude_git=False):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*"))
            if p.is_file() and (not exclude_git or ".git" not in p.relative_to(directory).parts)}


def prepare(trial, scenario="scout"):
    # Exclusive creation prevents overwriting a previous run or a real Codex home.
    trial.mkdir(parents=True, exist_ok=False)
    (trial / "home/agents").mkdir(parents=True)
    shutil.copytree(ROOT / "tests/fixtures" / SCENARIOS[scenario].get("fixture", scenario), trial / "workspace",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for role in ROLES:
        shutil.copy2(ROOT / "templates" / f"{role}.toml", trial / "home/agents" / f"{role}.toml")
    family = HANDOFF_SCENARIOS.get(scenario)
    if family:
        handoff_trials.prepare(trial, scenario)
        if family is not handoff_trials:
            family.prepare(trial, scenario)
    else:
        shutil.copy2(ROOT / "templates/entrances/delegation.md", trial / "workspace/AGENTS.md")
        runtime_skill = trial / "workspace/.agents/skills/feather-delegation/SKILL.md"
        runtime_skill.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "templates/feather-delegation/SKILL.md", runtime_skill)
    (trial / "workspace/.feather-root").touch()
    (trial / "home/config.toml").write_text('project_root_markers = [".feather-root"]\n\n[agents]\nenabled = true\n', encoding="utf-8")
    (trial / "prompt.txt").write_text(SCENARIOS[scenario]["prompt"], encoding="utf-8")
    write_json(trial / "manifest.json", {
        "format": 3, "scenario": scenario, "expected": SCENARIOS[scenario].get("expected", EXPECTED if scenario == "scout" else SCENARIOS[scenario]["roles"]), "actual": "unconfirmed",
        "workspace_before": hashes(trial / "workspace", exclude_git=scenario.startswith("handoff-git-")),
    })
    write_json(trial / "review.json", {
        "scenario": scenario, "criteria": SCENARIOS[scenario]["review"],
        "behavior": "unconfirmed", "actual_model_reasoning": "unconfirmed",
        "native_evidence_references": [], "usage": None, "notes": "",
    })


def check(trial, pristine=True):
    manifest = json.loads((trial / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 3 or manifest.get("scenario") not in SCENARIOS:
        raise ValueError("Unsupported trial manifest; prepare a fresh trial")
    family = HANDOFF_SCENARIOS.get(manifest["scenario"])
    if family:
        handoff_trials.check(trial)
        check_family = getattr(family, "check", None)
        if family is not handoff_trials and check_family:
            check_family(trial)
    configured = {}
    for name, (model, effort, sandbox) in ROLES.items():
        role = tomllib.loads((trial / "home/agents" / f"{name}.toml").read_text(encoding="utf-8"))
        if "model" in role or "model_reasoning_effort" in role:
            raise ValueError(f"{name} locks model or reasoning; remove role bindings and prepare a fresh trial")
        if (role.get("name"), role.get("sandbox_mode")) != (name, sandbox):
            raise ValueError(f"{name} identity or sandbox does not match the spec")
        if not role.get("description") or not role.get("developer_instructions"):
            raise ValueError(f"Missing required native role fields: {name}")
        configured[name] = {"model": None, "reasoning": None, "sandbox": sandbox,
                            "dispatch_defaults": {"model": model, "reasoning": effort}}
    if {p.name for p in (trial / "home/agents").glob("*.toml")} != {f"{r}.toml" for r in ROLES}:
        raise ValueError("Unexpected role template in isolated home")
    config = tomllib.loads((trial / "home/config.toml").read_text(encoding="utf-8"))
    if config != {"project_root_markers": [".feather-root"], "agents": {"enabled": True}}:
        raise ValueError("Trial config changed: main preferences must be supplied only for this run")
    changed = hashes(trial / "workspace", exclude_git=manifest["scenario"].startswith("handoff-git-")) != manifest["workspace_before"]
    result = {"static": "pass", "configured": configured, "workspace_unchanged": not changed,
              "actual": "unconfirmed", "behavior": "requires native run and manual review"}
    if changed and pristine:
        raise ValueError("Workspace differs from the prepared baseline")
    return result


def verify(trial):
    # Invalidate any previous pass before evaluating a changed artifact.
    write_json(trial / "verification.json", {"artifacts": "unconfirmed", "actual": "unconfirmed"})
    result = check(trial, pristine=False)
    manifest = json.loads((trial / "manifest.json").read_text(encoding="utf-8"))
    scenario = manifest["scenario"]
    exclude_git = scenario.startswith("handoff-git-")
    before, after = manifest["workspace_before"], hashes(trial / "workspace", exclude_git=exclude_git)
    changes = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
    unexpected = changes - set(SCENARIOS[scenario]["writes"])
    if scenario == "handoff-name":
        unexpected -= handoff_trials.new_handoffs(before, after)
    if unexpected:
        raise ValueError(f"Changes outside ownership scope: {sorted(unexpected)}")
    family = HANDOFF_SCENARIOS.get(scenario)
    if family:
        family.verify(trial, scenario)
    workspace = trial / "workspace"
    if scenario == "analyst-report":
        report = workspace / "analysis.md"
        if not report.is_file() or not report.read_text(encoding="utf-8").strip():
            raise ValueError("Analyst must produce the assigned nonempty analysis.md artifact")
        if report.is_symlink() or any(report.samefile(workspace / p) for p in before):
            raise ValueError("Analyst artifact must be separate from source files, not a link or alias")
    elif scenario == "mech":
        for region, retries in [("east", 2), ("west", 3)]:
            expected = f"[api]\ntimeout_ms = 2500\nretries = {retries}\n"
            if (workspace / f"configs/{region}.toml").read_text(encoding="utf-8") != expected:
                raise ValueError(f"Incorrect batch edit: {region}")
    elif scenario == "executor":
        tested = subprocess.run([sys.executable, "-I", "-B", "-c", EXECUTOR_CHECK, str(workspace / "retry.py")],
                                capture_output=True, text=True, timeout=10, cwd=workspace)
        if tested.returncode:
            raise ValueError("Executor behavior failed: " + tested.stderr[-2000:])
    elif scenario == "coordination":
        if (workspace / "output/summary.txt").read_text(encoding="utf-8") != "7319\nVERIFIED\n":
            raise ValueError("Coordination result must be 7319 followed by VERIFIED")
    elif scenario == "return-contract":
        for region in ("east", "west"):
            result_file = workspace / f"output/{region}.txt"
            if not result_file.is_file() or result_file.read_text(encoding="utf-8") != "READY\n":
                raise ValueError(f"Return-contract batch result must be exactly READY: {region}")
        tested = subprocess.run(
            [sys.executable, "-I", "-B", "-c", RETURN_CONTRACT_CHECK,
             str(workspace / "output/retry.py")],
            capture_output=True, text=True, timeout=10, cwd=workspace,
        )
        if tested.returncode:
            raise ValueError("Return-contract executor behavior failed: " + tested.stderr[-2000:])
    elif scenario == "bounded-reclaim":
        partial = workspace / "output/partial.txt"
        if not partial.is_file() or partial.read_text(encoding="utf-8") != "PARTIAL\n":
            raise ValueError("Bounded reclaim must preserve the exact PARTIAL result")
        attempts = workspace / "attempts.txt"
        if not attempts.is_file() or attempts.read_text(encoding="utf-8") != "2\n":
            raise ValueError("Bounded reclaim must preserve exactly two failed attempts")
    # Verify only artifacts. A correct artifact cannot establish role choice or execution identity.
    if hashes(workspace, exclude_git=exclude_git) != after:
        raise ValueError("Behavior validation itself changed workspace files")
    result.update(artifacts="pass", changed_files=sorted(changes),
                  review_criteria=SCENARIOS[scenario]["review"])
    write_json(trial / "verification.json", result)
    return result


def native(trial, executable, arguments, prefix):
    executable = Path(executable).resolve(strict=True)
    if os.name == "nt" and executable.suffix.lower() != ".exe":
        raise ValueError("On Windows pass the native codex.exe, not a shell shim")
    # Drop desktop/daemon/session routing so the isolated CLI cannot attach to this task.
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith("CODEX_")}
    environment["CODEX_HOME"] = str(trial / "home")
    started = time.monotonic()
    with (trial / f"{prefix}.stdout").open("w", encoding="utf-8") as out, (trial / f"{prefix}.stderr").open("w", encoding="utf-8") as err:
        process = subprocess.Popen([str(executable), *arguments], cwd=trial / "workspace",
                                   env=environment, stdout=out, stderr=err)
        try:
            code = process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
            process.kill()
            process.wait()
            write_json(trial / f"{prefix}.json", {"exit_code": process.returncode,
                       "timed_out": True, "elapsed_seconds": time.monotonic() - started})
            raise
    write_json(trial / f"{prefix}.json", {"exit_code": code,
               "elapsed_seconds": time.monotonic() - started, "arguments": arguments})
    if code:
        raise RuntimeError(f"Native command failed; see {prefix}.stderr")


def main():
    # Redirected output must match the UTF-8 contract used by the trial callers.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "check", "verify", "probe", "smoke"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--scenario", choices=SCENARIOS, default="scout", help="Scenario for prepare only")
    parser.add_argument("--codex", help="Absolute native Codex executable path")
    parser.add_argument("--enable-live", action="store_true", help="Explicitly allow model usage")
    parser.add_argument("--main-model", help="Your selected main model for the isolated run")
    parser.add_argument("--main-reasoning", choices=["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"])
    args = parser.parse_args()
    trial = args.directory.resolve()
    if args.action == "prepare":
        prepare(trial, args.scenario)
    elif args.action == "check":
        print(json.dumps(check(trial), indent=2))
    elif args.action == "verify":
        print(json.dumps(verify(trial), indent=2))
    else:
        if not args.codex:
            parser.error("--codex is required")
        check(trial)
        if args.action == "smoke" and not (args.enable_live and args.main_model and args.main_reasoning):
            parser.error("smoke requires --enable-live, --main-model, and --main-reasoning")
        if args.action == "smoke" and (trial / "smoke.stdout").exists():
            raise ValueError("Prepare a fresh directory for each smoke run")
        native(trial, args.codex, ["--version"], "version")
        if args.action == "probe":
            native(trial, args.codex, ["debug", "prompt-input", "Feather configuration probe"], "probe")
        else:
            scenario = json.loads((trial / "manifest.json").read_text(encoding="utf-8"))["scenario"]
            sandbox = "workspace-write" if SCENARIOS[scenario]["writes"] else "read-only"
            native(trial, args.codex, ["exec", "--strict-config", "--skip-git-repo-check",
                   "--sandbox", sandbox, "--model", args.main_model,
                   "-c", "model_reasoning_effort=" + json.dumps(args.main_reasoning),
                   "--json", "--output-last-message", str(trial / "answer.md"),
                   (trial / "prompt.txt").read_text(encoding="utf-8")], "smoke")
            print(json.dumps(verify(trial), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
