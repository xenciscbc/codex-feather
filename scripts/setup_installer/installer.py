"""Apply an explicit installation request and report its observable state."""
import json
import base64
from pathlib import Path
from typing import Any

from .bundle import Bundle, digest, validate_target
from .environment import Environment, find_codex
from .discovery import reuse_candidate, skill_name, unowned_handoff_paths
from .transaction import Plan, read_regular
from . import entrances, diagnostics
from .conflicts import ConflictError
from .handoff_runtime import inspect_python


def read_state(environment: Environment, plan: Plan) -> dict:
    saved = plan.read(environment.state_path)
    state = json.loads(saved) if saved is not None else {"format": 1, "environment": environment.identity, "components": {}}
    if state.get("format") != 1:
        raise ValueError("Unsupported installation record")
    if state.get("environment") != environment.identity:
        raise ValueError("Installation record belongs to a different environment. Use an explicit migration; no paths were retargeted.")
    return state


def plugin_provider(path: Path | None) -> dict | None:
    """Identify the plugin skill on disk; this does not establish session loading."""
    if path is None:
        return None
    source = path.resolve(strict=True)
    content = read_regular(source)
    if content is None or source.name != "SKILL.md" or skill_name(content) != "handoff":
        raise ValueError(f"Invalid plugin handoff skill: {source}")
    return {"kind": "plugin", "source": str(source), "sha256": digest(content)}


def execute(action: str, environment: Environment, bundle: Bundle, components: list[str], codex: str | None,
            dry_run: bool = False, entrance: str = "none", on_conflict: str = "fail",
            expected_plan: str | None = None, handoff_provider: Path | None = None,
            default_entrance: bool = False) -> dict:
    state_path = environment.state_path
    plan = Plan()
    state = read_state(environment, plan)
    report: dict[str, Any] = {"action": action, "components": {}, "project": str(environment.project),
                              "scope": environment.scope, "dry_run": dry_run, "changes": [], "entrances": {}}
    managed_operation = False
    components = list(bundle.components) if "all" in components else list(dict.fromkeys(components))
    provider = plugin_provider(handoff_provider) if "handoff" in components else None
    if action in {"install", "update"}:
        report["codex"] = find_codex(codex)
        if "delegation" in components:
            environment.require_agents_enabled()
    for component in components:
        if component not in bundle.components:
            raise ValueError(f"Unknown component: {component}")
        old = state["components"].get(component)
        selected_entrance = (entrance if entrance != "none" or not default_entrance or action != "install"
                             else ((old.get("entrance") or {}).get("scope", "none") if old else environment.scope))
        if component == "handoff" and provider and action in {"install", "update"} and old and not old.get("provider"):
            raise ValueError("A standalone handoff installation is recorded here; remove or manage it explicitly before selecting plugin handoff")
        if component == "handoff" and not provider and action in {"install", "update"} and old and old.get("provider"):
            raise ValueError("Plugin handoff is recorded here; use the owning plugin to update it")
        if component == "handoff" and provider and action in {"install", "update"} and selected_entrance == "none" and not (old or {}).get("entrance"):
            raise ValueError("Plugin handoff already supplies the skill; choose a project or user entrance to enable its guidance")
        if action == "check" and old and old.get("entrance"):
            report["entrances"][component] = entrances.inspect(environment, component, old["entrance"])
        collisions: list[Path] = []
        try:
            if component == "handoff" and provider and action in {"install", "update", "check"}:
                owned_targets = set(old.get("files", {})) if old and action == "check" else set()
                collisions = unowned_handoff_paths(environment, plan, owned_targets)
                if collisions:
                    raise ValueError(f"Plugin handoff overlaps an unowned standalone skill: {collisions}; preserve it and resolve its owning installation")
            existing = reuse_candidate(environment, component, owned=set(old.get("files", {})) if old else None) if action != "remove" else None
        except (OSError, ValueError) as error:
            if action != "check":
                raise
            report["components"][component] = {"status": "conflict", "message": str(error), "paths": [str(path) for path in collisions]}
            continue
        if existing:
            if component == "handoff" and provider and action in {"install", "update"}:
                raise ValueError(f"A standalone handoff skill is visible from {existing['scope']} scope; preserve its owning installation")
            if component == "handoff" and provider and old and old.get("provider") and action == "check":
                report["components"][component] = {"status": "conflict", "message": "Plugin handoff overlaps a standalone skill", "paths": existing["paths"]}
                continue
            if action == "update":
                raise ValueError(f"Component {component} is reused from {existing}; update its owning scope explicitly")
            report["components"][component] = existing
            if action == "install" and selected_entrance != "none":
                managed_operation = True
                record = state["components"].setdefault(component, {"reused": existing, "files": {}})
                link = entrances.location(environment, selected_entrance)
                report["entrances"][component] = entrances.attach(plan, environment, bundle, component, record, link,
                                                                  replace=on_conflict == "replace")
            continue
        files = {} if component == "handoff" and provider else bundle.files(component)
        if action == "remove":
            if not old:
                report["components"][component] = {"status": "not-managed"}
                continue
            managed_operation = True
            for target, expected in old["files"].items():
                validate_target(component, target)
                path = environment.target(target)
                before = plan.read(path)
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
            validate_target(component, target, bundled=True)
        if action == "update" and (not old or old.get("reused")):
            raise ValueError(f"No owned installation to update: {component}")
        if action in {"install", "update"}:
            managed_operation = True
            all_targets = dict.fromkeys([*files, *(old or {}).get("files", {})])
            for target in all_targets:
                validate_target(component, target)
                content = files.get(target)
                path = environment.target(target)
                before = plan.read(path)
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
            if component == "handoff" and provider:
                state["components"][component]["provider"] = provider
            if component == "delegation" and old and old.get("model_overrides"):
                state["components"][component]["model_overrides"] = old["model_overrides"]
            if component == "delegation" and old and "review_mode" in old:
                state["components"][component]["review_mode"] = old["review_mode"]
            if old and old.get("entrance"):
                state["components"][component]["entrance"] = old["entrance"]
            if selected_entrance != "none" or (old and old.get("entrance")):
                record = state["components"][component]
                link = entrances.location(environment, selected_entrance) if selected_entrance != "none" else old["entrance"]
                report["entrances"][component] = entrances.attach(plan, environment, bundle, component, record, link,
                                                                  replace=on_conflict == "replace")
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
        if component == "handoff":
            recorded_provider = (record or {}).get("provider")
            if recorded_provider:
                if provider is None:
                    status = "unavailable"
                elif recorded_provider.get("kind") != "plugin" or recorded_provider.get("sha256") != provider["sha256"]:
                    status = "provider-changed"
            elif provider and not record and action == "check":
                status = "available"
        if dry_run and action in {"install", "update"} and any(change.path in {environment.target(target) for target in files} for change in plan.changes):
            status = "would-update" if old else "would-install"
        if component == "handoff" and dry_run and action in {"install", "update"} and provider:
            status = "would-update" if old else "would-install"
        report["components"][component] = {"status": status, "paths": paths, "version": (record or {}).get("version")}
        if component == "handoff" and record and record.get("files") and not record.get("provider"):
            report["components"][component]["provider"] = {
                "kind": "standalone", "source": next((path for path in paths if Path(path).name == "SKILL.md"), str(environment.state_path)),
                "session": "unconfirmed"}
        elif component == "handoff" and (provider or (record or {}).get("provider")):
            report["components"][component]["provider"] = {
                "kind": "plugin", "source": (provider or record["provider"])["source"],
                "session": "unconfirmed"}
        if component == "handoff":
            report["components"][component]["guidance"] = (
                "recorded" if (record or {}).get("entrance") else "missing")
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
        report["runtime"] = diagnostics.inspect(environment, report["components"], codex)
        report["status"] = "attention-required" if any(item["status"] in {"conflict", "missing", "shadowed", "unavailable", "provider-changed", "disabled", "invalid"}
                                                         for category in ["components", "entrances", "runtime"]
                                                         for item in report[category].values()) else "ok"
    if action == "check" and "handoff" in components:
        runtime = inspect_python()
        report.setdefault("runtime", {})["python"] = runtime
        if runtime["status"] in {"missing", "incompatible"}:
            report["status"] = "attention-required"
    report["_plan_id"] = plan.fingerprint()
    return report
