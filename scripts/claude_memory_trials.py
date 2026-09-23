"""Known-answer Claude memory trials, not a memory reader or product resolver.

Artifact checks cannot establish what an Agent actually read or the correctness
of arbitrary prose. Review the native operations and answer against the fixture.
"""
from pathlib import Path
from dataclasses import dataclass
import json
import re
from urllib.parse import unquote
from handoff_trials import git


SCENARIOS = {
    "claude-memory-direct": {
        "fixture": "handoff", "roles": [], "writes": [],
        "prompt": "Use $handoff to find handoff records in the Claude memory directory "
                  "'memory' relative to this workspace. Summarize the results only. "
                  "Please give each matched work its own Markdown heading with its name, "
                  "link its source, and preserve concrete values and identifiers.",
        "review": "Report cache-rollout from memory/release.md, clearly identified as an explicit "
                  "unfinished handoff: port 7319, tests not run, readiness next, timeout undecided. "
                  "Do not list general preferences. Verify actual reads remain in the given memory "
                  "and skill instructions; no import, next-step execution or source writes. "
                  "Answer artifacts alone do not prove correct classification or read scope.",
    },
}

SCENARIOS["claude-memory-mixed"] = {
    **SCENARIOS["claude-memory-direct"],
    "review": "Find all three works, including unindexed observations and two works in notes.md. "
              "cache-rollout is explicit and unfinished; preserve the 7319 versus 8443 conflict. "
              "asset-cleanup is explicitly completed (17 files). queue-check is possible handoff "
              "with unknown status (probe-42). General preferences are not work. Inspect real "
              "read scope, no next-step execution, no invented missing fields and zero writes.",
}
for name, review in {
    "empty": "Search all memory Markdown, find only preferences and report no matching handoff; "
             "do not invent work or import anything.",
    "missing": "Report the absent explicit memory directory and actual checked path, not a completed "
               "search with zero results. Do not create it or fall back to another source.",
    "no-request": "There is no pending Feather work. Report that without opening Claude memory, "
                  "even though a memory directory exists. Inspect actual reads, not just unchanged files.",
}.items():
    SCENARIOS[f"claude-memory-{name}"] = {**SCENARIOS["claude-memory-direct"], "review": review}
SCENARIOS["claude-memory-no-request"]["prompt"] = (
    "Use $handoff to read our pending handoff and tell me where we left off. Only report it."
)
SCENARIOS["claude-memory-partial"] = {
    **SCENARIOS["claude-memory-direct"],
    "review": "Before native execution, hold memory/locked.md open with FileShare.None on Windows "
              "(or an equivalent real read denial). Release it before artifact verification. "
              "The Agent reports the readable cache-rollout and names locked.md as unreadable, "
              "without claiming a complete search, changing permissions or bypassing the lock. "
              "Do not claim fault coverage unless native events show the real failed read.",
}
SCENARIOS["claude-memory-project-custom"] = {
    **SCENARIOS["claude-memory-direct"],
    "prompt": "Use $handoff to find handoff records in Claude memory for project 'project' "
              "relative to this workspace. Its trusted Claude configuration root is 'claude-config'. "
              "There are no managed settings or additional launch overrides for this isolated source, "
              "and the project's Claude settings are trusted. Summarize only, with one Markdown heading "
              "per work, linked sources, concrete values and the evidence for the selected location.",
    "review": "Resolve the trusted project-local autoMemoryDirectory above shared-project and user "
              "values, selecting workspace/memory. Report cache-rollout with correct source and values. "
              "Do not scan the two lower-priority memory directories or expose unrelated settings. "
              "Review actual reads and preservation of project Git metadata and all settings.",
}
DEFAULT_PROJECT_SCENARIOS = (
    "claude-memory-project-default", "claude-memory-project-worktree",
    "claude-memory-project-non-git", "claude-memory-project-named",
)
for scenario in DEFAULT_PROJECT_SCENARIOS:
    SCENARIOS[scenario] = {
        **SCENARIOS["claude-memory-project-custom"],
        "review": "Resolve the main repository identity from Git metadata, then its unique path-derived "
                  "memory directory under the supplied Claude config root. Report cache-rollout and "
                  "the source/location evidence without changing Git state. For the worktree scenario, "
                  "start from checkout/subdir but use the main repository's shared memory.",
    }
SCENARIOS["claude-memory-project-worktree"]["prompt"] = str(
    SCENARIOS["claude-memory-project-custom"]["prompt"]
).replace("project 'project'", "project 'checkout/subdir'")
SCENARIOS["claude-memory-project-non-git"]["review"] = (
    "Use the specified non-Git project root to locate its default memory; report cache-rollout "
    "with source and location evidence. Run the native fixture outside any enclosing Git repository. "
    "Do not initialize Git or invent a worktree relationship."
)
SCENARIOS["claude-memory-project-named"]["prompt"] = str(
    SCENARIOS["claude-memory-project-custom"]["prompt"]
).replace(
    "There are no managed settings or additional launch overrides for this isolated source,",
    "For this Claude source (v2.1.234+), the launch environment sets CLAUDE_CONFIG_DIR to that root "
    "and CLAUDE_CODE_PROJECT_DIR_NAME to 'isolated-project'; no managed settings or other launch overrides apply,",
)
SCENARIOS["claude-memory-project-named"]["review"] = (
    "Use the user-supplied paired Claude launch overrides to select projects/isolated-project/memory. "
    "Do not replace the explicitly established launch name with a path-derived key or inspect personal "
    "process configuration. Summarize cache-rollout with the selection evidence and keep all files unchanged."
)
SCENARIOS["claude-memory-project-ambiguous"] = {
    **SCENARIOS["claude-memory-project-custom"],
    "prompt": str(SCENARIOS["claude-memory-project-custom"]["prompt"]).replace(
        "and the project's Claude settings are trusted.",
        "but the trust state of the project's Claude settings in that prior session is unknown.",
    ),
    "review": "Trusted project-local settings would select memory; without that trust the user "
              "setting would select user-memory. List both candidate paths and their evidence, "
              "ask which source to use and do not read either memory's contents. Do not describe "
              "an ordinary known-priority override as ambiguous; the missing fact here is trust.",
}
for name, review in {
    "missing": "The effective project-local setting points to nonexistent missing-memory. "
               "Report the setting and missing directory, not a complete zero-result search; "
               "do not read any lower-priority or default memory.",
    "invalid": "The project-local autoMemoryDirectory is relative-memory, an invalid relative value. "
               "Report the invalid setting and its source without guessing a path or scanning fallback memory.",
}.items():
    SCENARIOS[f"claude-memory-project-{name}"] = {
        **SCENARIOS["claude-memory-project-custom"], "review": review,
    }


@dataclass(frozen=True)
class ExpectedWork:
    name: str
    sources: tuple[str, ...]
    facts: tuple[str, ...]


DIRECT_WORK = ExpectedWork("cache-rollout", ("memory/release.md",), ("7319", "readiness", "timeout"))
WORKS = {
    "claude-memory-direct": (DIRECT_WORK,),
    "claude-memory-mixed": (
        ExpectedWork("cache-rollout", ("memory/release.md", "memory/unindexed/observations.md"),
                     ("7319", "8443", "readiness", "timeout")),
        ExpectedWork("asset-cleanup", ("memory/notes.md",), ("17",)),
        ExpectedWork("queue-check", ("memory/notes.md",), ("probe-42",)),
    ),
    "claude-memory-empty": (),
    "claude-memory-missing": (),
    "claude-memory-no-request": (),
    "claude-memory-partial": (DIRECT_WORK,),
    "claude-memory-project-custom": (DIRECT_WORK,),
    "claude-memory-project-default": (DIRECT_WORK,),
    "claude-memory-project-worktree": (DIRECT_WORK,),
    "claude-memory-project-ambiguous": (),
    "claude-memory-project-non-git": (DIRECT_WORK,),
    "claude-memory-project-named": (DIRECT_WORK,),
    "claude-memory-project-missing": (),
    "claude-memory-project-invalid": (),
}


def memory_directory(trial: Path, scenario: str) -> Path:
    """Name synthetic fixtures only; source resolution is performed by the Agent."""
    if scenario in DEFAULT_PROJECT_SCENARIOS:
        key = ("isolated-project" if scenario == "claude-memory-project-named"
               else re.sub(r"[^a-zA-Z0-9]", "-", str(trial / "workspace/project")))
        if len(key) > 200:
            raise ValueError("Prepare this untruncated-name fixture at a shorter trial path")
        return trial / "workspace/claude-config/projects" / key / "memory"
    return trial / "workspace/memory"


def prepare(trial: Path, scenario: str) -> None:
    if scenario == "claude-memory-missing":
        return
    memory = memory_directory(trial, scenario)
    memory.mkdir(parents=True)
    if scenario != "claude-memory-empty":
        (memory / "MEMORY.md").write_text(
            "# Memory index\n\n[cache-rollout handoff](release.md)\n"
            "[Preferences](preferences.md)\n", encoding="utf-8",
        )
        (memory / "release.md").write_text(
            "# Handoff\n\n## cache-rollout\n"
            "Status: in progress. Goal: verify the service configuration.\n"
            "Confirmed port 7319. Tests have not been run.\n"
            "Next: verify readiness. The timeout value needs the user's decision.\n",
            encoding="utf-8",
        )
    (memory / "preferences.md").write_text(
        "# Preferences\nUse short replies. Prefer pnpm.\n"
        "In general, a handoff is a way to pass context to another session.\n",
        encoding="utf-8",
    )
    if scenario == "claude-memory-mixed":
        (memory / "unindexed").mkdir()
        (memory / "unindexed/observations.md").write_text(
            "# cache-rollout handoff\nStatus: unfinished. Another observation records port 8443.\n"
            "It has not been reconciled with the earlier report.\n", encoding="utf-8",
        )
        (memory / "notes.md").write_text(
            "# asset-cleanup handoff\nCompleted: removed 17 temporary files. No further steps.\n\n"
            "# queue-check\nInvestigation note: probe-42 was observed in the queue audit.\n",
            encoding="utf-8",
        )
    if scenario == "claude-memory-partial":
        (memory / "locked.md").write_text(
            "# deployment-review handoff\nUnfinished: review tomorrow's deployment window.\n",
            encoding="utf-8",
        )
    if scenario in {"claude-memory-project-custom", "claude-memory-project-ambiguous",
                    "claude-memory-project-missing", "claude-memory-project-invalid"}:
        project = trial / "workspace/project"
        (project / ".claude").mkdir(parents=True)
        git(project, "init", "--quiet")
        config = trial / "workspace/claude-config"
        config.mkdir()
        for settings, target in [
            (config / "settings.json", "user-memory"),
            (project / ".claude/settings.json", "shared-memory"),
            (project / ".claude/settings.local.json", "memory"),
        ]:
            if target == "memory" and scenario in {"claude-memory-project-missing", "claude-memory-project-invalid"}:
                value = (str(trial / "workspace/missing-memory")
                         if scenario.endswith("missing") else "relative-memory")
                settings.write_text(json.dumps({"autoMemoryDirectory": value}), encoding="utf-8")
                continue
            if scenario == "claude-memory-project-ambiguous" and target == "shared-memory":
                settings.write_text("{}\n", encoding="utf-8")
                continue
            location = trial / "workspace" / target
            location.mkdir(exist_ok=True)
            settings.write_text(json.dumps({"autoMemoryDirectory": str(location)}), encoding="utf-8")
            if target != "memory":
                (location / "decoy.md").write_text(
                    "# wrong-source handoff\nCompleted: this is another memory location.\n", encoding="utf-8",
                )
    if scenario in DEFAULT_PROJECT_SCENARIOS:
        project = trial / "workspace/project"
        if scenario == "claude-memory-project-non-git" and any(
            (ancestor / ".git").exists() for ancestor in (project, *project.parents)
        ):
            raise ValueError("Prepare the non-Git fixture outside an existing Git repository")
        (project / ".claude").mkdir(parents=True)
        if scenario != "claude-memory-project-non-git":
            git(project, "init", "--quiet")
        (project / ".claude/settings.json").write_text("{}\n", encoding="utf-8")
        (trial / "workspace/claude-config/settings.json").write_text("{}\n", encoding="utf-8")
        if scenario == "claude-memory-project-worktree":
            hooks = trial / "empty-hooks"
            hooks.mkdir()
            git(project, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={hooks}",
                "commit", "--allow-empty", "--quiet", "-m", "Isolated fixture")
            git(project, "-c", f"core.hooksPath={hooks}", "worktree", "add", "--detach", "--quiet",
                str(trial / "workspace/checkout"))
            (trial / "workspace/checkout/subdir").mkdir()


def verify(trial: Path, scenario: str) -> None:
    answer = trial / "answer.md"
    if not answer.is_file() or not answer.read_text(encoding="utf-8").strip():
        raise ValueError("Claude memory trial requires a nonempty answer.md; native behavior remains unconfirmed")
    content = answer.read_text(encoding="utf-8")
    if not WORKS[scenario] and "cache-rollout" in content.casefold():
        raise ValueError("Answer reports work unavailable in the requested search scope")
    if scenario == "claude-memory-partial" and "locked.md" not in content:
        raise ValueError("Partial search answer must identify unreadable memory/locked.md")
    if scenario == "claude-memory-project-ambiguous":
        if not all(value in content for value in ("memory", "user-memory", "autoMemoryDirectory")):
            raise ValueError("Ambiguous source answer must list memory and user-memory with setting evidence")
    for value in {
        "claude-memory-project-missing": ("settings.local.json", "autoMemoryDirectory", "missing-memory"),
        "claude-memory-project-invalid": ("settings.local.json", "autoMemoryDirectory", "relative-memory"),
    }.get(scenario, ()):
        if value not in content:
            raise ValueError(f"Location diagnostic must identify {value}")
    verify_works(trial, content, WORKS[scenario], memory_directory(trial, scenario).parent)


def verify_works(trial: Path, content: str, works: tuple[ExpectedWork, ...], source_root: Path) -> None:
    """Check the shared heading/facts/citations contract for known fixture works."""
    sections = re.split(r"(?m)(?=^#{1,6} )", content)
    for work in works:
        matches = [section for section in sections if work.name in section.split("\n", 1)[0].casefold()]
        if len(matches) != 1:
            raise ValueError(f"Answer must report {work.name} once under its own heading")
        section = matches[0]
        for fact in work.facts:
            if fact not in section:
                raise ValueError(f"Answer lost the known {work.name} finding: {fact}")
        sources = cited_paths(trial, section)
        for source in work.sources:
            expected_source = (source_root / source).resolve()
            if expected_source not in sources:
                raise ValueError(f"Answer must cite the actual {work.name} source {expected_source}")


def cited_paths(trial: Path, content: str) -> set[Path]:
    """Accept relative/absolute Markdown citations with line or heading locators."""
    paths = set()
    for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", content):
        target = unquote(target.strip().strip("<>")).replace("\\", "/")
        target = re.sub(r":\d+(?::\d+)?$", "", target.split("#", 1)[0])
        if "://" in target:
            continue
        path = Path(target)
        if not path.is_absolute():
            path = trial / path if target.startswith("workspace/") else trial / "workspace" / path
        paths.add(path.resolve())
    return paths
