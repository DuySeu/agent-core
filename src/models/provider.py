import functools
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import boto3
import httpx
import openai
import urllib3
from botocore import config as boto_config
from botocore import credentials as boto_credentials
from botocore import session as boto_session
from botocore.exceptions import BotoCoreError, ClientError, ConnectTimeoutError, ReadTimeoutError
from openai import OpenAI
from openrouter import OpenRouter
from openrouter import errors as openrouter_errors

from core.constants import ModelId

from .llm_factory import (
    Embedder,
    EmbeddingResponse,
    LLMProvider,
    LLMResponse,
    ProviderCallError,
    ProviderOutcome,
    StreamChunk,
)

KNOWN_MODEL_IDS = frozenset(
    value for name, value in vars(ModelId).items() if isinstance(value, str) and name[0] != "_"
)
# What an OpenRouter call raises for a model that is down or limited; anything else is a bug
OPENROUTER_ERRORS = (
    openrouter_errors.OpenRouterError,
    openrouter_errors.NoResponseError,
    httpx.HTTPError,
)
TIMEOUT_STATUSES = frozenset({408, 504, 524})
# urllib3 errors come from the raw body of an event stream, which botocore does not wrap
BEDROCK_ERRORS = (ClientError, BotoCoreError, urllib3.exceptions.HTTPError)
BEDROCK_RATE_LIMITED = frozenset(
    {"throttlingexception", "toomanyrequestsexception", "servicequotaexceededexception"}
)


class OpenAIProvider(LLMProvider, Embedder):
    name = "openai"

    def __init__(self, api_key: str) -> None:
        # No SDK retries: the router falls back to the next model, and timeout_s stays one call
        self.client = OpenAI(api_key=api_key, max_retries=0)

    def invoke(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> LLMResponse:
        kwargs = _openai_options(tools, timeout_s)
        if response_format:
            kwargs["response_format"] = dict(response_format)
        try:
            response = self.client.chat.completions.create(
                model=model_id, messages=_with_system(messages, system_prompt), **kwargs
            )
        except openai.APIError as exc:
            raise _openai_error(exc) from exc

        message = response.choices[0].message
        return LLMResponse(
            answer=message.content,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            tool_calls=_function_calls(message.tool_calls),
            original_response=response,
        )

    def invoke_stream(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        timeout_s: float | None = None,
    ) -> Iterator[StreamChunk]:
        try:
            stream = self.client.chat.completions.create(
                model=model_id,
                messages=_with_system(messages, system_prompt),
                stream=True,
                **_openai_options(tools, timeout_s),
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield StreamChunk(delta=delta.content)
                for tc in delta.tool_calls or []:
                    yield StreamChunk(
                        tool_call_chunk={
                            "index": tc.index,
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    )
        except openai.APIError as exc:
            raise _openai_error(exc) from exc

    def embed(
        self, model_id: str, texts: Sequence[str], *, timeout_s: float | None = None
    ) -> EmbeddingResponse:
        kwargs = {"timeout": timeout_s} if timeout_s is not None else {}
        try:
            response = self.client.embeddings.create(model=model_id, input=list(texts), **kwargs)
        except openai.APIError as exc:
            raise _openai_error(exc) from exc
        return EmbeddingResponse(
            vectors=[item.embedding for item in response.data],
            input_tokens=response.usage.prompt_tokens,
        )


# Name an OpenAI failure; a 429 for an account out of credit is the quota, any other 429 a rate limit
def _openai_error(exc: openai.APIError) -> ProviderCallError:
    outcome: ProviderOutcome = "provider_error"
    if isinstance(exc, openai.RateLimitError):
        outcome = "quota_exhausted" if exc.code == "insufficient_quota" else "rate_limited"
    elif isinstance(exc, openai.APITimeoutError) or (
        isinstance(exc, openai.APIStatusError) and exc.status_code in TIMEOUT_STATUSES
    ):
        outcome = "timeout"
    return ProviderCallError(outcome, f"{type(exc).__name__}: {exc}")


# Tools and the per-call timeout, as chat.completions.create keyword arguments
def _openai_options(tools: list[dict[str, Any]] | None, timeout_s: float | None) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if tools:
        options["tools"] = _function_tools(tools)
    if timeout_s is not None:
        options["timeout"] = timeout_s
    return options


class OpenRouterProvider(LLMProvider, Embedder):
    name = "openrouter"

    def __init__(self, api_key: str, daily_cap_pattern: str) -> None:
        self.client = OpenRouter(api_key=api_key)
        self._daily_cap_pattern = daily_cap_pattern

    # Only ids of ModelId: an id dropped by scripts/sync_models.sh is skipped, not paid for
    def accepts(self, model_id: str) -> bool:
        return model_id in KNOWN_MODEL_IDS

    def invoke(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = _openrouter_options(tools, timeout_s)
        # With response_format: route only to endpoints that support it (a model with none answers
        # 404, so the router tries the next one), and let OpenRouter repair malformed JSON
        # https://openrouter.ai/docs/features/structured-outputs
        if response_format:
            kwargs |= {
                "response_format": dict(response_format),
                "provider": {"require_parameters": True},
                "plugins": [{"id": "response-healing"}],
            }
        try:
            response = self.client.chat.send(
                model=model_id,
                messages=_with_system(messages, system_prompt),
                stream=False,
                **kwargs,
            )
        except OPENROUTER_ERRORS as exc:
            raise self._error(exc) from exc

        message = response.choices[0].message
        return LLMResponse(
            answer=message.content,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            tool_calls=_function_calls(message.tool_calls),
            original_response=response,
        )

    def invoke_stream(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        timeout_s: float | None = None,
    ) -> Iterator[StreamChunk]:
        try:
            stream = self.client.chat.send(
                model=model_id,
                messages=_with_system(messages, system_prompt),
                stream=True,
                **_openrouter_options(tools, timeout_s),
            )
            for event in stream:
                if not event.choices:
                    continue
                delta = event.choices[0].delta
                if delta.content:
                    yield StreamChunk(delta=delta.content)
                for tc in delta.tool_calls or []:
                    yield StreamChunk(
                        tool_call_chunk={
                            "index": tc.index,
                            "id": tc.id,
                            "name": tc.function.name if tc.function else None,
                            "arguments": tc.function.arguments if tc.function else None,
                        }
                    )
        except OPENROUTER_ERRORS as exc:
            raise self._error(exc) from exc

    def embed(
        self, model_id: str, texts: Sequence[str], *, timeout_s: float | None = None
    ) -> EmbeddingResponse:
        kwargs = {"timeout_ms": round(timeout_s * 1000)} if timeout_s is not None else {}
        try:
            response = self.client.embeddings.generate(model=model_id, input=list(texts), **kwargs)
        except OPENROUTER_ERRORS as exc:
            raise self._error(exc) from exc
        usage = response.usage
        return EmbeddingResponse(
            vectors=[list(item.embedding) for item in response.data],
            input_tokens=usage.prompt_tokens if usage else 0,
        )

    # Name the failure; the daily cap is told from a per-minute 429 by its text
    def _error(self, exc: Exception) -> ProviderCallError:
        outcome: ProviderOutcome = "provider_error"
        if isinstance(exc, openrouter_errors.OpenRouterError):
            if exc.status_code == 429:
                text = f"{exc.message} {exc.body}"
                capped = re.search(self._daily_cap_pattern, text, re.IGNORECASE)
                outcome = "quota_exhausted" if capped else "rate_limited"
            elif exc.status_code in TIMEOUT_STATUSES:
                outcome = "timeout"
        elif isinstance(exc, httpx.TimeoutException):
            outcome = "timeout"
        return ProviderCallError(outcome, f"{type(exc).__name__}: {exc}")


# The system prompt as the first message, for chat-completions style APIs
def _with_system(messages: Sequence[Mapping[str, Any]], system_prompt: str) -> list[dict[str, Any]]:
    return [{"role": "system", "content": system_prompt}, *(dict(m) for m in messages)]


# Anthropic-style tool schemas ({name, description, input_schema}) as OpenAI function tools
def _function_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            },
        }
        if "input_schema" in tool
        else tool
        for tool in tools
    ]


# The tool calls of a chat-completions message, or None
def _function_calls(tool_calls: Any) -> list[dict[str, Any]] | None:
    calls = [
        {
            "id": tc.id,
            "name": tc.function.name,
            "arguments": tc.function.arguments,
            "type": "function",
        }
        for tc in tool_calls or []
    ]
    return calls or None


# Tools and the per-call timeout, as chat.send keyword arguments
def _openrouter_options(
    tools: list[dict[str, Any]] | None, timeout_s: float | None
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if tools:
        options["tools"] = _function_tools(tools)
    if timeout_s is not None:
        options["timeout_ms"] = round(timeout_s * 1000)
    return options


class BedrockProvider(LLMProvider, Embedder):
    name = "bedrock"

    # Empty keys fall back to boto3's default credential chain (a server role, for example); with
    # role_arn the role's temporary credentials are fetched on first use and refreshed before expiry
    def __init__(
        self,
        region: str,
        access_key: str,
        secret_key: str,
        role_arn: str,
        read_timeout_s: float,
        max_tokens: int,
    ) -> None:
        session = boto3.Session(
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region,
        )
        if role_arn:
            refresh = functools.partial(role_credentials, session.client("sts"), role_arn)
            role_session = boto_session.get_session()
            # botocore has no public setter for a session's credentials object
            role_session._credentials = boto_credentials.DeferredRefreshableCredentials(
                refresh_using=refresh, method="sts-assume-role"
            )
            session = boto3.Session(botocore_session=role_session, region_name=region)
        # boto3 has no per-call timeout, so the client's read timeout covers the slowest purpose; no
        # retries, the router falls back to the next model
        client_config = boto_config.Config(
            read_timeout=read_timeout_s, retries={"total_max_attempts": 1}
        )
        self.client: Any = session.client("bedrock-runtime", config=client_config)
        self._max_tokens = max_tokens

    # Claude on Bedrock (Anthropic payload). JSON relies on the prompt and the router's repair, so
    # response_format is ignored; timeout_s too (see the client's read timeout)
    def invoke(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> LLMResponse:
        try:
            response = self.client.invoke_model(
                **self._payload(model_id, messages, system_prompt, tools)
            )
            body = json.loads(response["body"].read())
        except BEDROCK_ERRORS as exc:
            raise _bedrock_error(exc) from exc

        text = ""
        tool_calls = []
        for block in body.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
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
            answer=text,
            input_tokens=body["usage"]["input_tokens"],
            output_tokens=body["usage"]["output_tokens"],
            tool_calls=tool_calls or None,
            original_response=body,
        )

    def invoke_stream(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        timeout_s: float | None = None,
    ) -> Iterator[StreamChunk]:
        try:
            response = self.client.invoke_model_with_response_stream(
                **self._payload(model_id, messages, system_prompt, tools)
            )
            for event in response.get("body") or []:
                chunk = event.get("chunk")
                if not chunk:
                    continue
                data = json.loads(chunk["bytes"].decode())
                kind = data["type"]
                if kind == "content_block_delta" and data["delta"]["type"] == "text_delta":
                    yield StreamChunk(delta=data["delta"].get("text"))
                elif kind == "content_block_start" and data["content_block"]["type"] == "tool_use":
                    yield StreamChunk(
                        tool_call_chunk={
                            "index": data["index"],
                            "id": data["content_block"]["id"],
                            "name": data["content_block"]["name"],
                            "arguments": "",
                        }
                    )
                elif kind == "content_block_delta" and data["delta"]["type"] == "input_json_delta":
                    yield StreamChunk(tool_call_chunk={"arguments": data["delta"]["partial_json"]})
        except BEDROCK_ERRORS as exc:
            raise _bedrock_error(exc) from exc

    # Titan embeds one text per call (and counts its tokens); Cohere embeds the batch in one call
    def embed(
        self, model_id: str, texts: Sequence[str], *, timeout_s: float | None = None
    ) -> EmbeddingResponse:
        if model_id.startswith("amazon.titan-embed"):
            replies = [self._invoke_json(model_id, {"inputText": text}) for text in texts]
            return EmbeddingResponse(
                vectors=[reply["embedding"] for reply in replies],
                input_tokens=sum(reply.get("inputTextTokenCount", 0) for reply in replies),
            )
        if model_id.startswith("cohere.embed"):
            reply = self._invoke_json(
                model_id, {"texts": list(texts), "input_type": "search_document"}
            )
            return EmbeddingResponse(vectors=reply["embeddings"], input_tokens=0)
        raise ProviderCallError(
            "provider_error", f"{model_id} is not a Titan or Cohere embedding model"
        )

    # One invoke_model call with a JSON body, its JSON reply
    def _invoke_json(self, model_id: str, body: Mapping[str, Any]) -> Any:
        try:
            response = self.client.invoke_model(
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
                modelId=model_id,
            )
            return json.loads(response["body"].read())
        except BEDROCK_ERRORS as exc:
            raise _bedrock_error(exc) from exc

    # invoke_model arguments: Claude needs max_tokens and turns that alternate, starting with user
    def _payload(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        turns = [
            {
                "role": turn["role"],
                "content": [{"type": "text", "text": turn["content"]}]
                if isinstance(turn["content"], str)
                else turn["content"],
            }
            for turn in alternate_turns(messages)
        ]
        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self._max_tokens,
            "messages": turns,
            "system": system_prompt,
        }
        if tools:
            body["tools"] = tools
        return {
            "body": json.dumps(body),
            "contentType": "application/json",
            "accept": "application/json",
            "modelId": model_id,
        }


# Turns as Claude takes them: leading assistant turns dropped, same-role neighbours merged (text
# joined by a blank line; block lists concatenated, a text turn becoming one text block)
def alternate_turns(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for message in messages:
        role, content = message["role"], message["content"]
        if not turns and role != "user":
            continue
        if turns and turns[-1]["role"] == role:
            previous = turns[-1]["content"]
            if isinstance(previous, str) and isinstance(content, str):
                turns[-1]["content"] = f"{previous}\n\n{content}"
            else:
                turns[-1]["content"] = _blocks(previous) + _blocks(content)
            continue
        turns.append({"role": role, "content": content})
    return turns


def _blocks(content: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "text", "text": content}] if isinstance(content, str) else list(content)


# The role's temporary credentials in the form botocore's refreshable credentials read
def role_credentials(sts: Any, role_arn: str) -> dict[str, str]:
    credentials = sts.assume_role(RoleArn=role_arn, RoleSessionName="BedrockSession")["Credentials"]
    return {
        "access_key": credentials["AccessKeyId"],
        "secret_key": credentials["SecretAccessKey"],
        "token": credentials["SessionToken"],
        "expiry_time": credentials["Expiration"].isoformat(),
    }


# Name a Bedrock failure; Bedrock has no daily quota, so never quota_exhausted. Event-stream errors
# carry the code with a lower-case first letter (throttlingException)
def _bedrock_error(exc: Exception) -> ProviderCallError:
    outcome: ProviderOutcome = "provider_error"
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "").lower()
        if code in BEDROCK_RATE_LIMITED:
            outcome = "rate_limited"
        elif code == "modeltimeoutexception":
            outcome = "timeout"
    elif isinstance(
        exc, ReadTimeoutError | ConnectTimeoutError | urllib3.exceptions.ReadTimeoutError
    ):
        outcome = "timeout"
    return ProviderCallError(outcome, f"{type(exc).__name__}: {exc}")
