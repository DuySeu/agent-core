# agent-core

Framework agentic LLM viết bằng Python, không phụ thuộc provider: cùng một bộ class (`LLM`, `Agent`, `RAG`) chạy trên OpenAI, OpenRouter hoặc AWS Bedrock, chọn bằng chuỗi `provider`. Code chia thành 9 layer trong `src/` theo sơ đồ `docs/project_structure.jpg`; chi tiết từng module ở `docs/architecture.md`.

## Cài đặt

Cần Python 3.13 (`/usr/bin/python3` của macOS là 3.9, quá cũ).

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # điền key
```

Biến môi trường trong `.env`:

| Biến | Dùng cho |
| --- | --- |
| `OPENROUTER_API_KEY` | `provider="openrouter"` và orchestrator agent |
| `OPENAI_API_KEY` | `provider="openai"` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ROLE_ARN` | Bedrock và `RAG` (assume role qua STS khi có `AWS_ROLE_ARN`) |
| `TAVILY_API_KEY` | tool `web_search` |

## Chạy

Mọi import đều tuyệt đối theo gốc `src/`, nên phải đặt `src/` vào `PYTHONPATH` (trừ `main.py`, tự thêm vào `sys.path`).

```bash
# chạy thử orchestrator agent (model và request sửa trực tiếp trong main.py)
python main.py orchestrator

# FastAPI server, Swagger UI ở http://127.0.0.1:8000/docs
PYTHONPATH=src uvicorn api.main:app --reload

# hạ tầng dev: Postgres, MinIO, Qdrant (chưa nối vào code)
docker compose up -d

# cập nhật danh sách model miễn phí của OpenRouter (chat, embed, rerank) vào src/core/constants.py
./scripts/sync_models.sh
```

## Test

`tests/` là các script smoke chạy trực tiếp, không phải pytest.

```bash
PYTHONPATH=src python tests/test_llm.py                            # LLM streaming, gọi model thật
PYTHONPATH=src python tests/test_agents/test_agent.py              # Agent + tool calling, gọi model thật
PYTHONPATH=src python tests/test_agents/test_routing_contract.py   # schema + parser RoutingDecision, không cần key
PYTHONPATH=src python tests/test_agents/test_orchestrator_agent.py # OrchestratorAgent với FakeProvider, không cần key
PYTHONPATH=src python tests/test_agents/eval_routing_live.py       # eval routing trên model OpenRouter thật, chỉ in kết quả
```

## Cấu trúc

| Layer | Đã có code | Còn là stub |
| --- | --- | --- |
| `core/` | `config.py` (đọc `.env`), `constants.py` (`ModelId`, `Region`), `prompts.py` | `exceptions.py`, `logger.py` |
| `models/` | `base.py` (`LLMProvider`, `Message`, `LLMResponse`, `StreamChunk`), `provider.py` (OpenAI, OpenRouter, Bedrock), `llm_factory.py` (`LLM`) | `model_router.py`, `callbacks.py` |
| `agents/` | `base_agent.py` (`Agent` có history và vòng lặp tool), `orchestrator_agent.py` (trả `RoutingDecision`) | `research_agent.py`, `tool_executor_agent.py` |
| `orchestration/` | `routing_schema.py`, `routing_parser.py` | `agent_orchestrator.py`, `task_planner.py`, `state_manager.py` |
| `tools/` | `base_tool.py` (`@tool`), `tool_registry.py`, `implementations/` gồm `chart_tool`, `web_search_tool`, `otp_tool` | `time_tool` (có schema, hàm trả `None`), `calendar_tool`, `email_tool` |
| `memory/` | | `memory_manager.py`, `vector_store.py`, `embeddings.py` |
| `knowledge/` | `retriever.py` (`RAG` trên Bedrock Knowledge Base) | `document_loader.py`, `text_splitter.py`, `rag_pipeline.py` |
| `api/` | `main.py`, `routes/health.py` (`GET /health`), `routes/chat.py` (`POST /chat`, `POST /chat/stream`) | `routes/agents.py` |
| `utils/` | | `helpers.py`, `validators.py` |

Ngoài `src/`: `main.py` (runner thử từng thành phần), `scripts/sync_models.sh`, `docs/` (`architecture.md`, `project_structure.jpg`, spec orchestrator `2026-10-27-orchestrator-agent-design.md`), `docker-compose.yml`. `Dockerfile` đang trống, `docs/api-docs.md` mới có tiêu đề.

Thêm tool mới: tạo `src/tools/implementations/<name>_tool.py` có một `SCHEMA` (format Anthropic) và một hàm gắn `@tool(SCHEMA)`, rồi gọi theo tên: `Agent(..., tools=["<name>"])`.
