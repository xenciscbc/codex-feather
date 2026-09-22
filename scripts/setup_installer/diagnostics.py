"""Read-only environment checks; file and configuration evidence is not live loading."""
from pathlib import Path
import tomllib

from .bundle import ROLES
from .environment import Environment, find_codex
from .transaction import read_regular


def inspect(environment: Environment, components: dict, codex: str | None) -> dict:
    result: dict = {}
    try:
        result["codex"] = {"status": "available", **find_codex(codex)}
    except (OSError, ValueError) as error:
        result["codex"] = {"status": "unavailable", "message": str(error)}
    if "delegation" in components:
        try:
            setting = environment.agents_setting()
            result["agents"] = {"status": "disabled" if setting["enabled"] is False else "not-disabled", **setting}
        except (OSError, ValueError) as error:
            result["agents"] = {"status": "invalid", "message": str(error)}
        issues = []
        paths = components["delegation"].get("paths", [])
        found = set()
        for filename in paths:
            path = Path(filename)
            try:
                content = read_regular(path)
                if content is None:
                    issues.append(f"Missing role: {path}")
                    continue
                role = tomllib.loads(content.decode("utf-8-sig"))
                if role.get("name") != path.stem or path.stem not in ROLES:
                    issues.append(f"Role identity does not match its filename: {path}")
                elif not all(isinstance(role.get(field), str) and role[field].strip()
                             for field in ["description", "developer_instructions"]):
                    issues.append(f"Role requires description and developer_instructions: {path}")
                else:
                    found.add(path.stem)
                if "model" in role or "model_reasoning_effort" in role:
                    issues.append(f"Role locks dispatch settings; update the owning installation and open a fresh session: {path}")
            except (OSError, ValueError) as error:
                issues.append(f"Cannot validate role {path}: {error}")
        if set(ROLES) != found:
            issues.append("A complete valid set of four Feather roles was not found")
        result["roles"] = {"status": "conflict" if issues else "compatible", "paths": paths, "issues": issues}
    result["session"] = {
        "status": "unconfirmed",
        "message": "Open a fresh Codex session after install/update/migrate and confirm the selected capabilities are listed. "
                   "This check does not establish live loading, model availability, project trust, or sandbox enforcement.",
    }
    return result
