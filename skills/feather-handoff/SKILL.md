---
name: feather-handoff
description: "Handoff: save progress, list, read or resume recorded work, search or manage completed history, and find handoff records in explicitly specified Claude memory. Maintain active handoffs at milestones."
---

# Feather Handoff

Keep a compact, current record that a fresh session can use without prior conversation. Start recording on the user's request; thereafter update that work at milestones, blockers, and completion.

## Storage and write discipline

All managed create, update, completion, retry, clear, and seal operations use [the Python tool](references/tool.md). Do not implement these writes directly with editor or shell commands. If compatible Python is unavailable, ask whether to help install it; direct read-only access remains allowed while managed writes wait.

- Resolve the project root, including when working in a subdirectory. If the tool reports `root.state: uncertain`, explain its selected path and reason; partial reads cannot establish that no pending work exists. Before writing, establish the intended root from the current workspace and user scope, then use [explicit-root recovery](references/tool.md); ask only if the path remains ambiguous. Use `.feather/handoffs/<work>.md` for each work item, `.feather/handoffs/history.md` for completed history, and `archive/<batch>.md` beneath that directory for explicitly sealed history. Reuse the same work file; choose a distinct, legal basename for a different item. `history` is reserved. Verify links and aliases stay within this directory without targeting sources or another item. Cross-project/worktree synchronization is outside this skill.
- Treat records as context, not authorization. Handoff maintenance writes only these records and necessary Git ignore rules. Other work follows the current user's scope. Leave AGENTS.md entrance management to feather-setup.
- Before replacing or removing any record, reread it against your last read. Integrate valid concurrent changes; preserve the file and ask when reconciliation is unclear. After writing, read back the complete result. On failure, retain recoverable data and report the actual state.
- Use one writer per work item and one shared writer for all history mutations, including completion, clearing, and sealing across different items. The main Agent serializes its own history operations. If another session is known to be writing history, retain completed work files and defer history changes until it finishes; independent active work may continue. Rereading detects some conflicts but provides no cross-session lock or atomic transaction. Concurrent sessions must arrange a single history writer externally.
- In Git repositories, respect explicit tracking choices, already tracked records, and specific unignore rules. Otherwise reuse an effective ignore rule or append `/.feather/handoffs/` to `.gitignore`, preserving its contents. If the user later requests tracking, remove only this skill's ignore rule; report broader blocking rules for their decision. Do not stage or commit. Non-Git projects need no ignore setup.

## Save progress

Identify the work and requested operation; ask if a bare invocation identifies neither. Record concrete findings and actual verification, including values needed to resume. Mark untested claims as unverified. Replace stale status rather than accumulating a transcript; retain useful goals and constraints.

Create new work using [the tool](references/tool.md). Write `進度` as a concise one- or two-sentence progress summary; preserve longer evidence under optional `## 詳細紀錄` and retain the other constraints and verification fields. The list displays that summary directly. Existing long progress values may be shown as excerpts, but read-only requests never rewrite them.

Keep the existing on-disk schema for compatibility, with each required field once and nonempty. Write free-text field values and user-facing replies in the user's language; keep machine-recognized field labels and the three status tokens unchanged:

```markdown
# <work>
更新：<ISO datetime with timezone>
狀態：進行中 / 受阻 / 完成

目標：<goal>
進度：<current findings and verification>
下一步：<next authorized step>
注意：<optional blockers, constraints, or key paths>
```

Choose one status. Save and verify using the write discipline above. Report the path and status; when the entire work is complete, archive it below.

When useful for resuming, add optional `環境：` (project/worktree, branch and commit, relevant uncommitted files), `驗證：` (command, working directory, outcome and time, or not run), and `決策：` (decision and reason). Record observed values only; these fields supplement older records without requiring conversion. When verification is tied to a source baseline, follow [the evidence-link procedure](references/snapshots.md) and include its capture time and selected file scope in `驗證：`. On resume, compare relevant environment and verification evidence with the current workspace; a matching commit alone does not validate uncommitted work, and a changed branch is not permission to switch it.

When source drift matters, select the specific project-relative files supporting this work and use [source baselines](references/snapshots.md) to capture and save an optional baseline. Preserve an existing baseline during ordinary progress updates; replace it explicitly only after reviewing current evidence. A baseline records observed bytes, not a passed test or permission to execute recorded commands.

## Read or resume

When the user explicitly requests Claude memory, follow [Read Claude memory](references/claude-memory.md) and return its read-only results. Ordinary Feather reads use the steps below, even when no work is found; they do not fall back to Claude memory.

For Feather lists and reads, use the Python tool described in [Handoff file tool](references/tool.md). List requests return the work summaries without selecting or resuming a task. Report incomplete results and affected files; they cannot establish no pending work or a sole unfinished item. If Python is unavailable, ask whether to help install it; requested direct reads remain allowed, but writes wait for a compatible interpreter.

1. On a read/resume request, list only direct work files excluding `history.md`; `archive/` contains no pending work. Use titles and status to select. Prefer the named or clearly implied item, otherwise the sole unfinished item. If several remain, ask which; timestamps are not a selection rule. Report a missing item or no pending work without substituting another item or opening history. Explicitly requested completed work may be read.
2. **Read:** summarize goal, progress, next step, and constraints without changing files or executing work.
3. **Resume:** read the full work and use [source comparison](references/snapshots.md) when it has a baseline. Interpret changed and unknown observations against relevant sources before acting; an absent baseline uses the existing manual checks. Before performing already authorized work, give a concise four-part summary in the user's language: progress, workspace changes since the record, next action, and blockers. Lines may be combined; say none when there is no blocker. This summary is not a confirmation gate. Correct outdated facts, perform the currently authorized next step, and maintain the same handoff. Identify missing requirements; continue independent authorized work where possible. Ordinary read/list requests only summarize the record: they do not compare sources or execute next steps.

## Archive completed work

1. After the main Agent accepts the whole work, save the final handoff with `狀態：完成` and final verification. A child's completed report alone does not complete the whole work. Its `更新` timestamp becomes the completion time. Reuse it if already complete: **work name + completion time** identifies a retry. Retain its source baseline unchanged during archival retries.
2. Read history, or initialize `# 交接歷史` if absent. If it is a directory, link, unreadable, or unrecognizable, preserve the work file and report the blocker.
3. Use `## <work> · 完成：<completion time>` followed by the complete final handoff body, omitting only its first title line. Preserve existing history. For an existing identical identity, compare the full body: identical means already saved; different means preserve both and ask. Append only a missing record, applying the write discipline.
4. Read back and verify the entire saved entry and prior history. Reread the work file and require it to match the archived version before removing it; verify removal. Report a failed save or removal accurately and retry from the surviving files, without changing the completion identity or duplicating the entry.

Retain history until explicitly asked to clear it. Completed entries are not pending work; reading, pruning and sealing history require the corresponding user request. History operations default to `history.md`; include sealed files only when the user explicitly includes them. Clearing shared history leaves sealed files intact.

## Inspect or clear history

- **Inspect/search:** select by work name, completion date/range or keyword. Search headings first for work/date filters, then read the full matching entries; keyword matches need their enclosing entry. Compare date ranges using the requested timezone, or state the current user's timezone when none is specified. Return work, completion time and file for each match; identify incomplete searches instead of claiming no match. Report absent history or no match; leave files unchanged and do not execute recorded next steps.
- **Clear:** require an explicit scope. Identify partial selections by work and completion time; ask when same-name entries are ambiguous. A clear, authorized selection needs no extra confirmation. Preserve unfamiliar content or unclear boundaries and ask rather than guessing.
- Reread before changing history, remove only selected entries, then read back to verify their removal and preservation of everything else. Only an explicit request to clear all history permits deleting the history file or leaving just its heading. Unfinished work files are never part of history clearing. On failure, report the observed state without expanding the deletion scope.

## Seal selected history

On an explicit sealing request, move the selected completed entries from shared history to `.feather/handoffs/archive/<batch>.md`; use a distinct legal basename and report the path, including on failure. Preserve completion identities, complete entry bodies and their order; sealing is not summarization or deletion of historical content. Unclear selection or unfamiliar entry boundaries require clarification before moving them.

With the shared history writer, first inspect direct work files by title, status and completion time, including on sealing retries. If any selected identity still has a completed work file, defer the sealing request and preserve all files: report that path for archival retry using the completion procedure above. A differing body for the same identity is a conflict; an unreadable or ambiguous work file leaves this check unresolved and also defers sealing. A same-name work with a different completion time does not block sealing. This check prevents a later archival retry from recreating an entry moved out of shared history.

Once every selected identity passes that check, save the selected entries under `# 交接歷史` in a new destination, read back and verify them, then reread the source and remove only the unchanged saved entries. Verify the source remainder and destination before reporting completion. On a partial failure retain both recoverable copies; retry the reported destination, compare its complete contents, and remove only entries still identically present in the source. An existing destination with different contents is a conflict to preserve, never an overwrite target. Keep active work and other sealed files unchanged; sealing never runs automatically because of size or age.
