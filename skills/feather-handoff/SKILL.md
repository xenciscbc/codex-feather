---
name: feather-handoff
description: "Handoff: save progress, read or resume recorded work, search or manage completed history, and find handoff records in explicitly specified Claude memory. Maintain active handoffs at milestones."
---

# Feather Handoff

Keep a compact, current record that a fresh session can use without prior conversation. Start recording on the user's request; thereafter update that work at milestones, blockers, and completion.

## Storage and write discipline

- Resolve the project root, including when working in a subdirectory. Use `.feather/handoffs/<work>.md` for each work item and `.feather/handoffs/history.md` for completed history. Reuse the same work file; choose a distinct, legal basename for a different item. `history` is reserved. Verify links and aliases stay within this directory without targeting sources or another item. Cross-project/worktree synchronization is outside this skill.
- Treat records as context, not authorization. Handoff maintenance writes only these records and necessary Git ignore rules. Other work follows the current user's scope. Leave AGENTS.md entrance management to feather-setup.
- Before replacing or removing any record, reread it against your last read. Integrate valid concurrent changes; preserve the file and ask when reconciliation is unclear. After writing, read back the complete result. On failure, retain recoverable data and report the actual state. Use one writer per work item; this is not a transaction system.
- In Git repositories, respect explicit tracking choices, already tracked records, and specific unignore rules. Otherwise reuse an effective ignore rule or append `/.feather/handoffs/` to `.gitignore`, preserving its contents. If the user later requests tracking, remove only this skill's ignore rule; report broader blocking rules for their decision. Do not stage or commit. Non-Git projects need no ignore setup.

## Save progress

Identify the work and requested operation; ask if a bare invocation identifies neither. Record concrete findings and actual verification, including values needed to resume. Mark untested claims as unverified. Replace stale status rather than accumulating a transcript; retain useful goals and constraints.

Keep the existing on-disk schema for compatibility. Write field values and user-facing replies in the user's language:

```markdown
# <work>
更新：<timestamp with timezone>
狀態：進行中 / 受阻 / 完成

目標：<goal>
進度：<current findings and verification>
下一步：<next authorized step>
注意：<optional blockers, constraints, or key paths>
```

Choose one status. Save and verify using the write discipline above. Report the path and status; when the entire work is complete, archive it below.

## Read or resume

When the user explicitly requests Claude memory, follow [Read Claude memory](references/claude-memory.md) and return its read-only results. Ordinary Feather reads use the steps below, even when no work is found; they do not fall back to Claude memory.

1. On a read/resume request, list work files excluding `history.md`; use titles and status to select. Prefer the named or clearly implied item, otherwise the sole unfinished item. If several remain, ask which; timestamps are not a selection rule. Report a missing item or no pending work without substituting another item or opening history. Explicitly requested completed work may be read.
2. **Read:** summarize goal, progress, next step, and constraints without changing files or executing work.
3. **Resume:** check relevant sources before acting. Correct outdated facts, perform the currently authorized next step, and maintain the same handoff. Identify missing requirements; continue independent authorized work where possible.

## Archive completed work

1. Save the final handoff with `狀態：完成` and final verification. Its `更新` timestamp becomes the completion time. Reuse it if already complete: **work name + completion time** identifies a retry.
2. Read history, or initialize `# 交接歷史` if absent. If it is a directory, link, unreadable, or unrecognizable, preserve the work file and report the blocker.
3. Use `## <work> · 完成：<completion time>` followed by the complete final handoff body, omitting only its first title line. Preserve existing history. For an existing identical identity, compare the full body: identical means already saved; different means preserve both and ask. Append only a missing record, applying the write discipline.
4. Read back and verify the entire saved entry and prior history. Reread the work file and require it to match the archived version before removing it; verify removal. Report a failed save or removal accurately and retry from the surviving files, without changing the completion identity or duplicating the entry.

Retain history until explicitly asked to clear it. Completed entries are not pending work; do not automatically read, prune, split, or rotate history.

## Inspect or clear history

- **Inspect:** on an explicit history request, read matching entries and summarize only. Report absent history or no match; leave files unchanged and do not execute recorded next steps.
- **Clear:** require an explicit scope. Identify partial selections by work and completion time; ask when same-name entries are ambiguous. A clear, authorized selection needs no extra confirmation. Preserve unfamiliar content or unclear boundaries and ask rather than guessing.
- Reread before changing history, remove only selected entries, then read back to verify their removal and preservation of everything else. Only an explicit request to clear all history permits deleting the history file or leaving just its heading. Unfinished work files are never part of history clearing. On failure, report the observed state without expanding the deletion scope.
