from typing import List, Dict, Any, Generator, Optional
import json
from models.base import LLMProvider
from models.provider import OpenAIProvider, OpenRouterProvider, BedrockProvider
from tools.tool_registry import registry


class Agent:
    def __init__(
        self,
        system_prompt: str,
        inference_config: dict,
        provider: str,
        model_id: str,
        max_history: int = 20,
        tools: Optional[List[str]] = None,
    ):
        self.system_prompt = system_prompt
        self.inference_config = inference_config
        self.provider = provider
        self.model_id = model_id
        self.max_history = max_history
        self.chat_history: List[Dict[str, Any]] = []
        self.tools = []
        self.tool_registry = {}

        # Initialize provider
        if provider == "openai":
            self.llm: LLMProvider = OpenAIProvider(model_id, inference_config)
        elif provider == "openrouter":
            self.llm: LLMProvider = OpenRouterProvider(model_id, inference_config)
        else:
            self.llm: LLMProvider = BedrockProvider(model_id, inference_config)

        # Resolve tools by name from the registry
        for name in tools or []:
            self.add_tool(name)

    def add_tool(self, name: str) -> None:
        """Register a tool on this agent by its (schema) name, via the registry.

        Idempotent: a name already registered is skipped so no duplicate schema
        is sent to the provider.
        """
        if name in self.tool_registry:
            return
        resolved = registry.get(name)  # raises ValueError on unknown name
        self.tools.append(resolved.schema)
        self.tool_registry[name] = resolved.func

    def _manage_history(self) -> None:
        if len(self.chat_history) >= self.max_history:
            self.chat_history = self.chat_history[4:]

    def invoke(self, message: str) -> Dict[str, Any]:
        if message:
            self.chat_history.append({"role": "user", "content": message})

        while True:
            response_obj = self.llm.invoke(
                messages=self.chat_history,
                system_prompt=self.system_prompt,
                tools=self.tools if self.tools else None,
            )

            # Check for tool calls
            if response_obj.tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": response_obj.answer,
                }

                # Hack: Use the provider name to decide format or try to be generic.
                if self.provider in ("openai", "openrouter"):
                    # We need to construct OpenAI compatible tool calls
                    openai_tool_calls = []
                    for tc in response_obj.tool_calls:
                        openai_tool_calls.append(
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": tc["arguments"],
                                },
                            }
                        )
                    assistant_msg["tool_calls"] = openai_tool_calls
                    # content can be null
                    if not assistant_msg["content"]:
                        assistant_msg["content"] = None
                else:
                    # Bedrock format
                    content = []
                    if response_obj.answer:
                        content.append({"type": "text", "text": response_obj.answer})

                    for tc in response_obj.tool_calls:
                        content.append(
                            {
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["name"],
                                "input": json.loads(tc["arguments"]),
                            }
                        )
                    assistant_msg["content"] = content

                self.chat_history.append(assistant_msg)

                for tc in response_obj.tool_calls:
                    func_name = tc["name"]
                    func_args_str = tc["arguments"]

                    try:
                        func_args = json.loads(func_args_str)
                    except json.JSONDecodeError:
                        func_args = {}

                    if func_name in self.tool_registry:
                        result = self.tool_registry[func_name](**func_args)

                        # Append tool result
                        if self.provider in ("openai", "openrouter"):
                            self.chat_history.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": str(result),
                                }
                            )
                        else:
                            self.chat_history.append(
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": tc["id"],
                                            "content": [
                                                {"type": "text", "text": str(result)}
                                            ],
                                        }
                                    ],
                                }
                            )
                continue
            else:
                answer = response_obj.answer
                self.chat_history.append({"role": "assistant", "content": answer})
                self._manage_history()
                return {
                    "answer": answer,
                    "input_tokens": response_obj.input_tokens,
                    "output_tokens": response_obj.output_tokens,
                }

    def invoke_stream(self, message: str) -> Generator:
        if message:
            self.chat_history.append({"role": "user", "content": message})

        while True:
            backend_stream = self.llm.invoke_stream(
                messages=self.chat_history,
                system_prompt=self.system_prompt,
                tools=self.tools if self.tools else None,
            )

            bot_response = ""
            # Map index to tool call dict
            active_tool_calls = {}

            for chunk in backend_stream:
                if chunk.delta:
                    bot_response += chunk.delta
                    yield chunk.delta

                if chunk.tool_call_chunk:
                    tc_chunk = chunk.tool_call_chunk
                    idx = tc_chunk.get("index", 0)  # Default 0 if not provided

                    if idx not in active_tool_calls:
                        active_tool_calls[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                            "type": "function",
                        }

                    if tc_chunk.get("id"):
                        active_tool_calls[idx]["id"] += tc_chunk["id"]
                    if tc_chunk.get("name"):
                        active_tool_calls[idx]["name"] += tc_chunk["name"]
                    if tc_chunk.get("arguments"):
                        active_tool_calls[idx]["arguments"] += tc_chunk["arguments"]

            # Process tool calls
            if active_tool_calls:
                # Convert to list
                tool_calls = list(active_tool_calls.values())

                # Construct assistant message
                assistant_msg = {
                    "role": "assistant",
                    "content": bot_response if bot_response else None,
                }

                if self.provider in ("openai", "openrouter"):
                    openai_tool_calls = []
                    for tc in tool_calls:
                        openai_tool_calls.append(
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": tc["arguments"],
                                },
                            }
                        )
                    assistant_msg["tool_calls"] = openai_tool_calls
                else:
                    content = []
                    if bot_response:
                        content.append({"type": "text", "text": bot_response})
                    for tc in tool_calls:
                        content.append(
                            {
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["name"],
                                "input": json.loads(tc["arguments"]),
                            }
                        )
                    assistant_msg["content"] = content

                self.chat_history.append(assistant_msg)

                for tc in tool_calls:
                    func_name = tc["name"]
                    func_args_str = tc["arguments"]
                    try:
                        func_args = json.loads(func_args_str)
                    except (json.JSONDecodeError, TypeError):
                        func_args = {}

                    if func_name in self.tool_registry:
                        result = self.tool_registry[func_name](**func_args)

                        if self.provider in ("openai", "openrouter"):
                            self.chat_history.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": str(result),
                                }
                            )
                        else:
                            self.chat_history.append(
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": tc["id"],
                                            "content": [
                                                {"type": "text", "text": str(result)}
                                            ],
                                        }
                                    ],
                                }
                            )
                continue
            else:
                if bot_response:
                    self.chat_history.append(
                        {"role": "assistant", "content": bot_response}
                    )
                self._manage_history()
                return
