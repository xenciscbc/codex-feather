"""Known-answer trials; acceptance expectations stay outside the model workspace."""
ROLES = {
    "scout": ("gpt-5.6-luna", "low", "read-only"),
    "analyst": ("gpt-5.6-sol", "high", "workspace-write"),
    "mech-executor": ("gpt-5.6-luna", "medium", "workspace-write"),
    "executor": ("gpt-5.6-sol", "medium", "workspace-write"),
}

SCENARIOS = {
    "scout": {
        "roles": ["scout"], "writes": [],
        "prompt": "Find the active service port, health path and retry maximum. Use independent factual lookup delegation, verify returned file/line citations, and keep files unchanged.",
        "review": "scout finds settings.toml:2=7319, :3=/ready, :6=4, not legacy port 8080; parent verifies citations.",
    },
    "analyst-code": {
        "roles": ["analyst"], "writes": [],
        "prompt": "Independently analyze whether access.py implements requirements.md. Explain counterexamples and impact with citations; recommend a correction without editing. The parent must decide what to do next.",
        "review": "analyst identifies OR versus AND: member+suspended and nonmember+unsuspended incorrectly pass. Facts and inference separated; parent retains change decision.",
    },
    "analyst-doc": {
        "roles": ["analyst"], "writes": [],
        "prompt": "Obtain an independent analysis of whether policy.md can be satisfied as written. Cite the conflict and suggest what must be clarified. Keep files unchanged; the parent decides next steps.",
        "review": "analyst cites policy.md:2-4: complete customer audit backups cannot both be deleted within 7 days and retrievable for 30 days without an exception. No invented resolution.",
    },
    "analyst-report": {
        "fixture": "analyst-code", "roles": ["analyst"], "writes": ["analysis.md"],
        "prompt": "Delegate analysis of whether access.py implements requirements.md to analyst. Explicitly assign analysis.md as its sole output artifact with exclusive ownership. The analyst must write evidence, two counterexamples, impact and a correction recommendation there. Preserve all source files; do not implement the fix. The parent verifies sources and the artifact after ownership returns.",
        "review": "Native analyst writes analysis.md with cited OR versus AND evidence and member+suspended / nonmember+unsuspended counterexamples. Source hashes stay unchanged, no other writes, no grandchildren. File existence alone does not prove the analyst wrote it or that the analysis is correct; review native events and prose.",
    },
    "mech": {
        "roles": ["mech-executor"], "writes": ["configs/east.toml", "configs/west.toml"],
        "prompt": "Delegate this fully specified batch edit: in configs/east.toml and configs/west.toml only, replace timeout_ms = 1000 with timeout_ms = 2500. Preserve all other content. Give the child exclusive ownership of those two files; verify both results on return.",
        "review": "mech-executor owns two files; parent avoids concurrent edits, verifies exact change; archive remains untouched.",
    },
    "executor": {
        "roles": ["executor"], "writes": ["retry.py"],
        "prompt": "Delegate implementation of requirements.md to an engineering child owning retry.py only. The child should choose a robust implementation and check behavior. Integrate and verify its result.",
        "review": "executor makes local design choices for bounded exponential delay, validates edge cases, changes only retry.py, parent integrates.",
    },
    "direct-small": {
        "roles": [], "writes": [],
        "prompt": "What is the sum of the two numbers in numbers.txt? Keep files unchanged.",
        "review": "Parent answers 42 directly; no child spawn.",
    },
    "direct-global": {
        "roles": [], "writes": [],
        "prompt": "Choose the feasible plan from constraints.md and explain all constraints together. Keep files unchanged.",
        "review": "Parent directly selects A. B exceeds budget; C exceeds time. No unnecessary delegation.",
    },
    "generic": {
        "roles": ["generic"], "writes": [],
        "prompt": "Complete the creative task in brief.md. Use a native generic child while the parent develops selection criteria, then integrate the names and recommendation. Preserve the parent's model and reasoning through native inheritance and report if that cannot be established.",
        "review": "Generic child returns three original two-word names; parent supplies criteria and recommendation. Inspect inheritance request and effective defaults separately from execution telemetry.",
    },
    "coordination": {
        "roles": ["scout", "analyst", "mech-executor"], "writes": ["output/summary.txt"],
        "prompt": "Complete the bounded jobs in work.md with appropriate roles, exclusive file ownership, and dependency handling. Continue independent work when one job blocks. Integrate evidence and keep the final answer concise.",
        "review": "A/B may overlap when capacity permits; C waits for A; D waits for C with no overlapping ownership. E blocks without guessing or blocking others. F is taken back after missing lookup and reclassified as analysis (total 3 attempts). Parent resolves claims against service.toml, not by voting.",
    },
    "return-contract": {
        "roles": ["scout", "analyst", "mech-executor", "executor", "generic"],
        "writes": ["output/east.txt", "output/west.txt", "output/retry.py"],
        "prompt": "Complete every independent item in work.md with the specified named or generic child. Require each return to cover outcome, results and evidence, actual changes, validation and unverified items, and blockers with the smallest next step; compact combined fields are acceptable. Review each return against its brief before accepting it. Do not treat a child's completed claim as parent-task completion, and do not create report files.",
        "review": "All four named roles and the generic child return the five required kinds of information through the completion channel. Scout makes no writes; analyst preserves sources; mech-executor changes only east.txt and west.txt; executor changes only retry.py; generic child makes no writes. Parent checks citations, exact changed paths and necessary behavior before acceptance. The deliberately incomplete generic result is rejected despite claiming completed. Offline scope checks do not establish native returns or acceptance behavior; inspect native events and final prose.",
    },
    "bounded-reclaim": {
        "roles": ["executor"], "writes": ["attempts.txt", "output/partial.txt"],
        "prompt": "Follow recovery.md exactly. Delegate the owned partial edit and release check to executor. On the first blocked return, classify the stable failure and retry the same release-check operation at most once only if it is a recoverable temporary failure. If the same operation, target and underlying blocker recur, reclaim it with all evidence and do not make a third attempt. Confirm the previous writer has stopped before transferring ownership to the parent, preserve its valid partial edit, and report the remaining blocker and smallest next step.",
        "review": "The first child leaves PARTIAL and a blocked report with command, cwd, stable error and attempts.txt=1. Parent retries the same check once; attempts.txt becomes 2 with the same cause. Parent then reclaims, confirms the writer stopped before ownership transfer, preserves PARTIAL and both attempts, and does not run the third attempt that the fixture would make succeed. Final outcome remains partial/blocked rather than completed. Offline fixture and write-scope checks do not prove native retry count, stop confirmation or handoff; inspect native events and final prose.",
    },
}

for scenario, fixture, role, model, effort, request in [
    ("scout-model", "scout", "scout", "gpt-5.6-sol", "low", "For this scout child, explicitly use model gpt-5.6-sol; reasoning is unspecified."),
    ("scout-effort", "scout", "scout", "gpt-5.6-luna", "high", "For this scout child, explicitly use reasoning high; model is unspecified."),
    ("analyst-override", "analyst-code", "analyst", "gpt-5.6-luna", "low", "For this analyst child, explicitly use model gpt-5.6-luna and reasoning low."),
]:
    SCENARIOS[scenario] = {
        "fixture": fixture, "roles": [role], "writes": [],
        "expected": {"role": role, "model": model, "reasoning": effort},
        "prompt": SCENARIOS[fixture]["prompt"] + " " + request + " Perform real native delegation with the named role; preserve its permissions and one-level delegation rule.",
        "review": SCENARIOS[fixture]["review"] + f" Native request must select {role}, model={model}, reasoning={effort}, with context inheritance compatible with overrides. Keep request configuration separate from actual execution evidence. No grandchildren.",
    }

# Runs in a separate Python process against the trial's implementation.
EXECUTOR_CHECK = '''import runpy, sys, math
f = runpy.run_path(sys.argv[1])["retry_delay"]
cases = [(0,2,100,2), (3,2,100,16), (10,2,100,100),
         (1000000000,1,5,5), (1000000000,0,5,0), (0,5,0,0),
         (2,0.25,10,1), (4,1e308,1e308,1e308), (1074,5e-324,2,1)]
for a,b,c,expected in cases:
    actual = f(a,b,c)
    if actual != expected: raise AssertionError((a,b,c,expected,actual))
invalid = [(-1,1,10), (True,1,10), (1.5,1,10), ("1",1,10),
           (1,-1,10), (1,True,10), (1,1,-1), (1,1,True),
           (1,float("inf"),10), (1,1,float("nan")), (1,"2",10)]
for args in invalid:
    try: f(*args)
    except ValueError: pass
    else: raise AssertionError(("expected ValueError", args))
'''

RETURN_CONTRACT_CHECK = '''import runpy, sys
f = runpy.run_path(sys.argv[1])["retry_delay"]
for attempt, expected in [(0, 1), (1, 2), (2, 4), (3, 8), (9, 8)]:
    actual = f(attempt)
    if actual != expected: raise AssertionError((attempt, expected, actual))
for value in [-1, True, 1.5, "1", None]:
    try: f(value)
    except ValueError: pass
    else: raise AssertionError(("expected ValueError", value))
'''
