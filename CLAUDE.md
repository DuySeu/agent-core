# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small, provider-agnostic agentic LLM framework in Python. A single set of classes (`LLM`, `Agent`, `RAG`) fronts three backends selected by a `provider` string: **`"openai"`** (standard OpenAI API), **`"openrouter"`** (the official `openrouter` SDK), and anything else → **AWS Bedrock** (Anthropic Claude models, via `boto3` with cross-account STS `assume_role`). The codebase was reorganized into a layered `src/` package following `docs/project_structure.jpg`; most layers are scaffolded but only a few are implemented (see "Implementation status").

## Commands

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# src/ is the source root - put it on PYTHONPATH to run anything
PYTHONPATH=src python tests/test_llm.py       # smoke scripts, NOT pytest - each has its own main()
PYTHONPATH=src python tests/test_agents/test_agent.py
PYTHONPATH=src python tests/test_tools/test_registry.py   # asserts tool discovery/registry
PYTHONPATH=src python tests/test_api/test_health.py   # boots the server, hits /health, shuts down

# run the FastAPI server (Swagger at /docs)
PYTHONPATH=src python -m uvicorn api.main:app --reload

docker compose up -d   # dev infra: Postgres, MinIO, Qdrant (not wired into code yet)
```

There is no build step, linter config, or pytest/CI setup. `tests/**/*.py` are manual smoke scripts you run directly (some assert, most just print). `Dockerfile` is empty.

Use `.venv` (Python 3.13); system `/usr/bin/python3` is 3.9 and too old. `tools/implementations/web_search_tool.py` uses `tavily-python` and needs `TAVILY_API_KEY` in `.env`; it lazy-imports the client, so the tool only fails when actually invoked without the key/package.

Credentials come from `.env` (loaded by `src/core/config.py` via `python-dotenv`; see `.env.example`): `OPENROUTER_API_KEY`, and for Bedrock `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_ROLE_ARN`. When `AWS_ROLE_ARN` is set, both `BedrockProvider` and `RAG` assume that role via STS before creating the client.

## Import convention

Code uses **absolute imports rooted at `src/`**: `from core.config import config`, `from models.provider import BedrockProvider`, `from agents.base_agent import Agent`. Nothing sets `sys.path` automatically (no `pyproject.toml`/`conftest.py`), so **`src/` must be on `PYTHONPATH`** to run or import anything. An `ImportError` is almost always a missing-path problem, not a wrong import.

## Architecture

Layered under `src/`, matching `docs/project_structure.jpg`:

- **core/** - cross-cutting configuration. `config.py` holds the `Config` settings class + `config` singleton (env creds). `constants.py` holds `ModelId` / `Region` enums + `model` / `region` singletons. `prompts.py` holds the reusable system-prompt templates (`prompt`, `prompt_for_web_search`, `text_to_query_prompt`). `exceptions.py` and `logger.py` are stubs.
- **models/** - the LLM provider layer. `base.py` defines the `LLMProvider` ABC and transport dataclasses (`Message`, `LLMResponse`, `StreamChunk`). `provider.py` has three concrete providers: **`OpenAIProvider`** (standard OpenAI API, `OPENAI_API_KEY`), **`OpenRouterProvider`** (the `openrouter` SDK's `client.chat.send`, `OPENROUTER_API_KEY`), and **`BedrockProvider`** (builds the `anthropic_version` payload, streams Bedrock event chunks). Both OpenAI-style providers convert Anthropic-style tool schemas to OpenAI function schemas via `_convert_tools`, and their `LLMResponse.tool_calls` share one normalized shape (`{id, name, arguments, type}`). `llm_factory.py` has **`LLM`**, a stateless single-shot wrapper that picks a provider from the `provider` string. `model_router.py` / `callbacks.py` are stubs.
- **agents/** - `base_agent.py` has **`Agent`**: stateful, holds `chat_history`, takes tools by name (`Agent(..., tools=["web_search"])` or `agent.add_tool("web_search")`, resolved through the tool registry), and drives the multi-turn tool-calling loop (call model → if `tool_calls`, run the registered funcs, append results, loop until a plain answer). `_manage_history` trims turns past `max_history`. `orchestrator_agent.py` / `research_agent.py` / `tool_executor_agent.py` are stubs.
- **tools/** - each tool is one `tools/implementations/<name>_tool.py` module with an Anthropic-format `SCHEMA` (`name` / `description` / `input_schema`, the canonical format; OpenAI-style providers convert on the fly) and a function decorated `@tool(SCHEMA)` (`base_tool.py`). The decorator registers it in the `registry` singleton (`tool_registry.py`), keyed by schema `name`; duplicate names raise. The file must end in `_tool.py` to be auto-imported by `implementations/__init__.py`, and import failures are logged and skipped, so a missing tool usually means its module failed to import. Real: `chart_tool`, `web_search_tool`, `otp_tool`; `time_tool` returns `None`; `calendar_tool` / `email_tool` are stubs.
- **knowledge/** - `retriever.py` has **`RAG`**: retrieves from an Amazon Bedrock Knowledge Base and mints presigned S3 URLs for source docs. `document_loader.py` / `text_splitter.py` / `rag_pipeline.py` are stubs.
- **api/** - FastAPI app (`api/main.py`): `GET /health`, `POST /chat` and `POST /chat/stream` (single-shot `LLM`, provider/model chosen per request, default `openrouter`). `routes/agents.py` is a stub.
- **memory/**, **orchestration/**, **utils/** - fully stubbed scaffolding.

**Provider selection is a string check duplicated in both `LLM` and `Agent`**: `"openai"` → `OpenAIProvider`, `"openrouter"` → `OpenRouterProvider`, anything else → `BedrockProvider`. The `provider` string also branches the message-formatting logic inside `Agent`: `provider in ("openai", "openrouter")` uses the OpenAI-style format (`role: "tool"` result messages + `tool_calls` on the assistant), while the Bedrock branch uses `tool_use` / `tool_result` content blocks. If you add a provider or touch tool wiring, update the selection in both classes **and** the four format branches in `Agent`.

## Implementation status

Only `core/config` + `core/constants` + `core/prompts`, `models/*` (except router/callbacks), `agents/base_agent`, `tools/base_tool` + `tools/tool_registry` + the real `implementations`, `knowledge/retriever`, and `api/` (health + chat) contain real code. Everything else is a one-line-docstring stub, intentionally left blank pending implementation; filling them in is the expected direction of work.

## Known rough edges

- `BedrockProvider.invoke` (`models/provider.py`) reads output tokens from `response.usage.completion_tokens` (an OpenAI-shaped attribute) instead of the Bedrock `usage["output_tokens"]`, a latent bug carried over from before the migration.
