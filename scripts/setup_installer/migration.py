"""Move verified owned bytes between explicit scopes in one filesystem transaction."""
import base64
import copy
from dataclasses import replace
import json
from typing import Any

from .bundle import Bundle, digest, validate_target
from .conflicts import ConflictError
from .discovery import reuse_candidate
from .environment import Environment, find_codex
from .installer import read_state
from . import entrances
from .transaction import Plan


def migrate(environment: Environment, bundle: Bundle, components: list[str], source_scope: str,
            target_scope: str, codex: str | None, dry_run: bool = False, entrance: str = "none",
            expected_plan: str | None = None) -> dict:
    if source_scope not in {"project", "user"} or target_scope not in {"project", "user"} or source_scope == target_scope:
        raise ValueError("Migration requires distinct --from project/user and --to project/user")
    source, destination = replace(environment, scope=source_scope), replace(environment, scope=target_scope)
    plan = Plan()
    source_state, destination_state = read_state(source, plan), read_state(destination, plan)
    selected = list(bundle.components) if "all" in components else list(dict.fromkeys(components))
    report: dict[str, Any] = {"action": "migrate", "from": source_scope, "to": target_scope, "dry_run": dry_run,
              "codex": find_codex(codex), "components": selected, "entrances": {},
              "impact": ("Removing the user-scope capability changes visibility in other projects too."
                         if source_scope == "user" else "The destination user scope makes capabilities visible to other projects.")}
    if "delegation" in selected:
        destination.require_agents_enabled()
    removals = []
    for component in selected:
        record = source_state["components"].get(component)
        if not record or record.get("reused") or not record.get("files"):
            raise ValueError(f"No owned migration source: {component} in {source_scope}")
        if component in destination_state["components"]:
            raise ValueError(f"Migration destination already records {component}; remove that selection explicitly first")
        other = reuse_candidate(destination, component, ignore=source)
        if other:
            raise ValueError(f"Conflict: migration would duplicate another visible capability: {other}")
        for target, expected in record["files"].items():
            validate_target(component, target)
            source_path, target_path = source.target(target), destination.target(target)
            content = plan.read(source_path)
            if content is None or digest(content) != expected:
                encoded = record.get("contents", {}).get(target)
                raise ConflictError(source_path, base64.b64decode(encoded) if encoded else None, content, content)
            current = plan.read(target_path)
            if current is not None:
                raise ConflictError(target_path, None, current, content, owned=False)
            plan.add(target_path, content)
            removals.append(source_path)
        moved = copy.deepcopy(record)
        old_link = record.get("entrance")
        new_link = entrances.location(environment, entrance) if entrance != "none" else old_link
        if old_link and new_link == old_link:
            report["entrances"][component] = entrances.manage(plan, source, bundle, component, old_link,
                                                               transfer_to=destination)
        else:
            if old_link:
                entrances.manage(plan, source, bundle, component, old_link, remove=True)
            if new_link:
                report["entrances"][component] = entrances.manage(plan, destination, bundle, component, new_link)
                moved["entrance"] = new_link
        destination_state["components"][component] = moved
        del source_state["components"][component]
    # Plan.apply verifies every destination write before any source removal is attempted.
    for path in removals:
        plan.add(path, None)
    plan.add(destination.state_path, (json.dumps(destination_state, indent=2) + "\n").encode())
    plan.add(source.state_path, (json.dumps(source_state, indent=2) + "\n").encode())
    report["changes"] = plan.summary()
    report["_plan_id"] = plan.fingerprint()
    if not dry_run:
        plan.require_preview(expected_plan)
        backup = plan.apply(destination.state_path.parent / "backups")
        if backup:
            report["backup"] = str(backup)
    return report
