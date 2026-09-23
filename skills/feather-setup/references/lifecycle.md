# Feather lifecycle

## Existing standalone handoff

The plugin owns its cached skills; Feather setup owns only files recorded by the installer. Check the currently listed skills and their source paths. Also run setup `check --components handoff --project <project> --scope <scope> --json` for applicable project/user scopes. That check sees standalone installations, not whether the plugin skill loaded successfully.

If standalone and plugin handoff skills coexist, report both sources. Do not install another copy or treat `missing` for standalone handoff as a missing plugin skill. The plugin wrapper rejects handoff install/update/migrate; its handoff check/remove modes exist only for legacy cleanup.

When the user requests switching to the plugin, first confirm the plugin handoff skill is available in a fresh session and its resources exist. Preview `remove --components handoff` at the standalone installation's owning scope, then apply within that authorization. The installer removes its managed handoff files and corresponding entrance, preserving handoff records and unrelated instructions. If the files are unowned or customized, preserve them and report the conflict instead of deleting them manually. A reused installation must be cleaned at its actual owning scope; check whether another installation still references its entrance.

The plugin handoff skill is discovered through its description and can be invoked explicitly. Removing the legacy handoff entrance means the old always-loaded handoff pointer is also removed; plugin discovery is the replacement, not an identical `AGENTS.md` deployment. Do not claim a handoff entrance was installed by delegation setup.

## Change role scope

Use the entry point's `migrate --from project --to user` (or reverse) with the original project/home parameters. Preview first. Migration preserves installed bytes; it does not simultaneously update to the plugin's latest templates. Follow with `update` at the destination if the user also requested an upgrade. Read the installer guide for entrance scope changes and customized-file conflicts.

## Remove

For a request to remove all Feather configuration, identify the managed scopes, preview and apply delegation removal in each authorized scope. If legacy standalone handoff is also present and removal is authorized, remove that component too. The wrapper supports `remove --components all` for both managed components, but use the narrow selection when only roles are requested.

Keep the plugin available until cleanup completes; then use the native plugin removal mechanism when the user requested uninstalling it. Removing the plugin does not call setup automatically. If the plugin is already gone, restore the complete plugin or use the standalone installer to perform owned-file cleanup. Preserve `.feather/handoffs/`, history and archives throughout.
