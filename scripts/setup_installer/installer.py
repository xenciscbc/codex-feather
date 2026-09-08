"""Apply an explicit installation request and report its observable state."""
import json
import base64
from typing import Any

from .bundle import Bundle, digest, validate_target
from .environment import Environment, find_codex
from .discovery import reuse_candidate
from .transaction import Plan, read_regular
from . import entrances
from .conflicts import ConflictError


def read_state(environment: Environment) -> dict:
    saved = read_regular(environment.state_path)
    state = json.loads(saved) if saved is not None else {"format": 1, "environment": environment.identity, "components": {}}
    if state.get("format") != 1:
        raise ValueError("Unsupported installation record")
    if state.get("environment") != environment.identity:
        raise ValueError("Installation record belongs to a different environment. Use an explicit migration; no paths were retargeted.")
    return state


def execute(action: str, environment: Environment, bundle: Bundle, components: list[str], codex: str | None,
            dry_run: bool = False, entrance: str = "none", on_conflict: str = "fail",
            expected_plan: str | None = None) -> dict:
    state_path = environment.state_path
    state = read_state(environment)
    report: dict[str, Any] = {"action": action, "components": {}, "project": str(environment.project),
                              "scope": environment.scope, "dry_run": dry_run, "changes": [], "entrances": {}}
    plan = Plan()
    managed_operation = False
    components = list(bundle.components) if "all" in components else list(dict.fromkeys(components))
    if action in {"install", "update"}:
        report["codex"] = find_codex(codex)
        if "delegation" in components:
            environment.require_agents_enabled()
    for component in components:
        if component not in bundle.components:
            raise ValueError(f"Unknown component: {component}")
        old = state["components"].get(component)
        if action == "check" and old and old.get("entrance"):
            report["entrances"][component] = entrances.inspect(environment, component, old["entrance"])
        existing = reuse_candidate(environment, component) if action != "remove" else None
        if existing:
            if action == "update":
                raise ValueError(f"Component {component} is reused from {existing}; update its owning scope explicitly")
            report["components"][component] = existing
            if action == "install" and entrance != "none":
                managed_operation = True
                record = state["components"].setdefault(component, {"reused": existing, "files": {}})
                link = entrances.location(environment, entrance)
                if record.get("entrance") and record["entrance"] != link:
                    raise ValueError("Existing entrance is in another scope; remove it explicitly before changing scope")
                report["entrances"][component] = entrances.manage(plan, environment, bundle, component, link,
                                                                   replace=on_conflict == "replace")
                record["entrance"] = link
            continue
        files = bundle.files(component)
        if action == "remove":
            if not old:
                report["components"][component] = {"status": "not-managed"}
                continue
            managed_operation = True
            for target, expected in old["files"].items():
                validate_target(component, target)
                path = environment.target(target)
                before = read_regular(path)
                if before is not None and digest(before) != expected and on_conflict != "replace":
                    encoded = old.get("contents", {}).get(target)
                    raise ConflictError(path, base64.b64decode(encoded) if encoded else None, before, None)
                plan.add(path, None)
            if old.get("entrance"):
                report["entrances"][component] = entrances.manage(plan, environment, bundle, component,
                                                                   old["entrance"], remove=True,
                                                                   replace=on_conflict == "replace")
            del state["components"][component]
            report["components"][component] = {"status": "would-remove" if dry_run else "removed"}
            continue
        for target in files:
            validate_target(component, target)
        if action == "update" and (not old or old.get("reused")):
            raise ValueError(f"No owned installation to update: {component}")
        if action in {"install", "update"}:
            managed_operation = True
            all_targets = dict.fromkeys([*files, *(old or {}).get("files", {})])
            for target in all_targets:
                validate_target(component, target)
                content = files.get(target)
                path = environment.target(target)
                before = read_regular(path)
                owned = bool(old and target in old["files"])
                expected_hash = old["files"].get(target) if old else None
                if (before is not None and digest(before) != expected_hash) or (owned and before is None):
                    encoded = (old or {}).get("contents", {}).get(target)
                    expected = base64.b64decode(encoded) if encoded else None
                    if not owned or on_conflict != "replace":
                        raise ConflictError(path, expected, before, content, owned)
                plan.add(path, content)
            state["components"][component] = {"version": bundle.version,
                                               "files": {target: digest(data) for target, data in files.items()},
                                               "contents": {target: base64.b64encode(data).decode() for target, data in files.items()}}
            if old and old.get("entrance"):
                state["components"][component]["entrance"] = old["entrance"]
            if entrance != "none" or (action == "update" and old and old.get("entrance")):
                record = state["components"][component]
                link = entrances.location(environment, entrance) if entrance != "none" else old["entrance"]
                if record.get("entrance") and record["entrance"] != link:
                    raise ValueError("Existing entrance is in another scope; remove it explicitly before changing scope")
                report["entrances"][component] = entrances.manage(plan, environment, bundle, component, link,
                                                                   replace=on_conflict == "replace")
                record["entrance"] = link
        record = state["components"].get(component)
        installed = bool(record) and not record.get("reused")
        conflicts = []
        paths = []
        if record:
            for target, expected in record["files"].items():
                validate_target(component, target)
                path = environment.target(target)
                paths.append(str(path))
                observed = read_regular(path)
                if action == "check" and observed is not None and digest(observed) != expected:
                    conflicts.append(str(path))
                installed = installed and observed is not None and digest(observed) == expected
        elif action == "check":
            paths = [str(environment.target(target)) for target in files]
            conflicts = [str(environment.target(target)) for target in files if read_regular(environment.target(target)) is not None]
        if action in {"install", "update"} and not dry_run:
            installed = True
        status = "conflict" if conflicts else "installed" if installed else "missing"
        if dry_run and action in {"install", "update"} and any(change.path in {environment.target(target) for target in files} for change in plan.changes):
            status = "would-update" if old else "would-install"
        report["components"][component] = {"status": status, "paths": paths, "version": (record or {}).get("version")}
        if conflicts:
            report["components"][component]["conflicts"] = conflicts
    if action in {"install", "update", "remove"} and managed_operation:
        plan.add(state_path, (json.dumps(state, indent=2) + "\n").encode("utf-8"))
        report["changes"] = plan.summary()
        if not dry_run:
            plan.require_preview(expected_plan)
            backup = plan.apply(environment.state_path.parent / "backups")
            if backup:
                report["backup"] = str(backup)
    if action == "check":
        report["status"] = "attention-required" if any(item["status"] in {"conflict", "missing", "shadowed"}
                                                         for category in ["components", "entrances"]
                                                         for item in report[category].values()) else "ok"
    report["_plan_id"] = plan.fingerprint()
    return report
