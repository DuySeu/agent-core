from abc import ABC, abstractmethod
from typing import Dict, Any, Union, Generator, List, Optional
from dataclasses import dataclass


@dataclass
class Message:
    role: str
    content: Union[str, List[Dict[str, Any]]]


@dataclass
class LLMResponse:
    answer: str
    input_tokens: int
    output_tokens: int
    tool_calls: Optional[List[Dict[str, Any]]] = None
    original_response: Any = None


@dataclass
class StreamChunk:
    text: Optional[str] = None
    tool_call: Optional[Dict[str, Any]] = None

    # Standard chunk:
    delta: Optional[str] = None
    tool_call_chunk: Optional[Dict[str, Any]] = (
        None  # {index, name, arguments_delta, id}
    )


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, model_id: str, inference_config: dict):
        self.model_id = model_id
        self.inference_config = inference_config

    @abstractmethod
    def invoke(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict]] = None,
    ) -> Union[Dict[str, Any], LLMResponse]:
        pass

    @abstractmethod
    def invoke_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict]] = None,
    ) -> Generator:
        pass
