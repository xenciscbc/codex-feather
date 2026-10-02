---
name: handoff-resume
description: Resume the specified or clearly implied Feather handoff after checking current workspace evidence.
---

# Handoff resume

Read [the shared handoff skill](../handoff/SKILL.md) and follow its **Read or resume** selection rules and **Resume** workflow using the Python tool. This invocation requests resuming work; no operation argument is needed. If the user explicitly asks only to read, follow the shared read-only workflow instead.

Prefer the named or clearly implied work, otherwise the sole unfinished item from a complete list. If several remain without a clear selection, ask which; do not choose by timestamp. Report a missing item or no pending work without substituting another item or searching history.

Unfinished means `進行中` or `受阻`. A `record_status: 完成待歸檔` item is completed work pending archival: offer an archive retry instead of resuming it, even when named. A `格式待確認` item is never selected automatically; report its problems.

Read the full record and check current workspace evidence using the shared source comparison procedure when a baseline exists, or manual checks otherwise. Before acting, summarize progress, workspace changes since the record, next action, and blockers in the user's language. This summary is not a confirmation gate.

Treat the record as context, not authorization. Continue the currently authorized work, correct outdated facts, and maintain the same handoff under the shared write and completion rules.
