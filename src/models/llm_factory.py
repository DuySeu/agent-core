"""The provider contract: one object per process, one SDK client, the model id passed per call."""

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

ProviderOutcome = Literal["rate_limited", "quota_exhausted", "timeout", "provider_error"]


@dataclass
class Message:
    role: str
    content: str | list[dict[str, Any]]


@dataclass
class LLMResponse:
    answer: str
    input_tokens: int
    output_tokens: int
    tool_calls: list[dict[str, Any]] | None = None
    original_response: Any = None


@dataclass
class StreamChunk:
    text: str | None = None
    tool_call: dict[str, Any] | None = None

    # Standard chunk:
    delta: str | None = None
    tool_call_chunk: dict[str, Any] | None = None  # {index, name, arguments_delta, id}


@dataclass
class EmbeddingResponse:
    # One vector per input text, in order
    vectors: list[list[float]]
    input_tokens: int


# An SDK or network failure, named the way the router handles it; any other exception is a bug
class ProviderCallError(Exception):
    def __init__(self, outcome: ProviderOutcome, message: str) -> None:
        super().__init__(message)
        self.outcome: ProviderOutcome = outcome


class LLMProvider(ABC):
    # Also the service name of the provider's quota block
    name: ClassVar[str]

    # Whether a configured model id can be sent to this provider; others are skipped by the router
    def accepts(self, model_id: str) -> bool:
        return True

    # response_format asks for JSON output: {"type": "json_object"} or {"type": "json_schema", ...}
    # Raises ProviderCallError for every SDK or network failure
    @abstractmethod
    def invoke(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> LLMResponse: ...

    # Raises ProviderCallError for every SDK or network failure, also after the first chunk
    @abstractmethod
    def invoke_stream(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        timeout_s: float | None = None,
    ) -> Iterator[StreamChunk]: ...


# Embedding models of the same provider object (and SDK client) as its LLMProvider side
class Embedder(ABC):
    # Also the service name of the provider's quota block
    name: ClassVar[str]

    def accepts(self, model_id: str) -> bool:
        return True

    # Raises ProviderCallError for every SDK or network failure
    @abstractmethod
    def embed(
        self, model_id: str, texts: Sequence[str], *, timeout_s: float | None = None
    ) -> EmbeddingResponse: ...
