---
name: handoff-list
description: List Feather handoff work items and their progress summaries without resuming work.
---

# Handoff list

Read [the shared handoff skill](../handoff/SKILL.md) and follow its list workflow using the Python tool. This invocation selects listing; no operation argument is needed. Use the current project unless the user specifies another project.

Return the work summaries, including completed work awaiting archival, and report incomplete results. Keep this operation read-only: do not select or resume a work item, compare source baselines, or archive records. Completed history and sealed archives require a separate explicit request.
