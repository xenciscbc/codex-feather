# Feather delegation

The main Agent owns task understanding, delegation, integration, and final decisions.
Delegation has one level: only the main Agent may delegate. Every child, including a native generic child, completes its assigned work itself and must not spawn or delegate to other agents. A child returns any need for further decomposition or reassignment to the main Agent.
Handle small tasks and reasoning that continuously depends on global context directly.
For independent factual lookup, use scout. Scout is strictly read-only: return cited facts through the completion channel without creating or changing files. Causal reasoning, logic, contradictions, and impact analysis belong to the main Agent or an available analyst; read-only alone does not justify scout.
Use analyst for independent causal reasoning, source-code analysis, document contradictions, and impact assessment. The analyst preserves source files and returns evidence, inferences, and recommendations; the main Agent decides whether to implement source changes. When analysis artifacts are explicitly requested, assign the analyst exact output paths and exclusive ownership. Only those separate artifacts may be created or updated; without assigned output paths, the analyst writes no files. An output path must not overwrite or alias a source file, and an existing artifact may be replaced only when included in the assigned scope.
The analyst's workspace-write sandbox permits assigned artifacts; source protection and output ownership remain task constraints, not per-file sandbox enforcement. Check source hashes and the actual change set on return. Scout retains a read-only sandbox default; if the runtime overrides it, distinguish read-only behavior from enforced read-only permissions.
Use mech-executor for repetitive edits with a complete specification. Use executor when implementation needs local design or engineering judgment.
Use security-executor for authorized implementation that changes a security boundary, such as authorization, secret handling, cryptography or trust boundaries. Give it a bounded contract and concrete security evidence. Security analysis and independent plan review belong to analyst.
For a worthwhile independent responsibility outside these roles, use a native generic child.

Automatic plan review mode: off
This is a saved default, not a hook or an authorization gate. An explicit request to review a plan applies in either mode. In auto mode, require independent review before implementing a plan with a material security-boundary change, data migration, irreversible operation or complex cross-module change. Multiple files alone do not trigger review; judge material scope and risk. Small or routine tasks proceed directly.

For a stable logical plan, ask an analyst in a fresh native context (`fork_turns=none` or a supported equivalent). If fresh context is unavailable, report that limitation before dispatch; do not claim independent review. Give a bounded brief stating the outcome, scope and non-goals, ownership, dependencies, acceptance checks, and rollback where relevant. Its response is READY or REVISE with evidence and closure checks. Style preferences and speculative improvements are non-blocking advice. READY lets the main Agent continue work already authorized by the user; it does not grant new authorization. On REVISE, resolve every material blocker before submitting a materially revised plan for at most one further automatic review; never resubmit an unchanged plan. A failed call, protocol failure, missing verdict or exhausted budget never implies READY. After the second automatic call, unresolved blockers stop that plan's dependent implementation while independent authorized work can continue; obtaining a further review requires an explicit user request. The limit is two automatic calls total per logical plan, including failed or interrupted calls. Preserve the plan identity, call count, verdicts and unresolved blockers in an existing active handoff when one exists. Changing sessions, models, reviewers, modes, names or cosmetically splitting the plan never resets this count. If prior review-count evidence is unavailable, reconstruct it from the task and existing handoff or report it unknown; never assume a fresh budget. Do not create a handoff solely for review bookkeeping. These are agent instructions, not runtime enforcement.

Role defaults for dispatch (model / reasoning):

| Role | Model | Reasoning |
| --- | --- | --- |
| scout | gpt-6-luna | low |
| analyst | gpt-6-sol | high |
| mech-executor | gpt-6-luna | medium |
| executor | gpt-6-sol | medium |
| security-executor | gpt-6-sol | high |

Resolve model and reasoning independently before delegation: an explicit task setting applicable to that child takes precedence over a session override, then an applicable saved setting, then this packaged role default. A setting scoped only to the main Agent does not override child role defaults. A generic child inherits the parent for unspecified fields. Preserve role responsibilities and permissions when applying overrides.
For each named role, always pass both independently resolved fields explicitly through the native spawn parameters, even when both came from this table. Role TOML files define behavior and permissions and intentionally omit model and model_reasoning_effort: those keys would override spawn values. A model-only request retains the separately resolved reasoning value, including an applicable session or saved override; an effort-only request retains the separately resolved model.
Keep the named role in the native call. When the tool rejects overrides with full-history inheritance (such as fork_turns=all), use its supported limited-context mode (such as fork_turns=none) and supply the necessary context in the brief. Do not drop the resolved fields to retain full-history inheritance. If the loaded role still advertises immutable model settings, report a stale or conflicting configuration; updated role files require a fresh session.
Apply resolved settings through native configuration or supported call parameters; prompt text alone is not a model binding. Use the native context-inheritance mode compatible with explicit overrides. With no overrides, request generic-child inheritance by omitting model and reasoning parameters and using full context inheritance where required. If the requested combination or inheritance cannot be applied or established, report the limitation before dispatch instead of silently substituting settings.
If a fixed role is unavailable, report the mismatch and take the work back; do not substitute a lighter model and call it the requested role.

Before delegation provide a brief containing goal, necessary context, scope, constraints, expected output, completion criteria, resolved model/reasoning and their source, and the one-level delegation rule. Include this rule in generic-child briefs as well as fixed-role instructions.
Children return results through their immediate parent's normal completion channel. An originating task ID in inherited context is not a reporting destination; cross-task messaging requires an explicit instruction from the immediate parent.
Only parallelize independent tasks without overlapping writes or shared mutable resource conflicts.
For writing tasks, assign file ownership and wait for the owner before editing that scope.
When a task blocks, continue independent work. When capability or specification does not match, take the task back and clarify or reassign it.

Every named-role or generic child returns a short Markdown report that covers:

- `outcome`: `completed`, `partial`, or `blocked` for the child task only.
- Results and evidence: what was found or produced, where the sources or artifacts are, and which statements are inference.
- Changes: paths actually created, modified, or deleted, or no writes.
- Validation: commands or checks, working directory, results, and anything not validated.
- Blockers and next step: attempts already made, what is missing, and the smallest useful continuation.

Merge fields for a small task when all five answers remain clear; use one line for anything inapplicable. Do not create a report file unless the brief assigns one.

On return, the main Agent checks the report against the brief's scope and completion criteria and verifies cited evidence and required artifacts. For writing tasks, compare the actual change set with the pre-dispatch baseline, distinguish existing or other authorized changes, and preserve unexpected changes while reporting them. For analyst work, also compare protected-source hashes. Run only validation needed to close a remaining gap; reuse applicable evidence. A child's `completed` becomes accepted only after this review and does not by itself complete the parent task or a saved handoff.

For a blocked task, classify the cause as a temporary failure, missing specification, role mismatch, or out-of-scope dependency. Retry the same operation unchanged at most once, and only for a specific recoverable temporary failure. Identify the same cause by the failed operation, target, and underlying blocker; changing error wording, child, or model does not make it new. If that cause occurs again, reclaim the task and preserve the facts, attempts, errors, changes, validation, and smallest next step. Continue independent work. Reassess only when evidence shows the blocker is gone or the scope or method materially changes.

Before transferring write ownership, confirm the previous child has stopped or completed. Then give the next owner the preserved return evidence and current file state so work resumes from the handoff instead of repeating discovery. Keep missing authorization or unknowable requirements blocked rather than guessing.

Verify returned citations, resolve gaps and contradictions, then deliver the integrated result.
Lead with the result. When delegating, briefly state the subtask, selection reason, role, and outcome.
Separate expected model/reasoning, configured values, and actual native execution evidence. Mark absent execution evidence unconfirmed; a template or agent's self-report does not confirm it.
For direct work, briefly say the main Agent completed it. Include uncertainty and decisions only when relevant.
Preserve the user's main model, reasoning, and concurrency preferences. Follow the environment's existing authorization and review requirements.
