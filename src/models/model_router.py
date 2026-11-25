"""Model routing: an ordered fallback chain per purpose, call logging, quota blocks and a call budget."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, NoReturn, Protocol
from uuid import UUID

from pydantic import BaseModel, ValidationError

from core.exceptions import InvalidLLMOutput, LLMBudgetExceeded, LLMUnavailable, QuotaExhausted
from db.repositories.llm_calls import LlmCallRecord
from models.llm_factory import Embedder, LLMProvider, LLMResponse, ProviderCallError

Purpose = Literal[
    "generate", "repair", "classify", "edit", "answer", "discover", "suggest", "guard", "embed"
]
Outcome = Literal[
    "ok", "rate_limited", "quota_exhausted", "timeout", "provider_error", "invalid_output"
]

logger = logging.getLogger(__name__)

MAX_ERROR_CHARS = 300
# What each purpose does, for the log line of a call
STEPS: Mapping[Purpose, str] = {
    "classify": "pick the chat flow",
    "answer": "write the chat reply",
    "edit": "turn the request into a plan edit",
    "discover": "read the chat for the trip draft",
    "suggest": "suggest destinations",
    "guard": "check the chat message is about travel",
    "generate": "write the trip plan",
    "repair": "fix invalid JSON",
    "embed": "embed text for similarity",
}


# The LLM calls one job attempt may still make; the only mutable object here
@dataclass
class CallBudget:
    limit: int
    used: int = 0

    # Count one call, or refuse it when the limit is reached
    def take(self) -> None:
        if self.used >= self.limit:
            raise LLMBudgetExceeded(f"LLM call budget of {self.limit} is used up")
        self.used += 1


# What a call belongs to, for the log and the budget
@dataclass(frozen=True)
class CallContext:
    trip_id: UUID | None = None
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    budget: CallBudget | None = None


# Where call records and quota blocks are kept
class CallSink(Protocol):
    # Store one call record
    def log(self, record: LlmCallRecord) -> None: ...

    # Block a service until its quota resets
    def block(self, service: str, until: datetime, reason: str) -> None: ...

    # When the service's block ends, or None
    def blocked_until(self, service: str) -> datetime | None: ...


class ModelRouter:
    def __init__(
        self,
        llm: LLMProvider,
        models: Mapping[Purpose, Sequence[str]],
        sink: CallSink,
        reset_hour_utc: int,
        now: Callable[[], datetime],
        timeouts: Mapping[Purpose, float] | None = None,
    ) -> None:
        self._llm = llm
        self._models = models
        self._sink = sink
        self._reset_hour_utc = reset_hour_utc
        self._now = now
        self._timeouts = timeouts or {}

    # The quota service of the provider in use
    @property
    def service(self) -> str:
        return self._llm.name

    # The configured model ids for a purpose, in order, without ids the provider does not accept
    def models_for(self, purpose: Purpose) -> list[str]:
        return [m for m in self._models.get(purpose, ()) if self._llm.accepts(m)]

    # One call to one model: checks the block, takes the budget, logs, maps errors. timeout_purpose
    # picks the timeout when it differs from the logged purpose (a repair keeps its flow's timeout)
    def invoke_model(
        self,
        model_id: str,
        purpose: Purpose,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        ctx: CallContext,
        response_format: Mapping[str, Any] | None = None,
        timeout_purpose: Purpose | None = None,
    ) -> LLMResponse:
        self._begin(ctx)
        started = time.monotonic()
        try:
            response = self._llm.invoke(
                model_id,
                messages,
                system_prompt,
                response_format=response_format,
                timeout_s=self._timeouts.get(timeout_purpose or purpose),
            )
        except ProviderCallError as exc:
            self._log(model_id, purpose, ctx, exc.outcome, started, error=exc)
            self._raise_for(exc.outcome, exc)
        self._log(
            model_id,
            purpose,
            ctx,
            "ok",
            started,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
        return response

    # Try the models of the purpose in order and return the answer with the model that gave it
    def invoke_with_model(
        self,
        purpose: Purpose,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        ctx: CallContext,
        response_format: Mapping[str, Any] | None = None,
    ) -> tuple[LLMResponse, str]:
        for model_id in self.models_for(purpose):
            try:
                response = self.invoke_model(
                    model_id, purpose, messages, system_prompt, ctx, response_format
                )
                return response, model_id
            except LLMUnavailable:
                continue
        raise LLMUnavailable(f"no model answered for purpose {purpose}")

    # Same as invoke_with_model, without the model id
    def invoke(
        self,
        purpose: Purpose,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        ctx: CallContext,
        response_format: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        return self.invoke_with_model(purpose, messages, system_prompt, ctx, response_format)[0]

    # Embed texts with one model: checks the block, takes the budget, logs, maps errors. A reply
    # without one vector per text is invalid output, so the caller can try the next model
    def embed_model(
        self, model_id: str, texts: Sequence[str], ctx: CallContext
    ) -> list[list[float]]:
        if not isinstance(self._llm, Embedder):
            raise LLMUnavailable(f"provider {self.service} has no embedding models")
        self._begin(ctx)
        started = time.monotonic()
        try:
            response = self._llm.embed(model_id, texts, timeout_s=self._timeouts.get("embed"))
        except ProviderCallError as exc:
            self._log(model_id, "embed", ctx, exc.outcome, started, error=exc)
            self._raise_for(exc.outcome, exc)
        if len(response.vectors) != len(texts):
            error = f"{len(response.vectors)} vectors for {len(texts)} texts"
            self._log(model_id, "embed", ctx, "invalid_output", started, error=ValueError(error))
            raise LLMUnavailable(f"invalid_output: {error}")
        self._log(
            model_id,
            "embed",
            ctx,
            "ok",
            started,
            input_tokens=response.input_tokens,
            output_tokens=0,
        )
        return response.vectors

    # Embed texts with model_id, or with the first model of the embed chain that answers
    def embed(
        self, texts: Sequence[str], ctx: CallContext, model_id: str | None = None
    ) -> list[list[float]]:
        if model_id is not None:
            return self.embed_model(model_id, texts, ctx)
        if not isinstance(self._llm, Embedder):
            raise LLMUnavailable(f"provider {self.service} has no embedding models")
        for candidate in self.models_for("embed"):
            try:
                return self.embed_model(candidate, texts, ctx)
            except LLMUnavailable:
                continue
        raise LLMUnavailable("no model answered for purpose embed")

    # Stream text; the next model is tried only while no token was sent yet
    def stream(
        self,
        purpose: Purpose,
        messages: Sequence[Mapping[str, Any]],
        system_prompt: str,
        ctx: CallContext,
    ) -> Iterator[str]:
        for model_id in self.models_for(purpose):
            self._begin(ctx)
            started = time.monotonic()
            sent = False
            outcome: Outcome = "ok"
            error: Exception | None = None
            try:
                for chunk in self._llm.invoke_stream(
                    model_id, messages, system_prompt, timeout_s=self._timeouts.get(purpose)
                ):
                    if chunk.delta:
                        sent = True
                        yield chunk.delta
                return
            except ProviderCallError as exc:
                outcome = exc.outcome
                error = exc
                if sent or outcome == "quota_exhausted":
                    self._raise_for(outcome, exc)
            finally:
                self._log(model_id, purpose, ctx, outcome, started, error=error)
        raise LLMUnavailable(f"no model answered for purpose {purpose}")

    # Refuse while the service is blocked, then count the call against the budget
    def _begin(self, ctx: CallContext) -> None:
        until = self._sink.blocked_until(self.service)
        if until is not None and until > self._now():
            raise QuotaExhausted(until)
        if ctx.budget is not None:
            ctx.budget.take()

    # The next reset_hour_utc:00 strictly after now
    def _next_reset(self) -> datetime:
        now = self._now()
        reset = now.replace(hour=self._reset_hour_utc, minute=0, second=0, microsecond=0)
        return reset if reset > now else reset + timedelta(days=1)

    # Turn a failed call into the exception callers handle; a daily cap also blocks the service
    def _raise_for(self, outcome: Outcome, exc: Exception) -> NoReturn:
        if outcome == "quota_exhausted":
            until = self._next_reset()
            self._sink.block(self.service, until, str(exc)[:MAX_ERROR_CHARS])
            raise QuotaExhausted(until) from exc
        raise LLMUnavailable(f"{outcome}: {exc}"[:MAX_ERROR_CHARS]) from exc

    # Record one call's outcome; never the prompt or the answer
    def _log(
        self,
        model_id: str,
        purpose: Purpose,
        ctx: CallContext,
        outcome: Outcome,
        started: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error: Exception | None = None,
    ) -> None:
        latency_ms = round((time.monotonic() - started) * 1000)
        # A ProviderCallError's text already names the SDK error
        error_text = None
        if error is not None:
            text = (
                str(error)
                if isinstance(error, ProviderCallError)
                else f"{type(error).__name__}: {error}"
            )
            error_text = text[:MAX_ERROR_CHARS]
        self._sink.log(
            LlmCallRecord(
                purpose=purpose,
                model_id=model_id,
                outcome=outcome,
                trip_id=ctx.trip_id,
                conversation_id=ctx.conversation_id,
                message_id=ctx.message_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                error=error_text,
            )
        )

        # One readable line per call, next to the generic httpx request line
        tokens = f", {input_tokens} in / {output_tokens} out tokens" if input_tokens else ""
        logger.log(
            logging.INFO if outcome == "ok" else logging.WARNING,
            "llm call %s (%s) via %s: %s in %d ms%s%s",
            purpose,
            STEPS[purpose],
            model_id,
            outcome,
            latency_ms,
            tokens,
            f", {error_text}" if error_text else "",
        )


REPAIR_PROMPT = """Your previous reply could not be used. Errors, one per line:
{errors}

Fix every error above and reply again with the corrected answer to the same request.
Return exactly one JSON object that validates against the schema, with no text before or after it and no code fence.
"""


# A validated model output and the model that produced it
@dataclass(frozen=True)
class JsonResult[T: BaseModel]:
    value: T
    model_id: str


# The first JSON object in the text, skipping prose and code fences, or the reasons there is none
def extract_json_object(text: str | None) -> tuple[dict[str, Any] | None, list[str]]:
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
    return data, []


# Call the models of the purpose in order; each gets one repair call showing its answer and the errors
def call_json[T: BaseModel](
    router: ModelRouter,
    purpose: Purpose,
    system_prompt: str,
    messages: Sequence[Mapping[str, Any]],
    schema: type[T],
    check: Callable[[T], list[str]] | None,
    ctx: CallContext,
    drop: Mapping[str, AbstractSet[str]] | None = None,
) -> JsonResult[T]:
    # The same schema the prompt shows (drop hides fields set by code). Not strict: strict mode
    # needs every field required with no defaults, which these schemas do not keep
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "strict": False,
            "schema": response_schema(schema, drop or {}),
        },
    }
    last_errors: list[str] = []
    for model_id in router.models_for(purpose):
        attempt_purpose: Purpose = purpose
        attempt_messages = list(messages)
        for _ in range(2):
            try:
                response = router.invoke_model(
                    model_id,
                    attempt_purpose,
                    attempt_messages,
                    system_prompt,
                    ctx,
                    response_format,
                    timeout_purpose=purpose,
                )
            except LLMUnavailable:
                break
            data, errors = extract_json_object(response.answer)
            value: T | None = None
            if data is not None:
                try:
                    value = schema.model_validate(data)
                except ValidationError as e:
                    errors = [
                        f"{'.'.join(str(part) for part in err['loc']) or '(root)'}: {err['msg']}"
                        for err in e.errors()
                    ]
            if value is not None:
                errors = check(value) if check else []
                if not errors:
                    return JsonResult(value, model_id)
            last_errors = errors
            attempt_purpose = "repair"
            attempt_messages = [
                *messages,
                {"role": "assistant", "content": response.answer or "(empty)"},
                {"role": "user", "content": REPAIR_PROMPT.format(errors="\n".join(errors))},
            ]
    if last_errors:
        raise InvalidLLMOutput(last_errors)
    raise LLMUnavailable(f"no model answered for purpose {purpose}")


# Keys that only add size: display titles and defaults
NOISE_KEYS = frozenset({"title", "default"})


# Copy a schema node without the noise keys; the keys of a "properties" map are field names, kept
def _strip(node: Any, drop: Mapping[str, AbstractSet[str]], owner: str | None = None) -> Any:
    if isinstance(node, list):
        return [_strip(n, drop) for n in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            hidden = drop.get(owner or "", frozenset())
            out[key] = {k: _strip(v, drop) for k, v in value.items() if k not in hidden}
        elif key == "required" and isinstance(value, list):
            hidden = drop.get(owner or "", frozenset())
            out[key] = [k for k in value if k not in hidden]
        elif key == "$defs" and isinstance(value, dict):
            out[key] = {name: _strip(v, drop, name) for name, v in value.items()}
        elif key not in NOISE_KEYS:
            out[key] = _strip(value, drop)
    return out


# The model's JSON schema without titles, defaults or the dropped fields
# drop maps a model class name to the field names to hide, such as {"PlanItem": {"id"}}
def response_schema(model: type[BaseModel], drop: Mapping[str, AbstractSet[str]]) -> Any:
    return _strip(model.model_json_schema(), drop, model.__name__)


# The same schema as one compact line, for the prompt
def compact_schema(model: type[BaseModel], drop: Mapping[str, AbstractSet[str]]) -> str:
    return json.dumps(response_schema(model, drop), separators=(",", ":"), ensure_ascii=True)
