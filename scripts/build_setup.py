"""Build a complete offline Feather release for the current platform."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

from setup_installer import VERSION


ROOT = Path(__file__).resolve().parents[1]


def payload(destination: Path) -> None:
    shutil.copytree(ROOT / "templates", destination / "assets/templates")
    shutil.copytree(ROOT / "skills/feather-handoff", destination / "assets/skills/feather-handoff",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    files = {path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted((destination / "assets").rglob("*")) if path.is_file()}
    components = {"handoff": {"files": {source: source.replace("assets/skills/", ".agents/skills/", 1)
                                        for source in files if source.startswith("assets/skills/")}},
                  "delegation": {"files": {source: ".codex/agents/" + Path(source).name
                                            for source in files if source.startswith("assets/templates/") and source.endswith(".toml")}}}
    sources = [ROOT / "scripts/feather_setup.py", ROOT / "scripts/build_setup.py", *(ROOT / "scripts/setup_installer").glob("*.py")]
    try:
        git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
        revision = subprocess.run([*git, "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run([*git, "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                                    capture_output=True, text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    manifest = {"format": 1, "version": VERSION, "components": components, "files": files,
                "build": {"os": platform.system(), "architecture": platform.machine(),
                          "python": platform.python_version(), "libc": platform.libc_ver(),
                          "source_commit": revision, "tracked_worktree_changes": dirty,
                          "source_hashes": {source.relative_to(ROOT).as_posix(): hashlib.sha256(source.read_bytes()).hexdigest()
                                            for source in sorted(sources)}}}
    (destination / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (destination / "README.txt").write_text(
        f"Feather {VERSION}\n\nKeep this complete directory together. The installer requires no Python installation.\n"
        "The handoff skill's file tool requires Python 3.11+; ask before helping install a missing interpreter.\n"
        "Run feather-setup --help (feather-setup.exe on Windows) for commands.\n"
        "Codex must already be installed. The installer does not install Codex or sign in.\n"
        "The bundle's assets and version manifest are local; no per-component downloads occur.\n",
        encoding="utf-8")
    (destination / "docs").mkdir()
    for name in ["setup.md", "setup-validation.md"]:
        shutil.copyfile(ROOT / "docs" / name, destination / "docs" / name)
    with (destination / "README.txt").open("a", encoding="utf-8") as readme:
        readme.write("\nUsage and recovery guide: docs/setup.md\nValidation evidence and platform limits: docs/setup-validation.md\n"
                     "Start without an action for interactive guidance. Default project is the current working directory.\n"
                     "Example: feather-setup install --project /path/to/project --components all --scope project --entrance project --dry-run\n")


def build(output: Path, prepare_only: bool) -> None:
    if output.exists():
        raise ValueError(f"Output already exists; choose a fresh release directory: {output}")
    if platform.system() not in {"Windows", "Linux"} or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("First release supports Windows x64 and Linux x64 only")
    workspace = ROOT / ".scratch/feather-setup/build"
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-", dir=workspace) as temporary:
        staging = Path(temporary)
        if prepare_only:
            release = staging / "feather-setup"
            release.mkdir()
        else:
            command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--name", "feather-setup",
                       "--distpath", str(staging / "dist"), "--workpath", str(staging / "work"),
                       "--specpath", str(staging), "--paths", str(ROOT / "scripts"),
                       str(ROOT / "scripts/feather_setup.py")]
            subprocess.run(command, cwd=ROOT, check=True)
            release = staging / "dist/feather-setup"
        payload(release)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(release, output)
    if not prepare_only:
        archive_format = "zip" if os.name == "nt" else "gztar"
        archive = shutil.make_archive(str(output), archive_format, root_dir=output.parent, base_dir=output.name)
        checksum = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
        Path(archive + ".sha256").write_text(f"{checksum}  {Path(archive).name}\n", encoding="ascii")
    print(json.dumps({"output": str(output), "version": VERSION, "prepared_only": prepare_only}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / f"dist/feather-setup-{VERSION}-{platform.system().lower()}-x64")
    parser.add_argument("--prepare-only", action="store_true", help="Prepare payload for source-CLI development")
    args = parser.parse_args()
    try:
        build(args.output.resolve(), args.prepare_only)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
