Complete all five independent child tasks. Each brief must include the normal Feather scope and completion details.

1. Scout: cite the active limit from `facts.toml`; keep files unchanged.
2. Analyst: determine whether `claim.md` agrees with `facts.toml`, separating cited facts from inference; preserve sources and write no artifact.
3. Mech-executor: own only `output/east.txt` and `output/west.txt`; replace exactly `PENDING` with `READY` in both files and verify both.
4. Executor: own only `output/retry.py`; implement `retry_delay(attempt)` from `requirements.md` and validate its observable behavior.
5. Generic child: review the supplied `recorded-return.md` against `label-brief.md`. Reject its `completed` claim because the required rationale is missing, then ask a generic child to supply that rationale while keeping files unchanged.

The parent reviews every return against its brief, checks actual changes and sources, and reports which child results were accepted. Do not create separate return-report files.
