"""Find existing capabilities before creating a second visible installation."""
from dataclasses import replace
import tomllib

from .bundle import ROLES
from .environment import Environment
from .transaction import read_regular


def reuse_candidate(environment: Environment, component: str, ignore: Environment | None = None) -> dict | None:
    candidates = [replace(environment, scope="user")]
    candidates.extend(replace(environment, scope="project", project=root) for root in environment.project_roots())
    identities = ([".agents/skills/feather-handoff/SKILL.md"] if component == "handoff"
                  else [f".codex/agents/{role}.toml" for role in ROLES])
    found = []
    for other in candidates:
        if ignore and other.identity == ignore.identity:
            continue
        if component == "delegation":
            role_directory = other.target(".codex/agents/scout.toml").parent
            for file in role_directory.glob("*.toml"):
                content = read_regular(file)
                if content is None:
                    continue
                declared = tomllib.loads(content.decode("utf-8-sig")).get("name")
                if declared in ROLES and file.name != f"{declared}.toml":
                    raise ValueError(f"Conflict: native role {declared} is already declared by {file}. Resolve the identity collision before installing.")
        paths = [other.target(identity) for identity in identities]
        if paths == [environment.target(identity) for identity in identities]:
            continue
        present = [path for path in paths if read_regular(path) is not None]
        if not present:
            continue
        if len(present) != len(paths):
            raise ValueError(f"Conflict: partial {component} installation in {other.scope} scope. Resolve it or explicitly migrate; no duplicate was installed.")
        found.append({"status": "reused", "scope": other.scope, "project": str(other.project),
                      "paths": [str(path) for path in paths],
                      "message": "Using the existing capability. Changing its scope requires an explicit migration."})
    if found and (len(found) > 1 or any(read_regular(environment.target(identity)) is not None for identity in identities)):
        raise ValueError(f"Conflict: {component} exists in multiple visible scopes. Choose an explicit migration; no copies were changed.")
    return found[0] if found else None
