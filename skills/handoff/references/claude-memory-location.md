# Locate project memory

This is a read-only source-selection step for an explicitly requested project. Keep candidate directory metadata separate from memory contents: identify one source before reading any candidate's notes. Do not search personal memory or unrelated project content to guess an association.

## Resolve the project and configuration

1. Resolve the user-specified project path and verify it exists. For Git, use `git -C <project> rev-parse --show-toplevel`, `rev-parse --git-common-dir` and `worktree list --porcelain` as needed to distinguish the checkout from its shared repository. The first worktree-list entry identifies the main worktree; confirm it against the common-directory relationship rather than blindly using a launch subdirectory or linked checkout. A bare or unrecognizable layout remains unresolved. For a non-Git project, use the specified project root. Do not switch branches, initialize a repository, repair metadata or change global Git settings to make lookup succeed.
2. Establish the Claude configuration root from user-supplied launch context or observable `CLAUDE_CONFIG_DIR`; otherwise use the user's `~/.claude`. The current process's environment is evidence about this session, not proof of how a past Claude session was launched. Note the source of any override; use the observable default when nothing indicates a conflict, without demanding proof that hypothetical overrides do not exist.
3. Inspect only the settings needed to locate memory: applicable managed settings, known `--settings` launch input, project-local/shared settings and user settings under the selected Claude configuration root. Read the relevant keys, not unrelated secrets or entire settings in the result. Use established settings precedence to resolve ordinary overrides; different values at different priorities alone are not an ambiguity. Project/local settings must be known to be trusted/effective for that Claude source; an unknown trust state or unavailable higher-priority input that actually affects the choice leaves candidate locations to clarify.
4. Apply an effective `autoMemoryDirectory` as the custom source. Expand `~/` for the relevant user's home; its value must be absolute or home-relative. Report invalid, inaccessible or conflicting effective inputs rather than guessing their intent. Do not treat an invalid explicit setting as permission to scan defaults.

## Validate a default candidate

When no effective custom memory directory is indicated, the documented default is `<Claude config root>/projects/<project key>/memory/`. A launch-time `CLAUDE_CODE_PROJECT_DIR_NAME` paired with `CLAUDE_CONFIG_DIR` can supply the project key; confirm the applicable version and that the pair belongs to the specified source. An unpaired key or one merely written in a settings-file `env` block is not an established launch override.

For an ordinary untruncated key, the documented directory convention replaces each non-alphanumeric character in the absolute identity path with `-`; `/Users/me/proj` becomes `-Users-me-proj`. Apply it to the shared repository identity established above (or the non-Git root), then check actual directory metadata. This is candidate generation, not a collision-free inverse mapping. Account for case variants and aliases without selecting by newest timestamp.

The session-storage docs describe names longer than 200 characters as truncated with a hash. A matching prefix can find candidates but does not validate a hash or project association. If the applicable encoding/hash or platform normalization cannot be established, list candidate metadata and ask for selection or an explicit memory path; do not invent the suffix. Search names only beneath the selected configuration's `projects` directory, never memory contents across candidates.

If exactly one supported candidate is established, report the path and location evidence and return to the read flow. If several remain, list their paths and reasons and ask the user to choose; stop before reading their contents. If none can be established, report the actual checked configuration/project scope and invite an explicit memory path. Distinguish a missing memory directory from insufficient evidence to locate it. Known missing/unreadable settings or ambiguous project identity must remain visible in that report.

## Version-sensitive reference

Checked against official documentation on 2026-09-10; recheck these sources when installed behavior or observed settings conflict. A stale search snippet is not a reason to override the current primary page.

- [Memory storage](https://code.claude.com/docs/en/memory#storage-location): default location, repository/worktree sharing, non-Git roots, custom memory directories and workspace trust for project/local settings.
- [Settings precedence](https://code.claude.com/docs/en/settings#settings-precedence): managed > launch arguments > project-local > shared project > user for an applicable key.
- [Environment variables](https://code.claude.com/docs/en/env-vars): configuration-root override and launch-only project-directory naming, including version requirements.
- [SDK session storage](https://code.claude.com/docs/en/agent-sdk/sessions): path-derived directory naming and long-name truncation apply to session storage; combine with memory's repository-scoping rule rather than substituting a session launch directory for the shared memory identity. Windows case/Unicode and collision behavior need evidence, not an invented universal conversion.
- [Git worktree list](https://git-scm.com/docs/git-worktree): main-worktree ordering and common/private metadata relationships used for the read-only identity check.
