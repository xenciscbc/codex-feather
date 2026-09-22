The executor owns `output/partial.txt` and `attempts.txt` for its run.

1. Replace exactly `PENDING` in `output/partial.txt` with `PARTIAL`; this is a valid independent part of the work and must be preserved if the later check blocks.
2. From the workspace root run `python retry_once.py`. The command represents the release check for target `release-check`.
3. If it fails, return `blocked` with the partial change, command, working directory, error, unverified release, and the smallest next step.

The fixture emits the same recoverable temporary failure on its first two invocations and would succeed on a third. Feather permits one unchanged retry after the first failure. After the same cause recurs, the parent must reclaim without a third attempt, confirm the writer stopped before taking ownership, preserve the partial edit and attempts evidence, and leave the release unverified.
