import boto3
from openai import OpenAI
from openrouter import OpenRouter
import json
from typing import List, Dict, Any, Generator, Optional
from core.config import config
from core.constants import region
from .base import LLMProvider, LLMResponse, StreamChunk


class OpenAIProvider(LLMProvider):
    def __init__(self, model_id: str, inference_config: dict):
        super().__init__(model_id, inference_config)
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
        )

    def _get_openai_config(self):
        return {
            k: v
            for k, v in self.inference_config.items()
            if k
            in [
                "max_tokens",
                "temperature",
                "top_p",
                "stop",
                "frequency_penalty",
                "presence_penalty",
            ]
        }

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        openai_tools = []
        for tool in tools:
            if "input_schema" in tool:
                # Anthropic format -> OpenAI format
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool["input_schema"],
                        },
                    }
                )
            else:
                openai_tools.append(tool)
        return openai_tools

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict]] = None,
    ) -> LLMResponse:
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        kwargs = {}
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=full_messages,
            **self._get_openai_config(),
            **kwargs,
        )

        message = response.choices[0].message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                        "type": "function",
                    }
                )

        return LLMResponse(
            answer=message.content,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            tool_calls=tool_calls if tool_calls else None,
            original_response=response,
        )

    def invoke_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict]] = None,
    ) -> Generator[StreamChunk, None, None]:
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        kwargs = {}
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        stream = self.client.chat.completions.create(
            model=self.model_id,
            messages=full_messages,
            stream=True,
            **self._get_openai_config(),
            **kwargs,
        )

        for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta

                if delta.content:
                    yield StreamChunk(delta=delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        yield StreamChunk(
                            tool_call_chunk={
                                "index": tc.index,
                                "id": tc.id,
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        )


class OpenRouterProvider(LLMProvider):
    def __init__(self, model_id: str, inference_config: dict):
        super().__init__(model_id, inference_config)
        self.client = OpenRouter(api_key=config.OPENROUTER_API_KEY)

    def _get_openai_config(self):
        return {
            k: v
            for k, v in self.inference_config.items()
            if k
            in [
                "max_tokens",
                "temperature",
                "top_p",
                "stop",
                "frequency_penalty",
                "presence_penalty",
            ]
        }

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        openai_tools = []
        for tool in tools:
            if "input_schema" in tool:
                # Anthropic format -> OpenAI (function) format
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool["input_schema"],
                        },
                    }
                )
            else:
                openai_tools.append(tool)
        return openai_tools

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict]] = None,
    ) -> LLMResponse:
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        kwargs = {}
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self.client.chat.send(
            model=self.model_id,
            messages=full_messages,
            stream=False,
            **self._get_openai_config(),
            **kwargs,
        )

        message = response.choices[0].message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                        "type": "function",
                    }
                )

        return LLMResponse(
            answer=message.content,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            tool_calls=tool_calls if tool_calls else None,
            original_response=response,
        )

    def invoke_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict]] = None,
    ) -> Generator[StreamChunk, None, None]:
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        kwargs = {}
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        stream = self.client.chat.send(
            model=self.model_id,
            messages=full_messages,
            stream=True,
            **self._get_openai_config(),
            **kwargs,
        )

        for event in stream:
            if event.choices and len(event.choices) > 0:
                delta = event.choices[0].delta

                if delta.content:
                    yield StreamChunk(delta=delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        yield StreamChunk(
                            tool_call_chunk={
                                "index": tc.index,
                                "id": tc.id,
                                "name": tc.function.name if tc.function else None,
                                "arguments": tc.function.arguments
                                if tc.function
                                else None,
                            }
                        )


class BedrockProvider(LLMProvider):
    def __init__(self, model_id: str, inference_config: dict):
        super().__init__(model_id, inference_config)
        self.session = boto3.Session(
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=region.AP_SOUTHEAST_1,
        )
        self.client = self._create_client()

    def _create_client(self, service_name: str = "bedrock-runtime"):
        # Explicit check for config.AWS_ROLE_ARN to assume role
        if config.AWS_ROLE_ARN:
            sts_client = self.session.client("sts")
            assumed_role = sts_client.assume_role(
                RoleArn=config.AWS_ROLE_ARN, RoleSessionName="BedrockSession"
            )
            credentials = assumed_role["Credentials"]
            return boto3.client(
                service_name=service_name,
                region_name=region.AP_SOUTHEAST_1,
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )
        return self.session.client(
            service_name=service_name, region_name=region.AP_SOUTHEAST_1
        )

    def _prepare_payload(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict]] = None,
    ) -> dict:
        bedrock_messages = []
        for msg in messages:
            if isinstance(msg["content"], str):
                bedrock_messages.append(
                    {
                        "role": msg["role"],
                        "content": [{"type": "text", "text": msg["content"]}],
                    }
                )
            else:
                bedrock_messages.append(msg)

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            **self.inference_config,
            "messages": bedrock_messages,
            "system": system_prompt,
        }

        if tools:
            body["tools"] = tools

        return {
            "body": json.dumps(body),
            "contentType": "application/json",
            "accept": "application/json",
            "modelId": self.model_id,
        }

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict]] = None,
    ) -> LLMResponse:
        payload = self._prepare_payload(messages, system_prompt, tools)
        response = self.client.invoke_model(**payload)
        response_body = json.loads(response.get("body").read())

        content_blocks = response_body.get("content", [])
        text_content = ""
        tool_calls = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input")),
                        "type": "tool_use",
                    }
                )

        return LLMResponse(
            answer=text_content,
            input_tokens=response_body["usage"]["input_tokens"],
            output_tokens=response.usage.completion_tokens,
            tool_calls=tool_calls if tool_calls else None,
            original_response=response_body,
        )

    def invoke_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict]] = None,
    ) -> Generator[StreamChunk, None, None]:
        payload = self._prepare_payload(messages, system_prompt, tools)
        response = self.client.invoke_model_with_response_stream(**payload)
        stream = response.get("body")

        if stream:
            for event in stream:
                chunk = event.get("chunk")
                if chunk:
                    data = json.loads(chunk.get("bytes").decode())

                    if (
                        data["type"] == "content_block_delta"
                        and data["delta"]["type"] == "text_delta"
                    ):
                        yield StreamChunk(delta=data["delta"].get("text"))

                    elif (
                        data["type"] == "content_block_start"
                        and data["content_block"]["type"] == "tool_use"
                    ):
                        yield StreamChunk(
                            tool_call_chunk={
                                "index": data["index"],
                                "id": data["content_block"]["id"],
                                "name": data["content_block"]["name"],
                                "arguments": "",
                            }
                        )

                    elif (
                        data["type"] == "content_block_delta"
                        and data["delta"]["type"] == "input_json_delta"
                    ):
                        yield StreamChunk(
                            tool_call_chunk={"arguments": data["delta"]["partial_json"]}
                        )
