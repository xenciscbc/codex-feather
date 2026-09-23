---
name: setup
description: "Inspect and independently manage Feather handoff maintenance guidance and agent delegation (rules plus roles), individually or together. Set up, update, migrate, or remove selected components after plugin installation."
---

# Feather Setup

The plugin supplies `handoff`, `model`, `auto-on`, `auto-off` and this setup skill. Setup manages two independently selectable components:

| Component | What setup manages |
| --- | --- |
| `handoff` | Agent guidance to invoke the plugin's handoff skill and automatically maintain an existing work handoff at milestones, blockers and completion. The plugin supplies the skill; setup installs no duplicate standalone copy. |
| `delegation` | The five native role files and delegation guidance, including dispatch responsibilities and defaults. |

Choose either component or `all` for both. They can use different scopes and can be updated, migrated or removed separately. Native plugin installation alone writes neither component's external guidance nor the role files. Use the bundled [setup entry point](scripts/setup.py); it calls Feather's installer with ownership records, conflict checks, backups and rollback. Do not reproduce its writes with shell or editor commands. For changing role models or reasoning effort, use the available `model` skill; setup updates preserve its saved choices. For automatic plan review preferences, use [the review-mode procedure](references/auto-review.md).

## Resolve the request

- Establish the target project from the request or current workspace. Resolve all tool paths from this skill's location, not the target project's working directory. The complete plugin root is two directories above this `SKILL.md`; keep its `scripts/`, `templates/`, `docs/`, and all skills together.
- **Show status first:** run `check --components all` for the project and user scopes with the same project/home parameters. Summarize each component's installation source, managed guidance, scope and conflicts. Distinguish the plugin handoff skill's availability from whether its maintenance guidance is installed; role files from delegation guidance; and static checks from live session loading. A missing unselected component is information, not permission to install it. Preserve readable results when a check reports an error.
- After showing status, ask only for choices not already provided: operation (install/update/remove/migrate or inspect only), component (`handoff`, `delegation`, or both), and applicable scope. A bare setup request inspects first, then asks what to do; it does not default to installing delegation or both. “Only handoff” and “only delegation” constrain every mutation. A request for both in different scopes is handled as two separately previewed operations. Explicit complete requests proceed after inspection without asking the same choices again.
- User scope shares the selected configuration across projects; project scope limits deployment to one project. Existing records determine update/removal ownership; a reused component must be updated at its owning scope. `check` compares installed files with ownership records; it does not prove they match the new plugin payload. Use `update --dry-run` to inspect the new payload. Inspect-only requests stop after the status report.
- The source tool requires Python 3.11+ and PyYAML from the plugin's `requirements-setup.txt`. Reuse a suitable interpreter. If dependencies are missing, explain the requirement and obtain authorization for installation; do not install packages or download executables merely by loading this skill. Read-only file inspection remains possible.

## Apply and verify

Run commands with the actual absolute setup path and an explicit `--project`. These examples use placeholders, not literal paths:

```text
python "<setup.py>" check --project "<project>" --scope project --components all --json
python "<setup.py>" check --project "<project>" --scope user --components all --json
python "<setup.py>" install --project "<project>" --scope project --components handoff --dry-run --json
python "<setup.py>" install --project "<project>" --scope project --components handoff --json
python "<setup.py>" install --project "<project>" --scope user --components delegation --dry-run --json
python "<setup.py>" install --project "<project>" --scope user --components delegation --json
python "<setup.py>" update --project "<project>" --scope user --components delegation --dry-run --json
python "<setup.py>" remove --project "<project>" --scope project --components handoff --dry-run --json
```

Pass `--components` explicitly for every mutation; use `all` only when both were selected. Check defaults to both. Choose entrance scope separately when requested; otherwise a new installation's entrance follows its selected scope. An update preserves the recorded entrance when `--entrance` is omitted. A plugin handoff installation needs its maintenance entrance; a request for handoff without any guidance is already satisfied by the available plugin skill. Delegation may explicitly use `--entrance none` for roles only. Existing authorization to set up or update includes applying a clean preview within that scope; ask only about missing choices, destructive conflict replacement or required environment permission.

Before a mutation, summarize the concrete preview, selected components and affected scopes. If there is a conflict, preserve current files and show the reported difference. `--on-conflict replace` requires authorization to replace that custom content, even if an ordinary update was requested. Do not retry an unchanged conflict. After applying, check the selected components, verify the other component's configuration was preserved, and report the backup location. For delegation, inspect the installed role/default-model values. Keep missing roles, absent Codex, disabled agents and unconfirmed live loading distinct from success. Open a fresh session to load changed roles or instructions. The packaged review mode defaults to off; setup updates preserve a saved mode.

The entry point uses a temporary verified bundle and does not edit the plugin cache. It never changes the main model or concurrency settings. It accepts the existing installer's `--user-home`, `--codex-home`, `--codex`, `--from`, `--to`, and conflict options; it requires an explicit operation and supplies its own `--bundle`.

## Existing installations, migration and removal

Read [lifecycle guidance](references/lifecycle.md) when an existing standalone handoff skill is found, when scope must change, or when removing Feather. Read the plugin's [installer guide](../../docs/setup.md) for reported ownership, environment or recovery errors.

Plugin updates refresh plugin files, not external role TOMLs or `AGENTS.md`. Run setup `update` in every owning scope the user wants updated. Removing or disabling the plugin alone leaves those external files in place; clean up the authorized scopes with setup before uninstalling the plugin. Handoff records under `.feather/handoffs/` are user data and remain intact.
