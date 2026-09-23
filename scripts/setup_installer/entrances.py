"""Own bounded instruction blocks separately from the capability installation scope."""
import json
from pathlib import Path

from .bundle import Bundle
from .environment import Environment
from .transaction import Plan
from .conflicts import ConflictError


def instruction(bundle: Bundle, component: str, overrides: dict | None = None,
                review_mode: str | None = None) -> str:
    if component == "delegation":
        body = bundle.payload["assets/templates/AGENTS.md"].decode("utf-8-sig").strip()
        if overrides:
            from .model_settings import render
            body = render(body, overrides)
        if review_mode is not None:
            from .review_settings import render_mode
            body = render_mode(body, review_mode)
        guard = ("Apply this delegation guidance only when scout, analyst, mech-executor, executor and security-executor "
                 "are available in the current environment. If unavailable, report the missing capability "
                 "and keep the work with the main Agent. This declaration does not install or enable roles.")
    else:
        guard = ("Use this capability only when handoff or legacy feather-handoff is listed among the skills available in the "
                 "current environment. This declaration does not install the skill in other projects.")
        body = ("When the user requests a handoff or continuation of recorded work, read and follow the "
                "available handoff skill (or feather-handoff when only that legacy skill is available). Preserve its handoff-file and history rules. "
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


def model_entrance(owner: Environment, record: dict, plan: Plan):
    link = record.get("entrance")
    if not link:
        return None
    if link["scope"] != owner.scope or link["root"] != str(owner.project if owner.scope == "project" else owner.codex_home):
        raise ValueError("Delegation entrance scope differs from the owning installation. Move it to the owner scope with setup before changing permanent defaults")
    observed = inspect(owner, "delegation", link)
    if observed["status"] != "installed":
        raise ValueError(f"Managed delegation entrance is {observed['status']}: {observed['path']}; resolve it with setup")
    root, ledger_path, ledger = load(plan, owner, link)
    entry = ledger["blocks"]["delegation"]
    if entry["owners"] != [str(owner.state_path) + "#delegation"]:
        raise ValueError(f"Delegation entrance has shared owners: {ledger_path}; separate its ownership before changing defaults")
    target = root / entry["file"]
    return ledger_path, ledger, entry, target


def set_model_defaults(plan: Plan, owner: Environment, record: dict, overrides: dict) -> None:
    """Plan a model-table edit with the same entrance ownership and content checks."""
    from .model_settings import render
    entrance = model_entrance(owner, record, plan)
    if entrance is None:
        raise ValueError("No managed delegation entrance is active")
    _replace_content(plan, entrance, render(entrance[2]["content"], overrides))


def set_review_mode(plan: Plan, owner: Environment, record: dict, mode: str) -> None:
    from .review_settings import render_mode
    entrance = model_entrance(owner, record, plan)
    if entrance is None:
        raise ValueError("No managed delegation entrance is active")
    _replace_content(plan, entrance, render_mode(entrance[2]["content"], mode))


def _replace_content(plan: Plan, entrance: tuple, content: str) -> None:
    ledger_path, ledger, entry, target = entrance
    before_block = entry["content"].encode()
    after_block = content.encode()
    file_content = plan.read(target)
    if file_content is None or file_content.count(before_block) != 1:
        raise ValueError(f"Managed entrance changed: {target}")
    plan.add(target, file_content.replace(before_block, after_block, 1))
    entry["content"] = after_block.decode()
    plan.add(ledger_path, (json.dumps(ledger, indent=2) + "\n").encode())


def attach(plan: Plan, environment: Environment, bundle: Bundle, component: str, record: dict,
           link: dict[str, str], replace: bool = False) -> dict:
    if record.get("entrance") and record["entrance"] != link:
        raise ValueError("Existing entrance is in another scope; remove it explicitly before changing scope")
    result = manage(plan, environment, bundle, component, link, replace=replace,
                    overrides=record.get("model_overrides"),
                    allow_model_update=not record.get("reused"), review_mode=record.get("review_mode"))
    record["entrance"] = link
    return result


def manage(plan: Plan, environment: Environment, bundle: Bundle, component: str,
           link: dict[str, str], remove: bool = False, replace: bool = False,
           transfer_to: Environment | None = None, overrides: dict | None = None,
           allow_model_update: bool = False, review_mode: str | None = None) -> dict:
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
    block = b"\n\n" + begin + b"\n" + instruction(bundle, component, overrides, review_mode).encode() + b"\n" + end + b"\n"
    if old:
        prior = old["content"].encode()
        # Existing role owners can upgrade shared guidance; joining or reused owners
        # cannot replace its model table with defaults from a different bundle.
        if (component == "delegation" and not remove and transfer_to is None
                and (owner not in old["owners"] or (len(old["owners"]) > 1 and not allow_model_update))):
            from .model_settings import values
            from .review_settings import mode_value
            if mode_value(prior.decode()) != mode_value(block.decode()):
                raise ValueError(f"Delegation entrance cannot be shared or rewritten with different review modes: {target}")
            if values(prior.decode(), allow_legacy=True) != values(block.decode(), allow_legacy=True):
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
