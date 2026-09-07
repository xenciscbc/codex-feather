"""Known-answer trials; acceptance expectations stay outside the model workspace."""
ROLES = {
    "scout": ("gpt-5.6-luna", "low", "read-only"),
    "analyst": ("gpt-5.6-sol", "medium", "read-only"),
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
