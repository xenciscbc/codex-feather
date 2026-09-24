"""Read the versioned offline payload without trusting manifest paths."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import tomllib


ROLES = ("scout", "analyst", "mech-executor", "executor", "security-executor")
LEGACY_ROLES = ROLES[:-1]
HANDOFF_ROOT = ".agents/skills/handoff/"
LEGACY_HANDOFF_ROOT = ".agents/skills/feather-handoff/"
DELEGATION_SKILL = ".agents/skills/feather-delegation/SKILL.md"


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def relative_path(value: str) -> Path:
    path = PurePosixPath(value)
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
    if (not value or "\\" in value or ":" in value or path.is_absolute()
            or any(p in {"", ".", ".."} or p.rstrip(" .") != p or p.split(".")[0].upper() in reserved
                   or any(character in p for character in '<>"|?*') for p in value.split("/"))):
        raise ValueError(f"Unsafe relative path: {value}")
    return Path(*path.parts)


@dataclass(frozen=True)
class Bundle:
    root: Path
    version: str
    components: dict
    payload: dict[str, bytes]

    @classmethod
    def read(cls, root: Path):
        manifest = json.loads((root / "bundle.json").read_text(encoding="utf-8"))
        if manifest.get("format") != 1 or not isinstance(manifest.get("version"), str):
            raise ValueError("Unsupported Feather bundle")
        payload = {}
        for source, expected in manifest["files"].items():
            path = root / relative_path(source)
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"Bundle file escapes payload: {source}")
            payload[source] = path.read_bytes()
            if digest(payload[source]) != expected:
                raise ValueError(f"Bundle checksum mismatch: {source}")
        components = manifest["components"]
        if not isinstance(components, dict) or not components:
            raise ValueError("Bundle has no components")
        for name, component in components.items():
            if f"assets/templates/entrances/{name}.md" not in payload:
                raise ValueError(f"Incomplete {name} payload: entrance template is required")
            targets = list(component["files"].values())
            if len({target.casefold() for target in targets}) != len(targets):
                raise ValueError(f"Duplicate payload targets in {name}")
            if name == "handoff":
                if HANDOFF_ROOT + "SKILL.md" not in targets:
                    raise ValueError("Incomplete handoff payload: SKILL.md is required")
            elif name == "delegation":
                required = {f".codex/agents/{role}.toml" for role in ROLES} | {DELEGATION_SKILL}
                if set(targets) != required or "assets/templates/entrances/delegation.md" not in payload:
                    raise ValueError("Incomplete delegation payload: all five roles, runtime skill and guidance are required")
            else:
                raise ValueError(f"Unknown bundle component: {name}")
            for source, target in component["files"].items():
                if source not in manifest["files"]:
                    raise ValueError(f"Unverified payload: {source}")
                validate_target(name, target, bundled=True)
                if name == "delegation" and target == DELEGATION_SKILL:
                    if not payload[source].startswith(b"---\nname: feather-delegation\n"):
                        raise ValueError(f"Invalid delegation runtime skill: {source}")
                if name == "delegation" and target != DELEGATION_SKILL:
                    role = tomllib.loads(payload[source].decode("utf-8-sig"))
                    if role.get("name") != Path(target).stem or not role.get("description") or not role.get("developer_instructions"):
                        raise ValueError(f"Invalid native role payload: {source}")
        return cls(root, manifest["version"], components, payload)

    def files(self, component: str) -> dict[str, bytes]:
        return {target: self.payload[source]
                for source, target in self.components[component]["files"].items()}


def validate_target(component: str, target: str, *, bundled: bool = False) -> None:
    relative_path(target)
    if component == "handoff" and (target.startswith(HANDOFF_ROOT)
                                   or (not bundled and target.startswith(LEGACY_HANDOFF_ROOT))):
        return
    if component == "delegation" and target in ({f".codex/agents/{name}.toml" for name in ROLES} | {DELEGATION_SKILL}):
        return
    raise ValueError(f"Unexpected {component} destination: {target}")
