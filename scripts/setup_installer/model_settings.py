"""Render and inspect the model table in managed delegation guidance."""
import re

from .bundle import ROLES


def values(content: str, allow_legacy: bool = False) -> dict[str, dict[str, str]]:
    result = {}
    for role in ROLES:
        pattern = rf"(?m)^\| {re.escape(role)} \| ([^|\r\n]+) \| ([^|\r\n]+) \|\r?$"
        matches = list(re.finditer(pattern, content))
        if allow_legacy and role == "security-executor" and not matches:
            continue
        if len(matches) != 1:
            raise ValueError(f"Managed delegation guidance has no unique {role} model row")
        result[role] = {"model": matches[0].group(1).strip(), "reasoning": matches[0].group(2).strip()}
    return result


def render(content: str, overrides: dict) -> str:
    baseline = values(content)  # Refuse to invent a table in a changed template.
    for role, fields in overrides.items():
        if role not in ROLES or not isinstance(fields, dict):
            raise ValueError(f"Invalid saved model override role: {role}")
        for field, value in fields.items():
            if field not in {"model", "reasoning"} or not isinstance(value, str):
                raise ValueError(f"Invalid saved model override field: {role}.{field}")
            if field == "model" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
                raise ValueError(f"Invalid saved model ID for {role}")
            if field == "reasoning" and value not in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}:
                raise ValueError(f"Invalid saved reasoning effort for {role}")
    for role in ROLES:
        chosen = {**baseline[role], **overrides.get(role, {})}
        pattern = rf"(?m)^\| {re.escape(role)} \| [^|\r\n]+ \| [^|\r\n]+ \|(\r?)$"
        content = re.sub(pattern, lambda match: f"| {role} | {chosen['model']} | {chosen['reasoning']} |" + match[1], content)
    return content
