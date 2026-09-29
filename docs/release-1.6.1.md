# 1.6.1 — Windows handoff read compatibility

Fix false `File changed during read` errors on Windows when `stat()` and
`fstat()` report different `st_ctime_ns` values for the same unchanged file.
The fix covers handoff reads and source snapshot observations.

Cross-API comparisons omit ctime only on Windows. Path-to-path and
descriptor-to-descriptor checks still compare ctime, and file identity, size,
modification time, mode, link count and existing path checks remain enforced.
POSIX cross-API ctime comparisons remain enabled.

Windows Python 3.12.11 reproduced the original problem with a real temporary
file: both APIs reported identical identity, size and modification time, but
different ctime. The original reader rejected the file; the fixed reader
returned its exact contents.

Regression tests cover stable cross-API differences, descriptor changes,
path ctime changes, and POSIX rejection of differing ctime values.

Upstream context: [CPython issue #157671](https://github.com/python/cpython/issues/157671).
This plugin works around the API discrepancy without requiring a Python upgrade.

Validation and publication results are recorded in
[the issue](../.scratch/windows-stat-fstat-ctime/issues/01-false-file-changed.md).


Known validation limits: the complete suite is not green. Existing installer
fixtures omit required entrance templates, and the committed installer rejects
CRLF delegation skill headers. Those installer changes are outside this patch.
The observations module also retains 18 pre-existing mypy diagnostics, identical
to the baseline; storage type checking passes. See the issue for exact results.

Final Windows Python 3.12.11 handoff regression: 107 tests, 106 passed and
1 platform-dependent symlink skip (installer runtime tests excluded).
