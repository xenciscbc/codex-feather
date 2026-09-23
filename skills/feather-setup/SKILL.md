---
name: feather-setup
description: "Set up, check, update, migrate, or remove Feather roles and agent guidance after plugin installation. Resolve existing standalone Feather installations without duplicating handoff skills."
---

# Feather Setup

The plugin supplies `feather-handoff` and this setup skill. Native plugin installation does not deploy the four custom roles or write agent guidance. Use the bundled [setup entry point](scripts/setup.py) for those external files; it calls Feather's existing installer with ownership records, conflict checks, backups and rollback. Do not reproduce its writes with shell or editor commands.

## Resolve the request

- Establish the target project and requested operation. Resolve all tool paths from this skill's location, not the target project's working directory. The complete plugin root is two directories above this `SKILL.md`; keep its `scripts/`, `templates/`, `docs/`, and both skills together.
- Preserve scope and home choices already provided. User scope shares roles across projects; project scope limits the deployment to one project. For a new installation with no scope preference, ask which scope to use while doing read-only checks. Existing installation records determine update/removal ownership; do not silently move it.
- Inspect before changing: run `check` for the intended scope and read its component, entrance and runtime results. A reused component must be updated at its owning scope. `check` compares installed files with ownership records; it does not prove they match the new plugin payload. Use an `update --dry-run` to inspect the new payload.
- The source tool requires Python 3.11+ and PyYAML from the plugin's `requirements-setup.txt`. Reuse a suitable interpreter. If dependencies are missing, explain the requirement and obtain authorization for installation; do not install packages or download executables merely by loading this skill. Read-only file inspection remains possible.

## Apply and verify

Run commands with the actual absolute setup path and an explicit `--project`. These examples use placeholders, not literal paths:

```text
python "<setup.py>" check --project "<project>" --scope user --json
python "<setup.py>" install --project "<project>" --scope user --entrance user --dry-run --json
python "<setup.py>" install --project "<project>" --scope user --entrance user --json
python "<setup.py>" update --project "<project>" --scope user --dry-run --json
python "<setup.py>" update --project "<project>" --scope user --json
```

`delegation` is the default component. Choose entrance scope separately when requested; otherwise a new installation's entrance follows its selected scope. An update preserves the recorded entrance when `--entrance` is omitted. Respect a request for no entrance. Existing authorization to set up or update includes applying a clean preview within that scope; ask only about missing choices, destructive conflict replacement or required environment permission.

Before a mutation, summarize the concrete preview. If there is a conflict, preserve current files and show the reported difference. `--on-conflict replace` requires authorization to replace that custom content, even if an ordinary update was requested. Do not retry an unchanged conflict. After applying, run `check`, inspect the installed role/default-model values and report the backup location. Keep missing roles, absent Codex, disabled agents and unconfirmed live loading distinct from success. Open a fresh session to load changed roles or instructions.

The entry point uses a temporary verified bundle and does not edit the plugin cache. It never changes the main model or concurrency settings. It accepts the existing installer's `--user-home`, `--codex-home`, `--codex`, `--from`, `--to`, and conflict options; it requires an explicit operation and supplies its own `--bundle`.

## Existing installations, migration and removal

Read [lifecycle guidance](references/lifecycle.md) when an existing standalone handoff skill is found, when scope must change, or when removing Feather. Read the plugin's [installer guide](../../docs/setup.md) for reported ownership, environment or recovery errors.

Plugin updates refresh plugin files, not external role TOMLs or `AGENTS.md`. Run setup `update` in every owning scope the user wants updated. Removing or disabling the plugin alone leaves those external files in place; clean up the authorized scopes with setup before uninstalling the plugin. Handoff records under `.feather/handoffs/` are user data and remain intact.
