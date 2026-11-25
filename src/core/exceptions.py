"""Custom exceptions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime


# A provider's daily or monthly free quota is used up until blocked_until
class QuotaExhausted(Exception):
    def __init__(self, blocked_until: datetime) -> None:
        super().__init__(f"quota exhausted until {blocked_until.isoformat()}")
        self.blocked_until = blocked_until


# Every model in the chain failed with a transient error
class LLMUnavailable(Exception):
    pass


# A job used all the LLM calls it may make
class LLMBudgetExceeded(Exception):
    pass


# The model's structured output stayed invalid after repair
class InvalidLLMOutput(Exception):
    def __init__(self, errors: Sequence[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)
