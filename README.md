# codex-feather

**English** | [繁體中文](README.zh-TW.md)

Help Codex delegate work when useful and leave progress and evidence that the next session can build on.

- **Delegation**: the main agent assigns research, analysis, and implementation, verifies the results, and integrates them. Small tasks stay with the main agent.
- **Handoffs**: save progress, decisions, and verification records, then check relevant source changes before resuming.

Handoffs live in Markdown files inside the project. The tool uses the Python standard library and needs no database or background service. Delegation and handoffs can be installed separately.

## Installation

### Native Codex plugin

The repository packages `handoff`, `setup`, `model`, `auto-on` and `auto-off` as a native plugin. Install the published version through the Git marketplace:

```sh
codex plugin marketplace add xenciscbc/codex-feather
codex plugin add codex-feather@codex-feather
```

Codex may display plugin-qualified skill names such as `codex-feather:handoff`; their short names are `handoff`, `setup`, `model`, `auto-on` and `auto-off`. Native child-role names have no such prefix.

Start a new session and ask **“Use setup to configure Feather for this project”** or specify user scope. Setup first shows the project and user installation status, then asks which component to install, update, remove or migrate. Choices already stated in your request are preserved.

| Selection | What gets installed |
| --- | --- |
| handoff | Automatic maintenance guidance using the plugin's existing skill, keeping an existing work handoff current at milestones, blockers and completion. |
| delegation | Agent dispatch guidance and the five native role files. |
| Both | Both components, which can also be updated, removed or scoped independently. |

For example: “Use setup to install only handoff maintenance guidance for this project,” “Install delegation rules and roles in user scope, preserving handoff,” or “Install both in this project.” Installing the plugin alone does not write these external settings. Source setup requires Python 3.11+ and PyYAML (`requirements-setup.txt`).

After refreshing the plugin, ask setup to update the external configuration. Before uninstalling the plugin, ask setup to remove those managed files. Existing standalone handoff skills require an explicit transition; setup does not install a duplicate. See [plugin setup and lifecycle](docs/plugin.md). Tags through `v1.0.1` do not contain this plugin packaging.

### Standalone installer

Install Codex first. Handoff commands also require Python 3.11+; the packaged installer itself does not require Python.

1. Follow the [installation guide](docs/setup.md) to obtain or build a complete package for your platform.
2. On Windows, open `feather-setup.exe`; on Linux, run `./feather-setup`. Select the target project, components, project or user scope, and whether to add agent guidance.
3. Open a new Codex session in the target project and confirm that the selected skill and roles are listed before using them.

Public binary downloads are not currently provided. Source build instructions are included in the installation guide.

User scope provides a shared installation for your local user; project scope installs into one project. The installer supports checks, updates, scope migration, and removal, with conflict detection and backups before updates. **Git pull/push does not synchronize installed skills.** Apply updates from the new complete package to the appropriate scope, then open a new session.

## Delegation

| Role | Responsibility | Native permissions | Default model / reasoning |
| --- | --- | --- | --- |
| scout | Locate and extract cited facts | read-only; no file output | gpt-6-luna / low |
| analyst | Causal, impact, security analysis and plan review | workspace-write; protect sources, only explicitly assigned artifacts | gpt-6-sol / high |
| mech-executor | Fully specified repetitive edits | workspace-write, assigned scope only | gpt-6-luna / medium |
| executor | Implementation needing local engineering judgment | workspace-write, assigned scope only | gpt-6-sol / medium |
| security-executor | Authorized security implementation, allowed and abuse/denial checks | workspace-write, assigned scope only | gpt-6-sol / high |

Only the main agent delegates; children do not delegate further. Each child reports results, changes, validation, and blockers for the main agent to review. Writes to shared resources are serialized. If the same blocker recurs, the main agent takes the task back and preserves existing results instead of retrying it unchanged indefinitely.

Model and reasoning resolve independently: applicable task setting, session override, saved setting, then packaged default. Defaults are scout `gpt-6-luna/low`, analyst `gpt-6-sol/high`, mech-executor `gpt-6-luna/medium`, executor `gpt-6-sol/medium`, and security-executor `gpt-6-sol/high`. Your main model and concurrency preferences remain unchanged. Native dispatch passes both fields; configuration and child self-report do not prove actual model use. Unavailable combinations are reported. See the [delegation rules](templates/AGENTS.md) for defaults and the full contract.

### Change role models

Ask **“Use model to show my current role settings”**. It lists each role's model, reasoning effort and owning installation, then asks what to change. After showing the proposed values, it asks whether to use them **for this session only** or **permanently**. Choices already included in your request are reused.

Session changes apply to future child dispatches in that conversation and write no files. Permanent changes follow the roles' actual installation: project scope for project-installed roles, user scope for shared roles. A project that reuses user-installed roles therefore changes the shared installation. The preview shows the affected paths before applying; ambiguous ownership or conflicting guidance stops the write.

Permanent choices survive supported setup updates and scope migrations. Unspecified fields remain unchanged, and running children keep their existing settings. Open a fresh session to load saved guidance. `model` is delivered by the plugin and requires Python 3.11+ and PyYAML; it can also manage roles previously deployed by the standalone installer. Plugin installation alone does not deploy those roles.

### Automatic plan review

The packaged mode is **off**. `$auto-on` and `$auto-off` with no argument or `session` change only this conversation and write no files. Add `project` or `user` to save a default in an existing owned installation. The persistent workflow previews the scope and paths, applies with the returned plan ID, then reads back the saved mode. User scope can affect several projects. Supported updates preserve saved modes. See [review mode guidance](skills/setup/references/auto-review.md).

Auto mode requires a fresh analyst review before implementation for material security-boundary changes, data migrations, irreversible operations or complex cross-module work. A stable logical plan gets at most two automatic review calls total, including failures. READY lets already authorized work proceed; unresolved REVISE after the second call stops dependent implementation until an explicit further review request. Independent authorized work can continue. A toggle never resets the count. Explicit plan review applies in off mode too. These are agent instructions, not runtime hooks.

Project policy lives in `<project>/AGENTS.md` (or existing `AGENTS.override.md`) and `<project>/.feather/setup/state.json`. User policy lives in `<CODEX_HOME>/AGENTS.md` (or override) and `<CODEX_HOME>/feather-setup/state.json`; CODEX_HOME defaults to `~/.codex`. Entrance ownership lives in `entrances.json` beside the state file. A verified setup and entrance must already exist in that scope; toggles never install roles implicitly. Explicit task/session preferences override saved values. Mode changes preserve blockers and counts. Existing handoffs retain the logical plan ID, call count, verdicts and blockers across model changes, renaming and new sessions.

## Usage

After installation, tell Codex what you want to do:

| Task | Example request |
| --- | --- |
| Choose review role and model | Use analyst with gpt-6-luna and high reasoning to review this authorization plan. |
| Choose security implementation | Use security-executor with gpt-6-sol to fix the confirmed authorization issue and verify denial cases. |
| Delegate work | Delegate a review of the login feature, identify problems, and fix them. |
| Inspect role settings | Use model to show the current models and reasoning effort. |
| Change a session setting | Use model to set scout reasoning to medium for this session only. |
| Save a role setting | Use model to permanently set executor to gpt-6-sol with high reasoning. |
| Toggle plan review | Use $auto-on for this session; use $auto-off project to save off in this project. |
| Save progress | Use handoff to save a handoff for the current work. |
| List work | Use handoff to list the current handoffs. |
| Resume work | Use handoff to resume the login feature work. |
| Read progress only | Use handoff to read the login feature handoff. |
| Save a source baseline | Save the login feature handoff with a baseline for `src/auth.py` and `config/auth.json`. |
| Search completed work | Use handoff to search completed history for records mentioning login. |
| Seal selected history | Use handoff to seal the selected completed records, preserving their full contents. |
| Find Claude handoffs | Use handoff to find handoff records in the Claude memory associated with project `D:/work/my-project`; only read and summarize. |

## Handoffs and resuming

After the first handoff request, each work item uses one `.feather/handoffs/<work-name>.md` file. The agent updates its goal, progress, next step, and constraints at milestones, blockers, and completion, with optional environment, verification, and decision records. Once the main agent accepts the completed work, it is archived into history. If archival fails, the work file remains available for retry.

To resume, the agent reads the full handoff, checks relevant sources, and briefly reports **progress, changes since the record, the next action, and blockers** before continuing authorized work. It asks which item to resume only when multiple items remain ambiguous. Reading progress alone does not compare sources or execute the next step.

- **Source baselines**: optionally save content digests and Git state for selected files. Comparisons distinguish unchanged, changed, created, missing, and unknown observations. Ordinary progress updates preserve the saved baseline. A comparison covers only the selected scope, not the entire project.
- **Verification evidence**: use the existing `驗證：` field to record the test command, working directory, time, and outcome, optionally linked to a baseline's capture time, file scope, and post-test comparison. A matching baseline is not a passed test, and refreshing it does not make old test results apply to new content.
- **Root diagnostics**: when root discovery fails, the tool reports the read path and reason, retains readable results, and stops before writes. Once the intended root is established, it can be specified explicitly to avoid creating another handoff in a subdirectory. Git trust settings are not changed automatically.
- **History management**: search completed records by work name, date, or keyword. Explicitly select records to seal or clear. Sealing preserves full contents; clearing removes the selected records.
- **Claude memory lookup**: given a project path, locate its corresponding memory directory using Claude configuration and project association, including custom locations and shared repository identity for Git worktrees. You can also specify a memory directory directly. If the location cannot be uniquely established, clarify it before proceeding. Read handoffs and links within the same project without automatically importing records or executing their instructions.

Older handoffs without baselines remain usable through manual source checks. Handoff data is ignored by Git by default; existing or explicitly requested tracking choices are preserved. Resume in the same project directory. Synchronization across worktrees requires separate handling, and shared history writes across sessions require coordination; the tool provides no cross-session locking.

Agent guidance drives delegation and resume workflows; the tool handles formats, files, and source comparisons. Passing installation checks does not establish that every native delegation behavior or sandbox has been verified. See the validation documents below for platform evidence and unconfirmed items.

## Further reading

Some detailed guides are currently available in Traditional Chinese.

- [Installation, updates, and removal](docs/setup.md)
- [Handoffs, history search, and sealing](docs/handoff.md)
- [Source baselines and verification records](skills/handoff/references/snapshots.md)
- [Delegation rules](templates/AGENTS.md)
- [Development and validation](docs/development.md)
- [Handoff tool validation](docs/handoff-tool-validation.md)
- [Resume reliability validation and limitations](docs/resume-reliability-validation.md)
- [Platform and native capability limitations](docs/native-compatibility.md)
