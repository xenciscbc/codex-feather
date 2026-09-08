"""Resolve explicitly selected environments and verify the Codex executable."""
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

from .transaction import read_regular
from .bundle import relative_path


@dataclass(frozen=True)
class Environment:
    project: Path
    user_home: Path
    codex_home: Path
    scope: str = "project"

    @property
    def state_path(self) -> Path:
        return (self.project / ".feather/setup/state.json" if self.scope == "project"
                else self.codex_home / "feather-setup/state.json")

    @property
    def identity(self) -> dict[str, str]:
        return ({"scope": "project", "project": str(self.project)} if self.scope == "project"
                else {"scope": "user", "user_home": str(self.user_home), "codex_home": str(self.codex_home)})

    def target(self, relative: str) -> Path:
        path = relative_path(relative)
        if self.scope == "project":
            return self.project / path
        if path.parts[0] == ".codex":
            return self.codex_home.joinpath(*path.parts[1:])
        if path.parts[0] == ".agents":
            return self.user_home / path
        raise ValueError(f"Unexpected installation namespace: {relative}")

    def require_agents_enabled(self) -> None:
        enabled = True
        configs = [self.codex_home / "config.toml"]
        if self.scope == "project":
            configs.extend(root / ".codex/config.toml" for root in reversed(self.project_roots()))
        for config in configs:
            content = read_regular(config)
            if content is not None:
                parsed = tomllib.loads(content.decode("utf-8-sig"))
                enabled = parsed.get("agents", {}).get("enabled", enabled)
        if enabled is False:
            raise ValueError("Conflict: agents.enabled is explicitly false. Enable agents in your Codex settings before installing delegation; existing settings were preserved.")

    def project_roots(self) -> list[Path]:
        markers = [".git"]
        content = read_regular(self.codex_home / "config.toml")
        if content is not None:
            markers = tomllib.loads(content.decode("utf-8-sig")).get("project_root_markers", markers)
        roots = []
        for root in [self.project, *self.project.parents]:
            roots.append(root)
            if any((root / marker).exists() for marker in markers):
                return roots
        return [self.project]


def find_codex(explicit: str | None) -> dict:
    candidates = [Path(explicit)] if explicit else []
    if not explicit:
        found = shutil.which("codex.exe" if os.name == "nt" else "codex")
        if found:
            candidates.append(Path(found))
        if os.name == "nt":
            local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            candidates.extend(sorted((local / "OpenAI/Codex/bin").glob("*/codex.exe"), reverse=True))
        else:
            candidates.extend([Path.home() / ".local/bin/codex", Path("/usr/local/bin/codex")])
    for candidate in candidates:
        if not candidate.is_file() or (os.name == "nt" and candidate.suffix.lower() != ".exe"):
            continue
        try:
            result = subprocess.run([str(candidate.resolve()), "--version"],
                                    capture_output=True, text=True, encoding="utf-8", timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip().startswith("codex-cli "):
            return {"path": str(candidate.resolve()), "version": result.stdout.strip()}
    raise ValueError("No usable Codex found. Install Codex first, or pass --codex with its native executable; Feather does not install Codex or sign in.")
