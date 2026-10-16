from typing import Dict, Any, Union, Generator
from .base import LLMProvider
from .provider import OpenAIProvider, OpenRouterProvider, BedrockProvider


class LLM:
    """Invoke the model and get the response (stateless)"""

    def __init__(
        self, system_prompt: str, inference_config: dict, provider: str, model_id: str
    ):
        self.system_prompt = system_prompt
        self.inference_config = inference_config
        self.provider = provider
        self.model_id = model_id

        if provider == "openai":
            self.llm: LLMProvider = OpenAIProvider(model_id, inference_config)
        elif provider == "openrouter":
            self.llm: LLMProvider = OpenRouterProvider(model_id, inference_config)
        else:
            self.llm: LLMProvider = BedrockProvider(model_id, inference_config)

    def invoke(self, message: Union[Dict[str, Any], str]) -> Dict:
        # construct message list from single message
        content = message
        if isinstance(message, dict):
            # adapt if needed, but assuming str or compatible dict
            # Original code extracted text content from dict in `_prepare_payload` or `invoke`
            if "content" in message:
                content = message["content"]

        # Original code used [{"role": "user", "content": content}]
        messages = [{"role": "user", "content": content}]

        response_obj = self.llm.invoke(messages, self.system_prompt)

        return {
            "answer": response_obj.answer,
            "input_tokens": response_obj.input_tokens,
            "output_tokens": response_obj.output_tokens,
        }

    def invoke_stream(self, message: Union[Dict[str, Any], str]) -> Generator:
        content = message
        if isinstance(message, dict):
            if "content" in message:
                content = message["content"]

        messages = [{"role": "user", "content": content}]

        stream = self.llm.invoke_stream(messages, self.system_prompt)

        for chunk in stream:
            if chunk.delta:
                yield chunk.delta
