# Architecture

`agent-core` là một framework agentic LLM viết bằng Python, thiết kế **provider-agnostic**: cùng một bộ class (`LLM`, `Agent`, `RAG`) chạy được trên nhiều backend model khác nhau. Code được tổ chức thành 9 layer trong `src/`, mỗi layer một trách nhiệm rõ ràng.

- **Nguồn code gốc là `src/`** — mọi import đều tuyệt đối theo gốc này (`from core.config import config`, `from agents.base_agent import Agent`). Vì vậy khi chạy/test phải đặt `src/` vào `PYTHONPATH`.
- Ký hiệu trạng thái dưới đây: ✅ = đã triển khai (có code chạy được), ⛔ = stub (mới là file rỗng/1 dòng docstring, chờ implement).

---

## Cây thư mục

```
agent-core/
├── .env / .env.example          # Biến môi trường (credentials) + file mẫu
├── .gitignore
├── README.md
├── LICENSE
├── requirements.txt             # Dependencies Python
├── Dockerfile                   # Image build (đang trống)
├── docker-compose.yml           # Postgres + MinIO + Qdrant (hạ tầng dev)
├── CLAUDE.md                    # Hướng dẫn cho Claude Code
│
├── docs/                        # Tài liệu
│   ├── architecture.md          #   (file này)
│   ├── api-docs.md
│   └── project_structure.jpg    #   Sơ đồ cấu trúc tham chiếu
│
├── infra/                       # Hạ tầng triển khai (đang là placeholder)
│   ├── docker/
│   ├── k8s/
│   └── terraform/
│
├── src/                         # === SOURCE ROOT ===
│   ├── core/                    # 1. Cấu hình & hằng số xuyên suốt
│   │   ├── config.py            #    ✅ Đọc credentials từ .env
│   │   ├── constants.py         #    ✅ ModelId / Region / message
│   │   ├── prompts.py           #    ✅ Các system-prompt template
│   │   ├── exceptions.py        #    ⛔ Custom exceptions
│   │   └── logger.py            #    ⛔ Logging tập trung
│   │
│   ├── models/                  # 2. Tầng LLM provider (khởi tạo + routing)
│   │   ├── base.py              #    ✅ LLMProvider ABC + dataclass transport
│   │   ├── provider.py          #    ✅ OpenAI / OpenRouter / Bedrock provider
│   │   ├── llm_factory.py       #    ✅ Class LLM (stateless, chọn provider)
│   │   ├── model_router.py      #    ⛔ Định tuyến model
│   │   └── callbacks.py         #    ⛔ Callback LLM
│   │
│   ├── agents/                  # 3. Các agent chuyên biệt
│   │   ├── base_agent.py        #    ✅ Class Agent (stateful + vòng lặp tool)
│   │   ├── orchestrator_agent.py#    ⛔ Agent điều phối
│   │   ├── research_agent.py    #    ⛔ Agent nghiên cứu
│   │   └── tool_executor_agent.py#   ⛔ Agent chuyên chạy tool
│   │
│   ├── orchestration/           # 4. Điều phối nhiều agent
│   │   ├── agent_orchestrator.py#    ⛔ Điều phối luồng agent
│   │   ├── task_planner.py      #    ⛔ Phân rã task
│   │   └── state_manager.py     #    ⛔ Quản lý state qua các bước
│   │
│   ├── tools/                   # 5. Tool cho agent gọi
│   │   ├── base_tool.py         #    ✅ Tool dataclass + decorator @tool
│   │   ├── tool_registry.py     #    ✅ Registry tra tool theo tên
│   │   └── implementations/     #    Mỗi file = SCHEMA + hàm @tool
│   │       ├── chart_tool.py    #      ✅ generate_chart_tool + execute_chart
│   │       ├── web_search_tool.py#     ✅ web_search_tool + execute_web_search
│   │       ├── otp_tool.py      #      ✅ generate_OTP_tool + generate_OTP
│   │       ├── time_tool.py     #      schema get_realtime_tool (hàm ⛔)
│   │       ├── calendar_tool.py #      ⛔ Lịch
│   │       └── email_tool.py    #      ⛔ Email
│   │
│   ├── memory/                  # 6. Bộ nhớ agent
│   │   ├── memory_manager.py    #    ⛔ Quản lý bộ nhớ ngắn/dài hạn
│   │   ├── vector_store.py      #    ⛔ Client vector DB
│   │   └── embeddings.py        #    ⛔ Dịch vụ embeddings
│   │
│   ├── knowledge/               # 7. Tri thức & RAG
│   │   ├── retriever.py         #    ✅ Class RAG (Bedrock Knowledge Base)
│   │   ├── document_loader.py   #    ⛔ Nạp tài liệu
│   │   ├── text_splitter.py     #    ⛔ Chia nhỏ tài liệu
│   │   └── rag_pipeline.py      #    ⛔ Pipeline RAG hoàn chỉnh
│   │
│   ├── api/                     # 8. REST API (FastAPI)
│   │   ├── main.py              #    ✅ FastAPI app (gắn router)
│   │   └── routes/
│   │       ├── chat.py          #    ✅ POST /chat & /chat/stream (test LLM)
│   │       ├── health.py        #    ✅ GET /health
│   │       └── agents.py        #    ⛔ Endpoint agents
│   │
│   └── utils/                   # 9. Tiện ích dùng chung
│       ├── helpers.py           #    ⛔ Hàm helper
│       └── validators.py        #    ⛔ Validate input
│
└── tests/                       # Test (script smoke, chạy trực tiếp)
    ├── test_agents/test_agent.py#    ✅ Test Agent + tool calling
    ├── test_llm.py              #    ✅ Test LLM streaming
    ├── test_rag.py              #    ⛔ (trống)
    ├── test_tools/              #    (chưa có test)
    └── test_api/                #    (chưa có test)
```

---

## Vai trò từng module

### 1. `core/` — Cấu hình & hằng số xuyên suốt
Nơi tập trung mọi thứ "cắt ngang" toàn hệ thống; các layer khác đều import từ đây.
- **`config.py`** ✅ — class `Config` đọc credentials từ `.env` qua `python-dotenv` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ROLE_ARN`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`), phơi ra singleton `config`.
- **`constants.py`** ✅ — `ModelId` (danh mục model Claude / Nemotron / MiMo), `Region`, template `message`; singleton `model` và `region`.
- **`prompts.py`** ✅ — các system-prompt template (chatbot OTP, web search, sinh chart).
- **`exceptions.py`** ⛔ — nơi định nghĩa custom exception.
- **`logger.py`** ⛔ — cấu hình logging tập trung.

### 2. `models/` — Tầng LLM provider
Trừu tượng hóa việc gọi model để phần còn lại của hệ thống không cần biết backend là gì.
- **`base.py`** ✅ — `LLMProvider` (abstract base class với `invoke` / `invoke_stream`) và các dataclass "transport" chuẩn hóa: `Message`, `LLMResponse` (answer + token + tool_calls), `StreamChunk` (delta text hoặc tool-call chunk).
- **`provider.py`** ✅ — ba hiện thực cụ thể:
  - `OpenAIProvider` — API OpenAI chuẩn (`OPENAI_API_KEY`).
  - `OpenRouterProvider` — SDK `openrouter` (`client.chat.send`, dùng `OPENROUTER_API_KEY`).
  - `BedrockProvider` — AWS Bedrock qua `boto3`, tự động assume-role STS nếu có `AWS_ROLE_ARN`.
  - Hai provider họ-OpenAI tự convert schema tool từ format Anthropic (`input_schema`) sang format function của OpenAI.
- **`llm_factory.py`** ✅ — class **`LLM`**: wrapper stateless một-phát-một (không giữ lịch sử), chọn provider dựa trên chuỗi `provider`.
- **`model_router.py`** ⛔ — logic định tuyến chọn model.
- **`callbacks.py`** ⛔ — callback/hook vòng đời LLM.

### 3. `agents/` — Các agent chuyên biệt
- **`base_agent.py`** ✅ — class **`Agent`**: có trạng thái, giữ `chat_history`, đăng ký tool qua `add_tool(schema, func)`, và chạy **vòng lặp tool-calling đa lượt** (gọi model → nếu có tool_call thì thực thi hàm → nối kết quả vào lịch sử → lặp đến khi có câu trả lời thuần văn bản). `_manage_history` cắt bớt lịch sử khi vượt `max_history`.
- **`orchestrator_agent.py`, `research_agent.py`, `tool_executor_agent.py`** ⛔ — các agent chuyên nhiệm, mỗi agent một trách nhiệm.

### 4. `orchestration/` — Điều phối nhiều agent ⛔
Toàn bộ layer còn là stub. Vai trò dự kiến: `agent_orchestrator.py` điều phối luồng chạy giữa nhiều agent, `task_planner.py` phân rã yêu cầu lớn thành task nhỏ, `state_manager.py` giữ trạng thái xuyên suốt các bước.

### 5. `tools/` — Công cụ cho agent gọi
Tool được **tra theo tên** qua registry; khai báo agent chỉ cần ghi tên tool:
```python
agent = Agent(system_prompt=..., provider="openrouter", model_id=...,
              tools=["web_search", "generate_OTP"])
```
- **`base_tool.py`** ✅ — dataclass `Tool` (`name`/`description`/`input_schema`/`func`, property `.schema`, `.run()`) và decorator **`@tool(SCHEMA)`** tự đăng ký tool vào registry.
- **`tool_registry.py`** ✅ — `ToolRegistry` (map `name → Tool`) + singleton `registry`; `discover()` auto-import package implementations để kích hoạt decorator; `get` báo lỗi rõ (liệt kê tool có sẵn), chống trùng tên.
- **`implementations/`** — mỗi file là **một tool self-contained**: một `SCHEMA` dict (format Anthropic) + một hàm `@tool(SCHEMA)` nhận kwargs khớp `input_schema`. `__init__.py` quét động import mọi `*_tool.py` (bỏ qua module lỗi import).
  - `otp_tool.py` ✅ (`generate_OTP`)
  - `web_search_tool.py` ✅ (`web_search`, Tavily — lazy import, cần `TAVILY_API_KEY`)
  - `chart_tool.py` ✅ (`generate_graph_data`)
  - `time_tool.py` — schema `get_time` ✅, hàm ⛔ (chưa hiện thực)
  - `calendar_tool.py` ⛔, `email_tool.py` ⛔
- Phía `Agent`: `tools=[...]` trong constructor hoặc `add_tool(name)` — resolve qua registry, dedupe theo tên, fail-fast nếu tên lạ.

### 6. `memory/` — Bộ nhớ agent ⛔
Stub toàn bộ. Vai trò dự kiến: `memory_manager.py` quản lý bộ nhớ ngắn/dài hạn, `vector_store.py` là client tới vector DB (Qdrant đã có sẵn trong `docker-compose.yml`), `embeddings.py` sinh embedding cho semantic memory.

### 7. `knowledge/` — Tri thức & RAG
- **`retriever.py`** ✅ — class **`RAG`**: truy vấn Amazon Bedrock Knowledge Base, lấy context + nguồn, và tạo presigned URL cho tài liệu S3.
- **`document_loader.py`** ⛔ / **`text_splitter.py`** ⛔ / **`rag_pipeline.py`** ⛔ — nạp tài liệu, chia chunk, và pipeline RAG đầu-cuối (hiện mới có bước retrieve).

### 8. `api/` — REST API (FastAPI)
- **`main.py`** ✅ — khởi tạo FastAPI `app`, gắn router `health` và `chat`. Chạy: `PYTHONPATH=src uvicorn api.main:app --reload` (Swagger UI ở `/docs`).
- **`routes/health.py`** ✅ — `GET /health` → `{"status": "ok"}`.
- **`routes/chat.py`** ✅ — `POST /chat` (trả câu trả lời đầy đủ) và `POST /chat/stream` (stream từng chunk) để test `LLM`; body chọn được `provider` / `model_id` / `system_prompt` / tham số sinh.
- **`routes/agents.py`** ⛔ — endpoint điều khiển agent (chưa làm).

### 9. `utils/` — Tiện ích dùng chung ⛔
`helpers.py` (hàm tái sử dụng) và `validators.py` (validate input) — đều là stub.

---

## Luồng hoạt động

**Gọi model một lần (stateless):**
```
LLM(provider, model_id) → chọn *Provider → provider.invoke()/invoke_stream()
→ trả LLMResponse / stream StreamChunk
```

**Agent có tool (stateful, đa lượt):**
```
Agent.invoke(msg)
  └─ append vào chat_history
     while True:
        provider.invoke(history, tools)
        ├─ có tool_calls? → chạy hàm trong tool_registry → nối kết quả → lặp
        └─ không?         → trả lời cuối, cắt bớt history, return
```

**RAG:**
```
RAG.retrieve_context(query, kbId) → get_contexts() → generate_presigned_urls()
```

### Chọn provider (điểm cần nhớ)
Việc chọn provider là một phép so chuỗi **lặp ở cả `LLM` và `Agent`**:

| `provider` | Class dùng |
|---|---|
| `"openai"` | `OpenAIProvider` |
| `"openrouter"` | `OpenRouterProvider` |
| còn lại (mặc định) | `BedrockProvider` |

Ngoài ra `Agent` còn dùng chuỗi này để chọn **định dạng message tool**: `provider in ("openai", "openrouter")` dùng format kiểu OpenAI (`role: "tool"` + `tool_calls`), còn nhánh Bedrock dùng khối `tool_use` / `tool_result`. ⚠️ Khi thêm provider mới hoặc sửa phần tool, phải cập nhật cả phần chọn provider (2 chỗ) lẫn 4 nhánh format trong `Agent`.

---

## Hạ tầng & phụ trợ

- **`docker-compose.yml`** (root) — dựng hạ tầng dev: **Postgres** (5432), **MinIO** (9000 API / 9001 console), **Qdrant** (6333 HTTP / 6334 gRPC), mỗi service có named volume riêng.
- **`Dockerfile`** (root) — đang trống, chờ định nghĩa image cho app.
- **`infra/{docker,k8s,terraform}/`** — placeholder cho cấu hình triển khai (Docker / Kubernetes / Terraform).
- **`tests/`** — các script smoke chạy trực tiếp (`python tests/...`), không phải pytest; cần `PYTHONPATH=src`.

## Trạng thái triển khai (tóm tắt)

- **Đã chạy được**: luồng lõi inference + tool cho cả 3 provider (`LLM`, `Agent`), và retrieval RAG cơ bản (`RAG`).
- **Chưa triển khai**: 4 layer `orchestration`, `memory`, `api`, `utils`; phần multi-agent; RAG pipeline đầy đủ; registry tool tập trung.
