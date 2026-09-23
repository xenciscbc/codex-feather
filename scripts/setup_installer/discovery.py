"""Find existing capabilities before creating a second visible installation."""
from dataclasses import replace
import os
from pathlib import Path
import tomllib
import yaml  # type: ignore[import-untyped]

from .bundle import HANDOFF_ROOT, LEGACY_HANDOFF_ROOT, LEGACY_ROLES, ROLES
from .environment import Environment
from .transaction import read_regular, validate_regular


def skill_name(content: bytes) -> str | None:
    try:
        lines = content.decode("utf-8-sig").splitlines()
        if not lines or lines[0].strip() != "---":
            return None
        stop = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
        if stop is None:
            return None
        metadata = yaml.safe_load("\n".join(lines[1:stop]))
        name = metadata.get("name") if isinstance(metadata, dict) else None
        return name if isinstance(name, str) else None
    except (UnicodeError, yaml.YAMLError, RecursionError):
        return None  # Invalid skill metadata is not a native identity.


def skill_files(root: Path):
    seen = set()
    for directory, children, files in os.walk(root, followlinks=True):
        resolved = Path(directory).resolve()
        if resolved in seen:
            children[:] = []
        else:
            seen.add(resolved)
        if "SKILL.md" in files:
            yield Path(directory) / "SKILL.md"


def reuse_candidate(environment: Environment, component: str, ignore: Environment | None = None,
                    owned: set[str] | None = None) -> dict | None:
    candidates = [replace(environment, scope="user")]
    candidates.extend(replace(environment, scope="project", project=root) for root in environment.project_roots())
    identities = ([HANDOFF_ROOT + "SKILL.md"] if component == "handoff"
                  else [f".codex/agents/{role}.toml" for role in ROLES])
    owned = owned or set()
    found = []
    for other in candidates:
        if component == "handoff":
            canonical = other.target(HANDOFF_ROOT + "SKILL.md")
            legacy = other.target(LEGACY_HANDOFF_ROOT + "SKILL.md")
            for file in skill_files(canonical.parent.parent):
                if file == canonical or file == legacy:
                    continue
                # These are discovery inputs, never mutation targets; existing linked skills may be read.
                if skill_name(file.read_bytes()) in {"handoff", "feather-handoff"}:
                    raise ValueError(f"Conflict: native handoff skill is already declared by {file}. Resolve the identity collision; no duplicate was installed.")
            legacy_present = validate_regular(legacy)
            canonical_present = validate_regular(canonical)
            if legacy_present and canonical_present:
                raise ValueError(f"Conflict: legacy and current handoff skills are both visible in {other.scope} scope")
            if legacy_present and (other.identity != environment.identity or LEGACY_HANDOFF_ROOT + "SKILL.md" not in owned):
                if skill_name(read_regular(legacy) or b"") != "feather-handoff":
                    raise ValueError(f"Conflict: existing skill has missing or different native identity: {legacy}")
        if component == "delegation":
            role_directory = other.target(".codex/agents/scout.toml").parent
            for file in role_directory.glob("*.toml"):
                content = read_regular(file)
                if content is None:
                    continue
                declared = tomllib.loads(content.decode("utf-8-sig")).get("name")
                if declared in ROLES and file.name != f"{declared}.toml":
                    raise ValueError(f"Conflict: native role {declared} is already declared by {file}. Resolve the identity collision before installing.")
        # Migration excludes its canonical source files, but unowned aliases still conflict.
        if ignore and other.identity == ignore.identity:
            continue
        if other.identity == environment.identity:
            if component == "handoff" and legacy_present and LEGACY_HANDOFF_ROOT + "SKILL.md" not in owned:
                raise ValueError(f"Conflict: unowned legacy handoff skill: {legacy}")
            continue
        paths = [other.target(identity) for identity in identities]
        if component == "handoff" and legacy_present:
            paths = [legacy]
        present = [path for path in paths if read_regular(path) is not None]
        if not present:
            continue
        if component == "handoff" and skill_name(read_regular(present[0]) or b"") != ("feather-handoff" if legacy_present else "handoff"):
            raise ValueError(f"Conflict: existing skill has missing or different native identity: {present[0]}")
        if component == "delegation" and len(present) == len(LEGACY_ROLES) and all(
                other.target(f".codex/agents/{role}.toml") in present for role in LEGACY_ROLES):
            paths = present  # A complete legacy role set is reusable until its owning scope is updated.
        elif len(present) != len(paths):
            raise ValueError(f"Conflict: partial {component} installation in {other.scope} scope. Resolve it or explicitly migrate; no duplicate was installed.")
        found.append({"status": "reused", "scope": other.scope, "project": str(other.project),
                      "paths": [str(path) for path in paths],
                      "message": "Using the existing capability. Changing its scope requires an explicit migration."})
    local_identities = [*identities, LEGACY_HANDOFF_ROOT + "SKILL.md"] if component == "handoff" else identities
    if found and (len(found) > 1 or any(read_regular(environment.target(identity)) is not None
                                       for identity in local_identities)):
        raise ValueError(f"Conflict: {component} exists in multiple visible scopes. Choose an explicit migration; no copies were changed.")
    return found[0] if found else None
