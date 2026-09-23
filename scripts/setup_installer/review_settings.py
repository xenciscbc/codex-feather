"""Persist opt-in plan-review policy in an existing managed installation."""
import json
import re

from . import entrances
from .bundle import ROLES, digest
from .discovery import reuse_candidate
from .environment import Environment
from .installer import read_state
from .transaction import Plan


MODE_LINE = re.compile(r"(?m)^Automatic plan review mode: (off|auto)\s*$")


def mode_value(content: str) -> str:
    matches = list(MODE_LINE.finditer(content))
    if not matches:
        return "off"  # Installations predating this feature are opt-out.
    if len(matches) != 1:
        raise ValueError("Managed guidance has multiple automatic review policies")
    return matches[0].group(1)


def render_mode(content: str, mode: str) -> str:
    if mode not in {"off", "auto"}:
        raise ValueError("Review mode must be off or auto")
    if len(list(MODE_LINE.finditer(content))) != 1:
        raise ValueError("Managed guidance needs a setup update before saving review policy")
    return MODE_LINE.sub(lambda match: match[0].replace(match[1], mode, 1), content)


def run(action: str, environment: Environment, mode: str | None = None,
        expected_plan: str | None = None) -> dict:
    if action not in {"show", "preview", "apply"}:
        raise ValueError("Unknown review policy action")
    if (action == "show" and mode is not None) or (action != "show" and mode not in {"off", "auto"}):
        raise ValueError("preview/apply require --review-mode auto|off; show accepts no mode")
    if action == "apply" and not expected_plan:
        raise ValueError("apply requires --expected-plan from preview")
    plan = Plan()
    state = read_state(environment, plan)
    record = state["components"].get("delegation")
    if not record:
        raise ValueError("No existing delegation setup in the selected scope; run setup first")
    reused = reuse_candidate(environment, "delegation")
    if record.get("reused"):
        if not reused:
            raise ValueError("Reused role installation is missing; repair with setup")
    else:
        expected = {f".codex/agents/{role}.toml" for role in ROLES}
        if set(record.get("files", {})) != expected:
            raise ValueError("Role installation needs a setup update before changing review policy")
        for target, checksum in record["files"].items():
            content = plan.read(environment.target(target))
            if content is None or digest(content) != checksum:
                raise ValueError("Managed roles changed; resolve with setup before changing policy")
    entrance = entrances.model_entrance(environment, record, plan)
    if entrance is None:
        raise ValueError("No managed entrance at the selected scope; attach one with setup first")
    ledger_path, ledger, entry, target = entrance
    before = mode_value(entry["content"])
    if record.get("review_mode", before) != before:
        raise ValueError("Review policy and installation state disagree; resolve with setup")
    report: dict = {"action": action, "scope": environment.scope, "state_path": str(environment.state_path),
              "entrance": str(target), "review_mode": before, "changes": [],
              "effect": "Saved guidance; explicit task/session preferences take precedence. No review counts are reset."}
    if action == "show":
        return report
    assert mode is not None
    entrances.set_review_mode(plan, environment, record, mode)
    record["review_mode"] = mode
    plan.add(environment.state_path, (json.dumps(state, indent=2) + "\n").encode())
    report.update(before=before, after=mode, changes=plan.summary(), plan_id=plan.fingerprint())
    if action == "apply":
        plan.require_preview(expected_plan)
        backup = plan.apply(environment.state_path.parent / "backups")
        if backup:
            report["backup"] = str(backup)
    return report
