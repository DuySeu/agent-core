"""Turn the orchestrator LLM's raw text into a validated LLMRoutingOutput."""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import ValidationError

from orchestration.routing_schema import AgentSpec, LLMRoutingOutput, check_semantics


# Extract, validate and semantically check one LLM answer; stop at the first failing layer
def parse_output(
    text: str | None, catalog: Sequence[AgentSpec]
) -> tuple[LLMRoutingOutput | None, list[str]]:
    # Layer 1: extract the first JSON value starting at the first "{"
    if not text or not text.strip():
        return None, ["response: empty, expected one JSON object"]
    start = text.find("{")
    if start == -1:
        return None, ["response: no JSON object found"]
    try:
        data, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as e:
        return None, [f"response: invalid or truncated JSON ({e.msg} at char {e.pos})"]
    if not isinstance(data, dict):
        return None, [f"response: expected a JSON object, got {type(data).__name__}"]

    # Layer 2: per-field format
    try:
        output = LLMRoutingOutput.model_validate(data)
    except ValidationError as e:
        return None, [
            f"{'.'.join(str(part) for part in err['loc']) or '(root)'}: {err['msg']}"
            for err in e.errors()
        ]

    # Layer 3: cross-field logic and agent names
    normalized, errors = check_semantics(output, catalog)
    if errors:
        return None, errors
    return normalized, []
