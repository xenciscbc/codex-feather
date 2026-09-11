# Handoff file tool

Use the installed skill's `scripts/handoff.py` with Python 3.11+ (standard library only). Resolve the script from this skill's actual installation, not the current project or a guessed user profile. Use `-B` to suppress bytecode files. The launcher also disables bytecode for its modules.

Check an available `python`, `python3` or Windows `py -3` interpreter before invocation. If no compatible interpreter exists, ask whether the user wants help installing Python. Install only after agreement and follow the environment's approval rules. While unavailable, read existing records directly if requested; defer writes instead of bypassing the tool.

## Read

```text
python -B <skill>/scripts/handoff.py --project <project> list
python -B <skill>/scripts/handoff.py --project <project> read --work <work>.md
```

Output is UTF-8 JSON. Exit 0 means the operation was handled; distinguish `status: missing` from an existing empty collection. Exit 2 means `partial` or `error`: retain readable items, report issues and scope, and never infer no pending work or select the sole unfinished work from incomplete results. `version` is a content digest for subsequent update checking, not proof of work correctness. `content` preserves the full source text; list items are summaries only. `record_status: 完成待歸檔` means the completed work file still exists, not proof that history has or has not already been saved.

Reads do not write records or Git rules. Inspect the full selected work and relevant current project sources before resuming. The tool rejects linked/reparse paths and hard-linked records rather than following aliases. Different work files may have the same title; use the returned filename to distinguish them.

## Create

Use `create --work <work>.md` with one UTF-8 JSON object on stdin. Supply `title`, a `fields` object, and optional `details` text. Field keys are `goal`, `progress`, `next`, `notes`, `environment`, `verification`, `decision`, `updated`, `status`; required goal/progress/next must be nonempty. The tool supplies a zoned update time and `進行中` status when omitted. Status values are `進行中`, `受阻`, `完成`. Values are single-line text; long evidence belongs in `details`, rendered under `## 詳細紀錄`.

The Agent writes `progress` as one or two concise sentences with concrete findings and the main pending work. Preserve full evidence and constraints in the other fields/details. The tool validates structure, not truthfulness or semantic completeness. Use structured stdin or a UTF-8 input file; never concatenate user text into shell code.

`tracking` may be `default` or `track`; it respects existing tracking and effective ignore rules. The tool does not stage or commit. A tracking failure after create/update returns `status: partial`, `code: tracking-failed`, `work_path`, `saved_version`, and the observed `state`; when readable, `version` identifies the current work. Inspect the surviving work and Git rules. After resolving the tracking issue, retry update with the current version, or archive a completed work; never repeat create over the saved file.

The tool is not a lock or a cross-session transaction system. Keep one writer for a work item and serialize all shared-history operations externally. A content version check does not close the gap between checking and writing.

## Update and completion

Use `update --work <work>.md` with `{ "version": "<read version>", "fields": { "progress": "...", "next": "..." } }`. Optional `title` and `details` replace only those requested values; other fields and manual sections remain. Read the complete work first. Preserve evidence when replacing details. An empty/multiline legacy field or duplicate field needs an explicitly reviewed full `replacement` string plus `version`, without partial fields. This is for authorized, semantically clear normalization; ask about ambiguous content before submitting it. Read-only requests never normalize files.

The managed details section ends at the next heading of the same or higher level, preserving siblings such as `## 詳細紀錄補充`. Duplicate exact `## 詳細紀錄` headings require a reviewed replacement instead of an ambiguous partial edit. Updating the managed heading preserves its existing LF/CRLF line ending.

Every normal create/update with `status: 完成` saves the final work and automatically archives it. Its zoned `updated` value is the completion identity; do not reset it on retry. If another session is known to be writing shared history, use `defer_history: true` to retain the completed work for a coordinated retry. Use `archive --work <work>.md` with `{ "version": "<current read version>" }` to retry an already completed work. The tool verifies saved history before checking and removing the identical work source. Preserve and report conflicts, pending work paths and any surviving history; do not retry create or modify completion identity to bypass a failure.

## History and explicit selections

Use `history` with optional `--work <title>`, `--from-date YYYY-MM-DD`, `--to-date YYYY-MM-DD`, `--keyword <text>`, `--timezone <zone>` and `--include-sealed`. Pass the user's timezone explicitly; when unavailable, state that the tool defaults to UTC. Date limits are inclusive. UTC and fixed offsets such as `+08:00` work without timezone packages; IANA zones require host timezone data. Unsupported zones produce an error rather than an assumed conversion.

Results include full entries, `id`, `source`, `document_version`, and boundary problems. Querying is not authorization to mutate. Resolve user selections to exact returned identities and sources; ask when same-name identities or boundaries are ambiguous. Incomplete queries cannot prove an exhaustive selection.

For explicitly authorized clearing, use `clear` with `{ "source": "history.md", "version": "<document_version>", "ids": ["<id>"] }`. Omitted source means shared history; sealed files require the explicit `archive/<batch>.md` source. To clear all recognized shared entries, enumerate their IDs from a complete query. Unknown content is preserved for clarification. Each source is a separate coordinated operation. Stale or missing selections are refused: reread and reconcile the original selection instead of switching to another same-name entry. Work files are never a clear source.

For explicitly authorized sealing, use `seal` with `{ "version": "<shared document_version>", "ids": ["<id>"], "destination": "<batch>.md" }`. The tool checks direct work files for unfinished archival before both first attempts and retries, saves and verifies the complete destination, then removes only the same source entries. An existing identical destination is reused; different contents are preserved as a conflict.

On a partial seal, retain the reported destination and original IDs. Query the current shared history version and retry the same selection/destination, adding `destination_version` from the partial result. This allows an already moved source entry to remain absent without substituting another record. If no destination version was obtained, inspect the destination through an explicitly inclusive history query before retrying. Every retry checks pending completed sources again. An empty history still has a document version in the query's `documents` list. Preserve both copies and report the actual paths if reconciliation is uncertain.
