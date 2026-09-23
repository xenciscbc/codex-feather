"""Own bounded instruction blocks separately from the capability installation scope."""
import json
from pathlib import Path

from .bundle import Bundle
from .environment import Environment
from .transaction import Plan
from .conflicts import ConflictError


def instruction(bundle: Bundle, component: str, overrides: dict | None = None) -> str:
    if component == "delegation":
        body = bundle.payload["assets/templates/AGENTS.md"].decode("utf-8-sig").strip()
        if overrides:
            from .model_settings import render
            body = render(body, overrides)
        guard = ("Apply this delegation guidance only when scout, analyst, mech-executor and executor "
                 "are available in the current environment. If unavailable, report the missing capability "
                 "and keep the work with the main Agent. This declaration does not install or enable roles.")
    else:
        guard = ("Use this capability only when feather-handoff is listed among the skills available in the "
                 "current environment. This declaration does not install the skill in other projects.")
        body = ("When the user requests a handoff or continuation of recorded work, read and follow the "
                "available feather-handoff skill. Preserve its handoff-file and history rules. "
                "This entry grants no additional authorization to edit, delegate, or delete data.")
    return f"{guard}\n\n{body}"


def location(environment: Environment, scope: str) -> dict[str, str]:
    return {"scope": scope, "root": str(environment.project if scope == "project" else environment.codex_home)}


def load(plan: Plan, environment: Environment, link: dict[str, str]) -> tuple[Path, Path, dict]:
    scope = link["scope"]
    if scope not in {"project", "user"} or link != location(environment, scope):
        raise ValueError("Entrance belongs to another environment; supply its original project and Codex home")
    root = Path(link["root"])
    ledger_path = root / (".feather/setup/entrances.json" if scope == "project" else "feather-setup/entrances.json")
    saved = plan.read(ledger_path)
    ledger = json.loads(saved) if saved is not None else {"format": 1, "location": link, "blocks": {}}
    if ledger.get("format") != 1 or ledger.get("location") != link:
        raise ValueError(f"Invalid entrance record: {ledger_path}")
    return root, ledger_path, ledger


def inspect(environment: Environment, component: str, link: dict[str, str]) -> dict:
    plan = Plan()
    root, ledger_path, ledger = load(plan, environment, link)
    old = ledger["blocks"].get(component)
    if not old:
        return {"scope": link["scope"], "path": str(ledger_path), "status": "missing"}
    if old["file"] not in {"AGENTS.md", "AGENTS.override.md"}:
        raise ValueError("Invalid entrance target")
    target = root / old["file"]
    content = plan.read(target)
    begin = f"<!-- feather-setup:{component}:begin -->".encode()
    end = f"<!-- feather-setup:{component}:end -->".encode()
    owner = str(environment.state_path) + "#" + component
    status = "installed"
    if content is None:
        status = "missing"
    elif (content.count(old["content"].encode()) != 1 or content.count(begin) != 1 or content.count(end) != 1
          or owner not in old["owners"]):
        status = "conflict"
    elif old["file"] == "AGENTS.md" and plan.read(root / "AGENTS.override.md") is not None:
        status = "shadowed"
    return {"scope": link["scope"], "path": str(target), "status": status, "version": old["version"],
            "load_condition": "Codex document limits, deeper instructions and project trust still apply"}


def attach(plan: Plan, environment: Environment, bundle: Bundle, component: str, record: dict,
           link: dict[str, str], replace: bool = False) -> dict:
    if record.get("entrance") and record["entrance"] != link:
        raise ValueError("Existing entrance is in another scope; remove it explicitly before changing scope")
    result = manage(plan, environment, bundle, component, link, replace=replace,
                    overrides=record.get("model_overrides"))
    record["entrance"] = link
    return result


def manage(plan: Plan, environment: Environment, bundle: Bundle, component: str,
           link: dict[str, str], remove: bool = False, replace: bool = False,
           transfer_to: Environment | None = None, overrides: dict | None = None) -> dict:
    root, ledger_path, ledger = load(plan, environment, link)
    scope = link["scope"]
    old = ledger["blocks"].get(component)
    owner = str(environment.state_path) + "#" + component
    override = root / "AGENTS.override.md"
    preferred = "AGENTS.override.md" if plan.read(override) is not None else "AGENTS.md"
    if old and old["file"] not in {"AGENTS.md", "AGENTS.override.md"}:
        raise ValueError("Invalid entrance target")
    filename = old["file"] if old else preferred
    target = root / filename
    if old and filename != preferred and not remove:
        raise ValueError(f"Conflict: {target} is now shadowed by {override}; preserve or remove the old managed entrance first")
    before = plan.read(target)
    current = before or b""
    begin = f"<!-- feather-setup:{component}:begin -->".encode()
    end = f"<!-- feather-setup:{component}:end -->".encode()
    block = b"\n\n" + begin + b"\n" + instruction(bundle, component, overrides).encode() + b"\n" + end + b"\n"
    if old:
        prior = old["content"].encode()
        if component == "delegation" and not remove and transfer_to is None and (len(old["owners"]) > 1 or owner not in old["owners"]):
            from .model_settings import values
            if values(prior.decode()) != values(block.decode()):
                raise ValueError(f"Delegation entrance cannot be shared or rewritten with different model defaults: {target}")
        if current.count(begin) != 1 or current.count(end) != 1 or current.count(prior) != 1:
            if current.count(begin) != 1 or current.count(end) != 1 or not replace:
                raise ConflictError(target, prior, current, None if remove else block)
            start, stop = current.index(begin), current.index(end) + len(end)
            if start >= stop:
                raise ConflictError(target, prior, current, None if remove else block)
            # Replace only the recognizable marker-bounded span; changed outside whitespace stays owned by the user.
            prior = current[start:stop]
            block = block.removeprefix(b"\n\n").removesuffix(b"\n")
        owners = set(old["owners"])
        if transfer_to is not None:
            if owner not in owners:
                raise ValueError(f"Missing entrance owner: {target}")
            owners.remove(owner)
            owners.add(str(transfer_to.state_path) + "#" + component)
            old["owners"] = sorted(owners)
        elif remove:
            if owner not in owners:
                raise ValueError(f"Missing entrance owner: {target}")
            owners.discard(owner)
            if owners:
                old["owners"] = sorted(owners)
            else:
                current = current.replace(prior, b"", 1)
                del ledger["blocks"][component]
        else:
            owners.add(owner)
            current = current.replace(prior, block, 1)
            old.update(content=block.decode(), owners=sorted(owners), version=bundle.version)
    elif remove:
        raise ValueError(f"Missing entrance ownership record: {target}")
    else:
        if begin in current or end in current:
            raise ValueError(f"Conflict: unowned Feather entrance: {target}")
        ledger.setdefault("created_files", {}).setdefault(filename, before is None)
        current += block
        ledger["blocks"][component] = {"file": filename, "content": block.decode(),
                                       "owners": [owner], "version": bundle.version}
    delete_empty = not current and ledger.get("created_files", {}).get(filename, False)
    if not any(record["file"] == filename for record in ledger["blocks"].values()):
        ledger.get("created_files", {}).pop(filename, None)
    plan.add(target, None if delete_empty else current)
    plan.add(ledger_path, (json.dumps(ledger, indent=2) + "\n").encode())
    return {"scope": scope, "path": str(target), "status": "removed" if remove else "managed",
            "load_condition": "Codex document limits, deeper instructions and project trust still apply"}
