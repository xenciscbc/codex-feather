# Feather delegation

Apply this delegation guidance only when scout, analyst, mech-executor, executor and security-executor are available in the current environment. If unavailable, report the missing capability and keep the work with the main Agent. This declaration does not install or enable roles.

Before delegating to a named or generic child, or performing an independent plan review, read the available `feather-delegation` skill. If the skill or required role is unavailable, report the missing capability and keep the work with the main Agent.

Automatic plan review mode: off
An explicit review request applies in either mode. In auto mode, read the skill before implementing a stable plan with a material security-boundary change, data migration, irreversible operation, or complex cross-module change. Small or routine tasks proceed directly.

Role defaults for dispatch (model / reasoning):

| Role | Model | Reasoning |
| --- | --- | --- |
| scout | gpt-6-luna | low |
| analyst | gpt-6-sol | high |
| mech-executor | gpt-6-luna | medium |
| executor | gpt-6-sol | medium |
| security-executor | gpt-6-sol | high |
