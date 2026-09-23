# Feather lifecycle

## Existing standalone handoff

The plugin owns its cached skills; Feather setup owns only its recorded role files and guidance. Check the currently listed skills and their source paths. Also run setup `check --components all --project <project> --scope <scope> --json` for project and user scopes. Distinguish a standalone handoff deployment from plugin-backed maintenance guidance. File checks do not establish that the plugin skill loaded successfully.

If standalone and plugin handoff skills coexist, report both sources. Plugin `install --components handoff` manages guidance without copying the skill. It does not silently convert or remove an existing standalone deployment. Resolve that source before switching providers; a missing maintenance entrance is not a missing plugin skill.

An ordinary update request preserves the existing provider. For an owned standalone handoff, use the standalone installer's update procedure in [the installer guide](../../../docs/setup.md) at its owning scope; the plugin-backed update path is for maintenance guidance. If the required standalone bundle/tool is unavailable, report that blocker and continue any separately authorized delegation update. Ask about switching providers only when the user requests a switch or the desired source is unclear. “Update both” alone does not authorize deleting the standalone skill.

When the user requests switching to the plugin, first confirm the plugin handoff skill is available in a fresh session and its resources exist. Preview `remove --components handoff` at the standalone installation's owning scope, then apply within that authorization. The installer removes its managed handoff files and corresponding entrance, preserving handoff records and unrelated instructions. If the files are unowned or customized, preserve them and report the conflict instead of deleting them manually. A reused installation must be cleaned at its actual owning scope; check whether another installation still references its entrance.

After authorized legacy cleanup, install `--components handoff` to add plugin-backed maintenance guidance if selected. The plugin skill can still be invoked explicitly without that guidance. Delegation alone does not install a handoff entrance. Removing plugin-backed handoff configuration removes its owned guidance, not the plugin skill or handoff data.

## Change component scope

Use `migrate --components handoff|delegation|all --from project --to user` (or reverse) with the original project/home parameters. Preview first. Plugin-backed handoff migration transfers guidance ownership; delegation migration moves role files and ownership. Migration preserves installed content; it does not simultaneously update to the plugin's latest templates. Without `--entrance`, it preserves the existing guidance location; pass the destination entrance scope when the user also wants that moved. Follow with `update` at the destination if an upgrade was requested. Read the installer guide for customized-file conflicts.

## Remove

For a request to remove all Feather configuration, identify each component's managed scopes, preview and apply removal in each authorized scope. `remove --components all` removes both managed components in that scope. Use `handoff` or `delegation` when only one is requested, preserving the other's files, settings and guidance. Existing standalone handoff removal also deletes its owned skill files; include those paths in the preview and preserve customized content unless replacement was authorized.

Keep the plugin available until cleanup completes; then use the native plugin removal mechanism when the user requested uninstalling it. Removing the plugin does not call setup automatically. If the plugin is already gone, restore the complete plugin or use the standalone installer to perform owned-file cleanup. Preserve `.feather/handoffs/`, history and archives throughout.
