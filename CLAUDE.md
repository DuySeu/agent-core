# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small, provider-agnostic agentic LLM framework in Python. A single set of classes (`Agent`, `OrchestratorAgent`, `RAG`) fronts three backends selected by a `provider` string through `core.wiring.build_llm`: **`"openai"`** (standard OpenAI API), **`"openrouter"`** (the official `openrouter` SDK), and anything else → **AWS Bedrock** (Anthropic Claude models, via `boto3` with cross-account STS `assume_role`). The codebase was reorganized into a layered `src/` package following `docs/project_structure.jpg`; most layers are scaffolded but only a few are implemented (see "Implementation status").

## Commands

```bash
UV_PROJECT_ENVIRONMENT=../.venv uv sync --inexact   # install pyproject.toml + uv.lock into the shared Lab venv

# src/ is the source root - put it on PYTHONPATH to run anything
PYTHONPATH=src ../.venv/bin/python tests/test_llm.py       # smoke scripts, NOT pytest - each has its own main()
PYTHONPATH=src ../.venv/bin/python tests/test_agents/test_agent.py
PYTHONPATH=src ../.venv/bin/python tests/test_tools/test_registry.py   # asserts tool discovery/registry
PYTHONPATH=src ../.venv/bin/python tests/test_api/test_health.py   # boots the server, hits /health, shuts down

# run the FastAPI server (Swagger at /docs)
PYTHONPATH=src ../.venv/bin/python -m uvicorn api.main:app --reload

docker compose up -d   # dev infra: Postgres, MinIO, Qdrant (not wired into code yet)
```

There is no build step, linter config, or pytest/CI setup. `tests/**/*.py` are manual smoke scripts you run directly (some assert, most just print). `Dockerfile` is empty.

Use the shared Lab venv at `../.venv` (Python 3.12, managed by uv, has no pip); system `/usr/bin/python3` is 3.9 and too old. Do not create a local `.venv` in this repo: no `python -m venv`, no `uv venv`, no `uv sync`/`uv run` without `UV_PROJECT_ENVIRONMENT=../.venv` (they create `./.venv`). Dependencies live in `pyproject.toml` + `uv.lock`: add one with `uv add --no-sync <pkg>`, then run the sync command above. Keep `--inexact` so packages of the other Lab repos stay installed. `tools/implementations/web_search_tool.py` uses `tavily-python` and needs `TAVILY_API_KEY` in `.env`; it lazy-imports the client, so the tool only fails when actually invoked without the key/package.

Credentials come from `.env` (loaded by `src/core/config.py` via `python-dotenv`; see `.env.example`): `OPENROUTER_API_KEY`, and for Bedrock `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_ROLE_ARN`. When `AWS_ROLE_ARN` is set, both `BedrockProvider` and `RAG` assume that role via STS; `BedrockProvider` fetches the role's credentials on first use and refreshes them before expiry.

## Import convention

Code uses **absolute imports rooted at `src/`**: `from core.config import config`, `from models.provider import BedrockProvider`, `from agents.base_agent import Agent`. Nothing sets `sys.path` automatically (`pyproject.toml` has no pytest config, no `conftest.py`), so **`src/` must be on `PYTHONPATH`** to run or import anything. An `ImportError` is almost always a missing-path problem, not a wrong import.

## Architecture

Layered under `src/`, matching `docs/project_structure.jpg`:

- **core/** - cross-cutting configuration. `config.py` holds the `Config` settings class + `config` singleton (env creds). `constants.py` holds `ModelId` / `Region` enums + `model` / `region` singletons. `prompts.py` holds the reusable system-prompt templates (`prompt`, `prompt_for_web_search`, `text_to_query_prompt`). `wiring.py` has **`build_llm(provider, max_tokens)`**, the one place a provider string becomes a provider object (credentials from `config`, Bedrock region `ap-southeast-1`). `exceptions.py` holds the exceptions `ModelRouter` raises (`QuotaExhausted`, `LLMUnavailable`, `LLMBudgetExceeded`, `InvalidLLMOutput`). `logger.py` is a stub.
- **models/** - the LLM provider layer, copied as-is from `../ai-trip-planner/src/models`; keep it identical and adapt agent-core around it rather than editing these files. `llm_factory.py` defines the contract: the `LLMProvider` and `Embedder` ABCs, the dataclasses (`Message`, `LLMResponse`, `StreamChunk`, `EmbeddingResponse`) and `ProviderCallError`, which every provider raises for any SDK or network failure, with an `outcome` (`rate_limited`, `quota_exhausted`, `timeout`, `provider_error`). A provider object holds one SDK client and takes the model id per call: `invoke(model_id, messages, system_prompt, *, tools, response_format, timeout_s)` and `invoke_stream(...)` yielding `StreamChunk`. `provider.py` has **`OpenAIProvider(api_key)`**, **`OpenRouterProvider(api_key, daily_cap_pattern)`** (only accepts ids listed in `ModelId`) and **`BedrockProvider(region, access_key, secret_key, role_arn, read_timeout_s, max_tokens)`** (Anthropic payload; merges same-role neighbour turns and drops leading assistant turns). OpenAI-style providers convert Anthropic-style tool schemas to function tools, and all three return `tool_calls` in one shape (`{id, name, arguments, type}`). No `inference_config` reaches the providers: temperature and top_p are not sent, max_tokens only applies to Bedrock. `model_router.py` has **`ModelRouter`** (an ordered fallback chain of model ids per purpose, call logging and quota blocks through a `CallSink`, a per-job `CallBudget`) and `call_json` (JSON output validated against a pydantic schema, one repair call per model); nothing in agent-core uses it yet, and its purposes and log fields (`trip_id`, ...) come from ai-trip-planner. `callbacks.py` is a stub.
- **agents/** - `base_agent.py` has **`Agent`**: stateful, holds `chat_history`, takes tools by name (`Agent(..., tools=["web_search"])` or `agent.add_tool("web_search")`, resolved through the tool registry), and drives the multi-turn tool-calling loop (call model → if `tool_calls`, run the registered funcs, append results, loop until a plain answer). `_manage_history` trims turns past `max_history`. `orchestrator_agent.py` has **`OrchestratorAgent`**: stateless, always on OpenRouter, `route(messages, catalog)` returns a `RoutingDecision` (one repair call on invalid output, `fallback` after two). `research_agent.py` / `tool_executor_agent.py` are stubs.
- **tools/** - each tool is one `tools/implementations/<name>_tool.py` module with an Anthropic-format `SCHEMA` (`name` / `description` / `input_schema`, the canonical format; OpenAI-style providers convert on the fly) and a function decorated `@tool(SCHEMA)` (`base_tool.py`). The decorator registers it in the `registry` singleton (`tool_registry.py`), keyed by schema `name`; duplicate names raise. The file must end in `_tool.py` to be auto-imported by `implementations/__init__.py`, and import failures are logged and skipped, so a missing tool usually means its module failed to import. Real: `chart_tool`, `web_search_tool`, `otp_tool`; `time_tool` returns `None`; `calendar_tool` / `email_tool` are stubs.
- **knowledge/** - `retriever.py` has **`RAG`**: retrieves from an Amazon Bedrock Knowledge Base and mints presigned S3 URLs for source docs. `document_loader.py` / `text_splitter.py` / `rag_pipeline.py` are stubs.
- **api/** - FastAPI app (`api/main.py`): `GET /health`, `POST /chat` and `POST /chat/stream` (one provider call per request via `build_llm`, provider/model chosen per request, default `openrouter`). `routes/agents.py` is a stub.
- **db/** - only `repositories/llm_calls.py` with the `LlmCallRecord` dataclass that `ModelRouter` hands to its sink; there is no database code.
- **orchestration/** - `routing_schema.py` (`AgentSpec`, `RoutingDecision`, ...) and `routing_parser.py` (`parse_output`) back `OrchestratorAgent`; the other modules are stubs.
- **memory/**, **utils/** - fully stubbed scaffolding.

**Provider selection lives only in `core.wiring.build_llm`**: `"openai"` → `OpenAIProvider`, `"openrouter"` → `OpenRouterProvider`, anything else → `BedrockProvider`. The `provider` string also branches the message-formatting logic inside `Agent`: `provider in ("openai", "openrouter")` uses the OpenAI-style format (`role: "tool"` result messages + `tool_calls` on the assistant), while the Bedrock branch uses `tool_use` / `tool_result` content blocks. If you add a provider or touch tool wiring, update `build_llm` **and** the four format branches in `Agent`.

## Implementation status

Only `core/config` + `core/constants` + `core/prompts` + `core/wiring` + `core/exceptions`, `models/*` (except callbacks), `agents/base_agent` + `agents/orchestrator_agent`, `orchestration/routing_schema` + `orchestration/routing_parser`, `tools/base_tool` + `tools/tool_registry` + the real `implementations`, `knowledge/retriever`, and `api/` (health + chat) contain real code. Everything else is a one-line-docstring stub, intentionally left blank pending implementation; filling them in is the expected direction of work.

## Known rough edges

- `api/routes/chat.py` and `tests/test_agents/test_agent.py` default to `model.NEMOTRON_3_NANO_30B_A3B`, and `tests/test_llm.py` uses `model.MIMO_V2_FLASH`; neither is in `ModelId` any more, so `api.main` fails to import (`AttributeError`) until they point at a listed id.

## Harness: orchestrator agent

**Goal:** Xây orchestrator agent trả `RoutingDecision` (structured output) để hệ thống điều phối tới agent phù hợp theo kiến trúc router, sequential, parallel.

**Trigger conditions:** Khi được yêu cầu build, thiết kế, sửa, mở rộng hoặc chạy lại phần orchestrator agent / routing agent, dùng skill `orchestrator-build`. Câu hỏi đơn giản về code có thể trả lời trực tiếp.

**Change history:**

| Date | Change | Target | Reason |
| --- | --- | --- | --- |
| 2026-10-27 | Initial setup with Harness v2 | All | - |
| 2026-10-27 | Skill trỏ tới spec làm nguồn duy nhất; bỏ schema baseline, đổi thành routing-cases.md; Bước 1 chỉ chạy khi chưa có spec | routing-contract, orchestrator-build | Spec orchestrator đã duyệt (OpenRouter, catalog do người gọi truyền) mâu thuẫn với harness ban đầu |
