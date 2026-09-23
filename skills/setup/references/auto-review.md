# Automatic plan review mode

Use this procedure for `$auto-on` and `$auto-off`. The mode is a preference for future automatic review decisions, not authorization for implementation and not a runtime hook. The packaged default is `off`. An explicit request to review a particular plan applies in either mode.

## Scope

- No argument or `session`: set the preference in this conversation only. Make no file change and do not run the configuration tool. A review already running continues. A new session uses the saved mode.
- `project`: save the mode for the selected, existing project installation.
- `user`: save the mode for the selected, existing user installation. Project guidance may take precedence in a project with its own setting.

Accept an unambiguous equivalent scope in natural language. Clarify conflicting or unknown scope before writing. A toggle does not install Feather or take ownership of an installation. A recorded project setup may reuse user-installed roles while owning its own project entrance; in that case project policy changes that entrance only, not the user policy. Shared, missing or cross-scope entrances must be resolved through setup first. A persistent change does not erase a separately stated task or session preference unless the user explicitly asks for immediate effect too.

## Persistent change

Resolve the project root and plugin root from this reference. The tool is `../../../scripts/feather_review.py`. Use the actual absolute path and any explicit `--user-home` or `--codex-home`. Inspect the selected scope first:

```text
python "<feather_review.py>" show --project "<project>" --scope project
python "<feather_review.py>" preview --project "<project>" --scope project --review-mode auto
python "<feather_review.py>" apply --project "<project>" --scope project --review-mode auto --expected-plan "<preview-plan-id>"
```

Use `user` and `off` when those were selected. Summarize preview paths and before/after mode; apply the same arguments and exact returned plan ID. The explicit scoped command authorizes the setting change. On a conflict, preserve files and report the blocker. Read `show` afterward and report saved mode, scope and path. If no owned installation exists, report that setup is needed rather than installing it implicitly.

Auto mode triggers only for material security-boundary changes, data migrations, irreversible operations or complex cross-module work. Use a fresh analyst with a bounded stable plan. There are at most two automatic review calls total per logical plan, including failures or interrupted calls. READY permits already authorized work to proceed. REVISE identifies blockers to resolve; after a second automatic call, unresolved blockers stop dependent implementation until an explicit request permits further review. Preserve count, plan identity, verdicts and blockers in an existing active handoff. Session, reviewer, model, mode, name or cosmetic plan changes do not reset them. See the installed delegation guidance for full protocol.
