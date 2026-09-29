# Windows stat/fstat ctime compatibility

## Notes

Regression in handoff reads and source observations on Windows Python 3.12.

## Decisions-so-far

[01 — false File changed during read](issues/01-false-file-changed.md): implemented
for plugin 1.6.1. Exclude ctime only for Windows cross-API checks; retain same-API
ctime checks and POSIX behavior. Two independent reviews completed.

## Fog

The full suite retains installer and test-environment failures documented in the
issue. These are outside the ctime fix. This release does not claim a green full
suite or include unrelated pre-existing worktree changes.
