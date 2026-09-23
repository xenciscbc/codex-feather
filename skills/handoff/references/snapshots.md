# Source baselines and resume comparison

Read this reference when saving selected source observations or resuming a handoff with `snapshot_state: available/invalid`. Use the installed skill's Python tool and interpreter rules in [tool.md](tool.md).

## Capture and save

Choose explicit project-relative ordinary files relevant to the work, including expected missing files when useful. Use `/` separators; directories, globs, duplicate paths, absolute paths, `..`, links/reparse paths, hard links, Git metadata and `.feather/handoffs` sources are excluded. Sources remain unchanged.

```text
python -B <skill>/scripts/handoff.py --project <project> snapshot
stdin: {"paths": ["src/auth.py", "config/local.json"]}
```

The JSON response contains `snapshot`, `complete`, `status` and `issues`. Copy the returned `snapshot` object into the existing create/update payload; update still needs the full handoff's current `version`. Supply it as structured stdin or a UTF-8 file, not shell-interpolated user text. The tool saves one optional `## 檔案基準` JSON section alongside the existing fields/details, with schema version, zoned capture time, raw-byte SHA-256 observations and Git identity.

Capture is read-only and does not establish that a past test covered these bytes. Record test command, cwd, time and outcome separately. A claim that a test covered the baseline requires observations showing relevant sources unchanged across that test, and still excludes unobserved dependencies and external state.

### Link existing test evidence

Use the optional `驗證：` field to link a test run to a saved baseline without adding another schema:

1. Select the files that support the claim, then capture and save the baseline immediately before the test.
2. After the test, compare that saved baseline and confirm both the selected source observations and available Git identity stayed unchanged.
3. Record the command, cwd, run time and outcome together with the baseline's `captured_at`, selected path scope, and post-test comparison result.

The capture timestamp alone is no proof that the test used those bytes. Any selected-source drift or unknown observation, or changed/unknown Git evidence, leaves the link unconfirmed. Refreshing the baseline starts new evidence: test results linked to the old capture time and scope do not transfer to the refreshed baseline. This protocol records tests already being run; it does not require a rerun or authorize automated execution.

The writer rechecks explicitly supplied present/missing observations and known Git identity before saving. On `snapshot-conflict`, reread the relevant sources and handoff, reconcile progress, then capture again if appropriate. It never silently refreshes the baseline. Unknown observations remain unknown and are not reread during save verification. Ordinary updates without `snapshot` preserve the old baseline even when sources changed. `snapshot: null` is rejected; no separate baseline-removal command exists.

Baseline validation failures happen before saving. Tracking or archival failures after saving use the existing partial-result recovery, including the surviving path/version; do not repeat create over a saved handoff. Completion and sealing retain the full baseline, and retries preserve the completion identity.

## Compare before resuming

```text
python -B <skill>/scripts/handoff.py --project <project> compare --work <work>.md
```

Read the full selected handoff first. Compare does not write, refresh evidence, run tests, switch branches or execute recorded steps. It provides `work_version`, `baseline_state`, per-file before/current observations and `comparison`, separate Git observations, and issues.

| Result | Meaning and response |
| --- | --- |
| unchanged | Selected bytes match, or a deliberately missing file is still missing. Inspect the states; this is not proof the whole project or test environment is unchanged. |
| changed | Selected bytes differ. Reassess conclusions that depend on them. |
| created | A previously missing selected path now exists. Inspect it if relevant. |
| missing | A previously present selected file is absent. Reconcile the work before relying on it. |
| unknown | Either saved or current evidence is incomplete. Explain the specific reason and verify relevant facts by other authorized means when possible. |

Git HEAD and branch are shown independently of file observations. Detached HEAD has `branch: null`; an unborn branch has `head: null`; non-Git projects can still have complete file comparisons. Unknown Git information leaves the overall result incomplete without hiding file results. Probe commands and root discovery respect existing Git trust settings without overriding `safe.directory` or modifying Git configuration. If Git rejects the repository as untrusted, Git observations are `unknown` and capture/compare reports a partial result while retaining file observations.

Complete differences, including changed/missing/created, exit 0. An old handoff without a baseline returns `baseline_state: absent`, `complete: false`, status ok/exit 0; continue manual source checks without forcing conversion. Invalid/unknown schema, partial reads and observed races exit 2 and retain readable evidence. A missing work file returns status missing/exit 2, including when it was already archived; no implicit history lookup occurs. A retained completed file can still be compared.

Capture accepts 1–256 selected paths, at most 16 MiB per file and 64 MiB total reads. File limits, inaccessible paths and unstable reads are explicit unknown results; a truncated file never gets a valid digest. The tool checks identities and metadata, retries a changing individual read at most once, rechecks the selected observations/Git state and compares the handoff version again. These checks are not an atomic project snapshot or cross-session lock.

## Preserve human content

Existing records need no conversion. The exact fence-external heading `## 檔案基準` is reserved for one managed JSON block; examples inside code fences and similar manual headings are preserved. Duplicate sections/JSON keys, malformed blocks and unsupported versions are visible as invalid, not absent. Read-only commands never repair them. Use a reviewed full replacement only for authorized, unambiguous repair; partial updates preserve malformed content by refusing the write.

Keep details and snapshot as separate payload properties. When supplying snapshot, a second managed baseline in details is rejected. Updating details preserves its sibling baseline and manual sections. Source hashes and capture timestamps are caller-supplied evidence, not authenticated history or execution authority.
