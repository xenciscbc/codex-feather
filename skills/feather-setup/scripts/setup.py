"""Run Feather's owned-file installer from a native plugin, without writing its cache."""
import argparse
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__, add_help=False, allow_abbrev=False)
    parser.add_argument("action", choices=["install", "check", "update", "remove", "migrate"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--components", nargs="+", choices=["delegation", "handoff", "all"], default=["delegation"])
    parser.add_argument("--bundle")
    parser.add_argument("--interactive", action="store_true")
    if sys.version_info < (3, 11):
        print(json.dumps({"error": "Feather setup requires Python 3.11 or newer."}), file=sys.stderr)
        return 1
    if any(arg in {"--help", "-h"} for arg in sys.argv[1:]):
        parser.print_help()
        print("Also accepts installer options: --scope project|user, --entrance none|project|user, "
              "--user-home, --codex-home, --codex, --dry-run, --json, "
              "--from project|user, --to project|user, --on-conflict fail|keep|replace.")
        return 0
    args, _ = parser.parse_known_args()
    if args.bundle is not None or args.interactive:
        parser.error("The plugin supplies its own bundle; choose an explicit operation without --bundle or --interactive.")
    if args.action not in {"check", "remove"} and args.components != ["delegation"]:
        parser.error("The plugin supplies feather-handoff. Only delegation can be installed, updated or migrated here. "
                     "Use handoff check/remove solely for an existing standalone installation.")
    try:
        import yaml  # type: ignore[import-untyped]  # Required by installer skill discovery.
    except ImportError:
        print(json.dumps({"error": "Feather setup requires PyYAML in this Python environment.",
                          "next_step": "Install requirements-setup.txt from this plugin using an approved Python environment, then retry."}),
              file=sys.stderr)
        return 1
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_setup import payload
    from setup_installer.cli import main as installer_main
    try:
        with tempfile.TemporaryDirectory(prefix="feather-plugin-setup-") as directory:
            bundle = Path(directory)
            payload(bundle)
            manifest_path = bundle / "bundle.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            plugin = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
            manifest["version"] = plugin["version"]
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            arguments = [*sys.argv[1:], "--bundle", str(bundle)]
            if not any(arg == "--components" or arg.startswith("--components=") for arg in sys.argv[1:]):
                arguments.extend(["--components", "delegation"])
            return installer_main(arguments)
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"error": str(error), "next_step": "Restore or reinstall the complete Feather plugin; preserve target configuration."}),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
