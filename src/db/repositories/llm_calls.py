"""Log record of one LLM call, the shape ModelRouter hands to its CallSink."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


# One LLM call's outcome; no prompt or response text (privacy)
@dataclass(frozen=True)
class LlmCallRecord:
    purpose: str
    model_id: str
    outcome: str
    trip_id: UUID | None = None
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error: str | None = None
