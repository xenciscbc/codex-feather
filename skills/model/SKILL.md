---
name: model
description: "Inspect or change Feather child-role models and reasoning effort. Guide session-only overrides or permanent settings in the owning project or user installation."
---

# Feather Model

Configure `scout`, `analyst`, `mech-executor`, `executor` and `security-executor` dispatch settings. Preserve their responsibilities, permissions, the main Agent's model and concurrency preferences. Use [model.py](scripts/model.py) for inspection and permanent writes; do not edit role TOMLs, managed guidance or ownership records manually. Resolve model and reasoning independently for each dispatch: applicable task instruction, then session override, saved setting and packaged default. A setting limited to the main Agent does not change children.

## Show, choose, then decide duration

1. Resolve the project and the absolute tool path from this skill's location. Run `show` with the actual project. Respect explicit `--user-home` and `--codex-home`; otherwise use the tool's environment defaults. Show a compact table of each role's current model and reasoning, and the owning installation's scope and path. Distinguish saved settings, packaged defaults when no managed entrance exists, applicable task settings and any explicit session overrides already in the conversation. Saved settings are not proof of a running child's model.
2. Ask which roles and fields the user wants to change, unless already supplied. Preserve each unspecified field independently. Check the requested combination against the current native tool's exposed models and supported reasoning levels. If unavailable or unconfirmed, explain the limitation before applying or dispatching; never silently substitute a model or effort. The script checks syntax, not provider availability.
3. Show the resulting before/after values. Then ask whether the change is **only for this session** or **permanent**, unless the user already chose. A duration choice is necessary because it determines whether files change. Explain the permanent target: a project reusing user-installed roles changes that shared user installation, affecting other projects using it. Do not offer an arbitrary target scope; moving an installation is a setup operation.

## Session only

Keep the chosen per-field overrides in the current conversation and pass both resolved model and reasoning explicitly through supported native spawn parameters for future named-role children. Use the native context inheritance mode compatible with those parameters. Keep the named role and its permissions. Do not call `apply` or write configuration, instructions, plugin cache or handoff files merely to store the preference. Existing children are unchanged. Report the resolved table and that the override lasts only for this session; do not claim a provider-level setting was changed.

## Permanent

Run `preview` with the chosen fields, show its actual target paths, before/after values and scope. After the user has selected permanent changes within that scope, run `apply` using the same arguments and the preview's plan identifier. Existing explicit authorization is sufficient; do not ask the duration question again. If the plan changes, preview again and reconcile the changed scope or values before applying.

```text
python "<model.py>" show --project "<project>"
python "<model.py>" preview --project "<project>" --set scout.model=gpt-6-luna --set scout.reasoning=medium
python "<model.py>" apply --project "<project>" --set scout.model=gpt-6-luna --set scout.reasoning=medium --expected-plan "<preview-plan-id>"
```

All commands return JSON. Repeat `--set ROLE.model=VALUE` or `--set ROLE.reasoning=VALUE` for the fields to change. Use actual paths and the returned identifier, not the example placeholders. After applying, run `show` again and report the saved values, affected scope and backup location. Fresh sessions load the changed guidance; keep any separately agreed session override explicit.

Permanent settings are recorded with the owning installation and survive supported setup updates and migrations. The tool updates managed guidance transactionally, preserving unrelated content and backing up changes. Model bindings stay out of role TOMLs so explicit native dispatch overrides remain possible.

If ownership, an entrance conflict or unsupported layout prevents a safe change, report the tool's blocker and next step without bypassing it. Use the available `setup` skill for installation repair or migration when authorized. A plugin-only install without deployed roles is not an owned role installation. Keep the complete plugin tree together; the script imports the root's installer modules and requires Python 3.11+ and PyYAML from `requirements-setup.txt`. Missing dependencies do not authorize installing packages.
