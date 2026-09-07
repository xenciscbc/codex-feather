Use bounded delegation for the independent jobs below. Keep shared-write jobs sequential.
A: Extract the service port from service.toml with a citation.
B: Analyze the disagreement between claims/old.md and claims/current.md against service.toml. Do not edit sources.
C: In owned output/summary.txt, replace exactly PENDING with the verified port from A. C depends on A.
D: After C completes, append exactly one line VERIFIED to the same file; C and D cannot own it concurrently.
E: Configure a new timeout in output/timeout.txt. The required value has deliberately not been supplied; return this blocker without guessing. Complete other independent jobs.
F: First assign a factual lookup of max_attempts in service.toml to scout. If the key is absent, take back the job and analyze retry.md to derive the stated limit; do not retry the same lookup. Keep source files unchanged.
Integrate A and B into the final answer and explain which claim is supported. Report E's missing value and F's handoff.
Only output/summary.txt may change; leave output/timeout.txt unchanged until the missing requirement is supplied.
