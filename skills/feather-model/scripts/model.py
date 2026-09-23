"""Inspect and change Feather's managed role dispatch defaults."""
import argparse
import copy
import io
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from typing import NoReturn

sys.dont_write_bytecode = True


def _load_installer() -> Path:
    root = Path(__file__).resolve().parents[3]
    if (root / "scripts/setup_installer/transaction.py").is_file():
        sys.path.insert(0, str(root / "scripts"))
        return root
    raise ValueError("Feather installer runtime is unavailable. Run model.py from the Feather source or plugin installation.")


try:
    SOURCE_ROOT = _load_installer()
except ValueError as error:
    print(json.dumps({"error": str(error)}, ensure_ascii=False))
    raise SystemExit(1)
try:
    from setup_installer.bundle import ROLES, digest  # noqa: E402
    from setup_installer.discovery import reuse_candidate  # noqa: E402
    from setup_installer.environment import Environment  # noqa: E402
    from setup_installer.installer import read_state  # noqa: E402
    from setup_installer.model_settings import values, render  # noqa: E402
    from setup_installer.transaction import Plan, TransactionError  # noqa: E402
    from setup_installer import entrances  # noqa: E402
except ImportError as error:
    print(json.dumps({"error": f"Feather installer runtime dependency unavailable: {error}"}, ensure_ascii=False))
    raise SystemExit(1)


EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def _owner(environment: Environment, plan: Plan):
    from dataclasses import replace
    reuse_candidate(environment, "delegation")  # Also rejects native role aliases and competing scopes.
    candidates = [replace(environment, scope="user")]
    candidates += [replace(environment, scope="project", project=root) for root in environment.project_roots()]
    owned = []
    for candidate in candidates:
        state = read_state(candidate, plan)
        record = state["components"].get("delegation")
        targets = [candidate.target(f".codex/agents/{role}.toml") for role in ROLES]
        present = [path for path in targets if plan.read(path) is not None]
        if record and not record.get("reused"):
            if set(record.get("files", {})) != {f".codex/agents/{role}.toml" for role in ROLES}:
                raise ValueError(f"Incomplete managed delegation ownership: {candidate.state_path}")
            for role, path in zip(ROLES, targets):
                current = plan.read(path)
                if current is None or digest(current) != record["files"][f".codex/agents/{role}.toml"]:
                    raise ValueError(f"Managed role changed or disappeared: {path}; resolve with feather-setup before changing defaults")
                native = tomllib.loads(current.decode("utf-8-sig"))
                if "model" in native or "model_reasoning_effort" in native:
                    raise ValueError(f"Native role binding overrides Feather dispatch defaults: {path}; update the managed role installation first")
            owned.append((candidate, state, record))
        elif present:
            raise ValueError(f"Visible delegation roles are unmanaged or reused without a verified owner: {present[0]}; resolve the installation scope first")
    if len(owned) != 1:
        raise ValueError("Expected one visible owned delegation installation; resolve duplicate scopes or install delegation first")
    return owned[0]


def _entrance(owner: Environment, record: dict, plan: Plan):
    link = record.get("entrance")
    if not link:
        return None
    if link["scope"] != owner.scope or link["root"] != str(owner.project if owner.scope == "project" else owner.codex_home):
        raise ValueError("Delegation entrance scope differs from the owning installation. Move it to the owner scope with feather-setup before changing permanent defaults")
    observed = entrances.inspect(owner, "delegation", link)
    if observed["status"] != "installed":
        raise ValueError(f"Managed delegation entrance is {observed['status']}: {observed['path']}; resolve it with feather-setup")
    root, ledger_path, ledger = entrances.load(plan, owner, link)
    entry = ledger["blocks"]["delegation"]
    if entry["owners"] != [str(owner.state_path) + "#delegation"]:
        raise ValueError(f"Delegation entrance has shared owners: {ledger_path}; separate its ownership before changing defaults")
    target = root / entry["file"]
    return ledger_path, ledger, entry, target


def _check_other_guidance(environment: Environment, own_target: Path | None, plan: Plan) -> None:
    roots = [environment.codex_home, *environment.project_roots()]
    marker = b"<!-- feather-setup:delegation:begin -->"
    for root in roots:
        for name in ("AGENTS.md", "AGENTS.override.md"):
            path = root / name
            if path == own_target:
                continue
            content = plan.read(path)
            if content is not None and marker in content:
                raise ValueError(f"Another visible delegation entrance can override the owner's defaults: {path}; resolve the competing guidance")


def _assignments(raw: list[str]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in raw:
        if "=" not in item or "." not in item.split("=", 1)[0]:
            raise ValueError(f"Invalid --set {item!r}; use ROLE.model=ID or ROLE.reasoning=EFFORT")
        key, value = item.split("=", 1)
        role, field = key.split(".", 1)
        if role not in ROLES or field not in {"model", "reasoning"}:
            raise ValueError(f"Unknown role or field: {key}")
        if field == "model" and not MODEL_ID.fullmatch(value):
            raise ValueError(f"Invalid model ID: {value!r}; use letters, digits, dot, underscore or hyphen")
        if field == "reasoning" and value not in EFFORTS:
            raise ValueError(f"Invalid reasoning effort: {value!r}")
        if field in result.get(role, {}):
            raise ValueError(f"Duplicate assignment: {key}")
        result.setdefault(role, {})[field] = value
    return result


def run(action: str, environment: Environment, raw: list[str], expected_plan: str | None = None) -> dict:
    if action == "show" and raw:
        raise ValueError("show does not accept --set")
    if action in {"preview", "apply"} and not raw:
        raise ValueError(f"{action} requires at least one --set")
    if action == "apply" and not expected_plan:
        raise ValueError("apply requires --expected-plan from the matching preview")
    assignments = _assignments(raw)
    plan = Plan()
    owner, state, record = _owner(environment, plan)
    entrance = _entrance(owner, record, plan)
    _check_other_guidance(environment, entrance[3] if entrance else None, plan)
    current: dict[str, dict[str, str]]
    if entrance:
        ledger_path, ledger, entry, target = entrance
        current = values(entry["content"])
        overrides = record.get("model_overrides", {})
        for role, fields in overrides.items():
            for field, override in fields.items():
                if current[role][field] != override:
                    raise ValueError(f"Managed role table and ownership state disagree for {role}.{field}; resolve with feather-setup")
    else:
        current = values((SOURCE_ROOT / "templates/AGENTS.md").read_text(encoding="utf-8-sig"))
    owner_info: dict = {"scope": owner.scope, "state_path": str(owner.state_path),
                  "entrance": {"status": "installed", "path": str(target)} if entrance else {"status": "missing", "path": None}}
    report: dict = {"action": action, "owner": owner_info, "roles": current,
                    "roles_source": "managed-entrance" if entrance else "packaged-defaults-no-entrance", "changes": []}
    if action == "show":
        return report
    if not entrance:
        raise ValueError("No managed delegation entrance is active. Attach one at the owning scope with feather-setup --entrance before saving permanent defaults")
    updated = copy.deepcopy(current)
    for role, fields in assignments.items():
        updated[role].update(fields)
    new_overrides = copy.deepcopy(record.get("model_overrides", {}))
    for role, fields in assignments.items():
        new_overrides.setdefault(role, {}).update(fields)
    before_block = entry["content"].encode()
    after_block = render(entry["content"], new_overrides).encode()
    file_content = plan.read(target)
    if file_content is None or file_content.count(before_block) != 1:
        raise ValueError(f"Managed entrance changed: {target}")
    plan.add(target, file_content.replace(before_block, after_block, 1))
    entry["content"] = after_block.decode()
    plan.add(ledger_path, (json.dumps(ledger, indent=2) + "\n").encode())
    record["model_overrides"] = new_overrides
    plan.add(owner.state_path, (json.dumps(state, indent=2) + "\n").encode())
    report.update(before=current, after=updated, changes=plan.summary(), plan_id=plan.fingerprint())
    if action == "apply":
        plan.require_preview(expected_plan)
        backup = plan.apply(owner.state_path.parent / "backups")
        if backup:
            report["backup"] = str(backup)
    return report


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    class JsonParser(argparse.ArgumentParser):
        def error(self, message: str) -> NoReturn:
            raise ValueError(message)

    parser = JsonParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=["show", "preview", "apply"])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--user-home", type=Path, default=Path.home())
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--expected-plan")
    try:
        args = parser.parse_args(argv)
        project = args.project.resolve(strict=True)
        user_home = args.user_home.resolve()
        codex_home = (args.codex_home or Path(os.environ.get("CODEX_HOME", user_home / ".codex"))).resolve()
        print(json.dumps(run(args.action, Environment(project, user_home, codex_home), args.set, args.expected_plan), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, TransactionError) as error:
        detail = error.details if isinstance(error, TransactionError) else {"error": str(error)}
        print(json.dumps(detail, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
