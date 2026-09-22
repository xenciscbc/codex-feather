# codex-feather

**English** | [繁體中文](README.zh-TW.md)

Help Codex delegate work when useful and leave progress and evidence that the next session can build on.

- **Delegation**: the main agent assigns research, analysis, and implementation, verifies the results, and integrates them. Small tasks stay with the main agent.
- **Handoffs**: save progress, decisions, and verification records, then check relevant source changes before resuming.

Handoffs live in Markdown files inside the project. The tool uses the Python standard library and needs no database or background service. Delegation and handoffs can be installed separately.

## Installation

Install Codex first. Handoff commands also require Python 3.11+; the packaged installer itself does not require Python.

1. Follow the [installation guide](docs/setup.md) to obtain or build a complete package for your platform.
2. On Windows, open `feather-setup.exe`; on Linux, run `./feather-setup`. Select the target project, components, project or user scope, and whether to add agent guidance.
3. Open a new Codex session in the target project and confirm that the selected skill and roles are listed before using them.

Public binary downloads are not currently provided. Source build instructions are included in the installation guide.

User scope provides a shared installation for your local user; project scope installs into one project. The installer supports checks, updates, scope migration, and removal, with conflict detection and backups before updates. **Git pull/push does not synchronize installed skills.** Apply updates from the new complete package to the appropriate scope, then open a new session.

## Delegation

| Role | Responsibility |
| --- | --- |
| scout | Find locations and extract content without writing files; return facts with references. |
| analyst | Analyze logic, contradictions, and impacts while preserving sources; write a separate analysis artifact only when assigned. |
| mech-executor | Apply repetitive edits from a complete specification. |
| executor | Implement changes that require local design or engineering judgment. |

Only the main agent delegates; children do not delegate further. Each child reports results, changes, validation, and blockers for the main agent to review. Writes to shared resources are serialized. If the same blocker recurs, the main agent takes the task back and preserves existing results instead of retrying it unchanged indefinitely.

You can specify a child's model or reasoning effort; unspecified settings use role defaults. Your main model and concurrency preferences remain unchanged. Unavailable capabilities or model combinations are reported. See the [delegation rules](templates/AGENTS.md) for defaults and the full contract.

## Usage

After installation, tell Codex what you want to do:

| Task | Example request |
| --- | --- |
| Delegate work | Delegate a review of the login feature, identify problems, and fix them. |
| Save progress | Use feather-handoff to save a handoff for the current work. |
| List work | Use feather-handoff to list the current handoffs. |
| Resume work | Use feather-handoff to resume the login feature work. |
| Read progress only | Use feather-handoff to read the login feature handoff. |
| Save a source baseline | Save the login feature handoff with a baseline for `src/auth.py` and `config/auth.json`. |
| Search completed work | Use feather-handoff to search completed history for records mentioning login. |
| Seal selected history | Use feather-handoff to seal the selected completed records, preserving their full contents. |
| Find Claude handoffs | Use feather-handoff to find handoff records in Claude memory at `D:/work/my-project-memory`; only read and summarize. |

## Handoffs and resuming

After the first handoff request, each work item uses one `.feather/handoffs/<work-name>.md` file. The agent updates its goal, progress, next step, and constraints at milestones, blockers, and completion, with optional environment, verification, and decision records. Once the main agent accepts the completed work, it is archived into history. If archival fails, the work file remains available for retry.

To resume, the agent reads the full handoff, checks relevant sources, and briefly reports **progress, changes since the record, the next action, and blockers** before continuing authorized work. It asks which item to resume only when multiple items remain ambiguous. Reading progress alone does not compare sources or execute the next step.

- **Source baselines**: optionally save content digests and Git state for selected files. Comparisons distinguish unchanged, changed, created, missing, and unknown observations. Ordinary progress updates preserve the saved baseline. A comparison covers only the selected scope, not the entire project.
- **Verification evidence**: use the existing `驗證：` field to record the test command, working directory, time, and outcome, optionally linked to a baseline's capture time, file scope, and post-test comparison. A matching baseline is not a passed test, and refreshing it does not make old test results apply to new content.
- **Root diagnostics**: when root discovery fails, the tool reports the read path and reason, retains readable results, and stops before writes. Once the intended root is established, it can be specified explicitly to avoid creating another handoff in a subdirectory. Git trust settings are not changed automatically.
- **History management**: search completed records by work name, date, or keyword. Explicitly select records to seal or clear. Sealing preserves full contents; clearing removes the selected records.
- **Claude memory lookup**: read external handoffs and links within the same project from an explicitly specified scope, without automatically importing records or executing their instructions.

Older handoffs without baselines remain usable through manual source checks. Handoff data is ignored by Git by default; existing or explicitly requested tracking choices are preserved. Resume in the same project directory. Synchronization across worktrees requires separate handling, and shared history writes across sessions require coordination; the tool provides no cross-session locking.

Agent guidance drives delegation and resume workflows; the tool handles formats, files, and source comparisons. Passing installation checks does not establish that every native delegation behavior or sandbox has been verified. See the validation documents below for platform evidence and unconfirmed items.

## Further reading

Some detailed guides are currently available in Traditional Chinese.

- [Installation, updates, and removal](docs/setup.md)
- [Handoffs, history search, and sealing](docs/handoff.md)
- [Source baselines and verification records](skills/feather-handoff/references/snapshots.md)
- [Delegation rules](templates/AGENTS.md)
- [Development and validation](docs/development.md)
- [Handoff tool validation](docs/handoff-tool-validation.md)
- [Resume reliability validation and limitations](docs/resume-reliability-validation.md)
- [Platform and native capability limitations](docs/native-compatibility.md)
