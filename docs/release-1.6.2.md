# 1.6.2 — Updated role model defaults

Set the packaged model default for analyst, executor and security-executor to
`gpt-6.1-sol`. Their reasoning defaults remain high, medium and high respectively.
Scout and mech-executor keep their existing model and reasoning defaults.

Update the managed delegation entrance, English and Traditional Chinese usage
examples, trial scenarios and test expectations together. Saved model overrides
continue to take precedence over packaged defaults. Historical validation
records retain the model settings used at the time.

The model and trial suites passed 36 tests both in the working tree and in an
isolated release snapshot that excludes separate, uncommitted installer fixes.
Delegation skill format, Python compilation and Git whitespace checks passed.
The complete suite was not rerun; the installer limitations documented for
1.6.1 remain outside this release.
