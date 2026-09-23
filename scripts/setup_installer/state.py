"""Read ownership records without changing or retargeting their environment."""
import json

from .environment import Environment
from .transaction import Plan


def read_state(environment: Environment, plan: Plan) -> dict:
    saved = plan.read(environment.state_path)
    state = json.loads(saved) if saved is not None else {"format": 1, "environment": environment.identity, "components": {}}
    if not isinstance(state, dict) or state.get("format") != 1:
        raise ValueError("Unsupported installation record")
    if state.get("environment") != environment.identity:
        raise ValueError("Installation record belongs to a different environment. Use an explicit migration; no paths were retargeted.")
    if not isinstance(state.get("components"), dict):
        raise ValueError("Invalid installation components record")
    for component, record in state["components"].items():
        if not isinstance(record, dict) or not isinstance(record.get("files"), dict):
            raise ValueError(f"Invalid installation component record: {component}")
        if record.get("provider") is not None and not isinstance(record["provider"], dict):
            raise ValueError(f"Invalid installation provider record: {component}")
    return state
