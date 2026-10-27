# Thiết kế orchestrator agent

Ngày: 2026-10-27. Trạng thái: chờ duyệt.

## Mục tiêu

Orchestrator agent nhận hội thoại của người dùng cùng danh sách agent đang có, và trả về một `RoutingDecision` có cấu trúc. Hệ thống bên ngoài đọc `RoutingDecision` để điều phối request tới agent phù hợp theo một trong 3 kiến trúc: `router`, `sequential`, `parallel`. Orchestrator chỉ ra quyết định, không tự chạy agent nào.

## Phạm vi

Trong phạm vi:

- Python class `OrchestratorAgent` với một method `route(messages, catalog)`.
- Schema đầu vào, đầu ra, validate, sửa lỗi 1 lần, fallback.
- System prompt của orchestrator.
- Smoke test không cần LLM, và một script thử với model thật.

Ngoài phạm vi:

- Dispatcher hay executor chạy các agent theo `RoutingDecision`.
- Endpoint HTTP. `src/api/routes/agents.py` vẫn là stub.
- Kiến trúc hierarchical (DAG, sub-plan lồng nhau).
- Registry agent trong code hay file cấu hình. Catalog do người gọi truyền vào mỗi lần.
- Thay đổi `LLMProvider` hay các provider trong `src/models/provider.py`.
- Bedrock (boto3) và OpenAI provider. Orchestrator chỉ chạy trên OpenRouter.

## Stack

- LLM: OpenRouter qua `OpenRouterProvider` có sẵn (`src/models/provider.py:132`), dùng SDK `openrouter` (đã có trong `requirements.txt`).
- Xác thực: `OPENROUTER_API_KEY` trong `.env`, đọc qua `config.OPENROUTER_API_KEY` (`src/core/config.py:14`). Không cần AWS credential hay STS.
- `model_id` theo định dạng `<nhà cung cấp>/<model>` của OpenRouter, nên cùng một code thử được nhiều model bằng cách đổi chuỗi này.
- Validate: pydantic (đã có trong `requirements.txt`). Không thêm dependency.

## Giao diện

```python
from agents.orchestrator_agent import OrchestratorAgent
from orchestration.routing_schema import AgentSpec

orchestrator = OrchestratorAgent(model_id="<nhà cung cấp>/<model>", inference_config={"max_tokens": 1024, "temperature": 0})
decision = orchestrator.route(
    messages=[
        {"role": "user", "content": "Tìm GDP Việt Nam 5 năm gần nhất"},
        {"role": "assistant", "content": "...kết quả..."},
        {"role": "user", "content": "Giờ vẽ biểu đồ cho nó"},
    ],
    catalog=[
        AgentSpec(name="web_researcher", description="Tìm thông tin trên web"),
        AgentSpec(name="data_analyst", description="Phân tích số liệu, vẽ biểu đồ"),
    ],
)
```

Chữ ký: `OrchestratorAgent(model_id: str, inference_config: dict, llm: LLMProvider | None = None)`.

- `llm=None` (mặc định): tự tạo `OpenRouterProvider(model_id, inference_config)`. Nếu `config.OPENROUTER_API_KEY` rỗng thì raise `ValueError` ngay lúc khởi tạo, để lỗi thiếu key lộ ra sớm thay vì thành lỗi xác thực ở lần gọi đầu tiên.
- `llm` truyền vào: dùng provider đó, bỏ qua kiểm tra key. Tham số này chỉ để test truyền `FakeProvider`; không có nhánh chọn provider theo chuỗi, nên không thêm bản sao thứ ba của đoạn rẽ nhánh đang lặp ở `LLM` và `Agent`.

Không dùng lại class `LLM` (`src/models/llm_factory.py`) vì nó chốt system prompt lúc khởi tạo và chỉ nhận 1 message, còn orchestrator cần chèn catalog vào prompt mỗi lần gọi.

`OrchestratorAgent` không giữ state giữa các lần gọi. Cùng `messages` và `catalog` thì đầu vào gửi LLM giống hệt nhau.

## Đầu vào

### messages

List message dạng `{role, content}`, cùng format với `Agent.chat_history`, nên người gọi truyền thẳng history đang có vào được.

- Message cuối là request cần định tuyến, phải có `role: "user"` và có text. Các message trước là history, chỉ để hiểu ngữ cảnh; orchestrator không định tuyến lại yêu cầu cũ.
- Người gọi chịu trách nhiệm giữ history đủ ngắn. Orchestrator không tự cắt.

Chuẩn hóa trước khi gửi LLM. Message cuối được lấy từ list gốc trước khi lọc: nó phải có `role: "user"` và còn text sau khi lấy text theo các luật dưới, nếu không thì raise `ValueError`. Luật lọc theo role và bỏ message rỗng chỉ áp dụng cho history, để một message `user` cũ không bao giờ bị đẩy lên thành request.

- History chỉ giữ message có `role` là `user` hoặc `assistant`. Message `role: "tool"` bị bỏ.
- `content` là string: giữ nguyên.
- `content` là list block: lấy `text` của các block `type: "text"`, nối bằng xuống dòng. Block loại khác (ảnh, tool) bị bỏ.
- `content` là `None` hoặc kiểu khác (ví dụ message assistant chỉ có `tool_calls` mà `Agent` lưu ở nhánh OpenAI, `src/agents/base_agent.py:89`): tính là không có text.
- Text được strip. Message history không còn text sau khi chuẩn hóa thì bị bỏ.

Lý do bỏ phần tool: output của tool dài và không giúp chọn agent.

### catalog

List `AgentSpec(name: str, description: str)`. Cả hai field được strip và không được rỗng. Tên phải duy nhất không phân biệt hoa thường, vì tên agent trong output được so khớp không phân biệt hoa thường. `description` quyết định gần như toàn bộ chất lượng định tuyến; người gọi nên viết nó theo dạng "khi nào nên chọn agent này".

### Lỗi đầu vào

Các trường hợp sau raise `ValueError` ngay, không gọi LLM, vì đó là lỗi của người gọi chứ không phải quyết định điều phối:

- `catalog` rỗng, có tên rỗng, mô tả rỗng, hoặc tên trùng.
- `messages` rỗng.
- Message cuối không có `role: "user"`, hoặc không còn text sau khi chuẩn hóa (ví dụ content là `None` hoặc chỉ có block ảnh).

## Đầu ra

### RoutingDecision

| Field | Kiểu | Quy tắc |
| --- | --- | --- |
| `status` | `"routed"` / `"needs_clarification"` / `"fallback"` | Luôn có |
| `architecture` | `"router"` / `"sequential"` / `"parallel"` hoặc `None` | Có khi `routed`, `None` khi khác |
| `steps` | `list[RoutingStep]` | `routed`: theo luật kiến trúc bên dưới. Trạng thái khác: rỗng |
| `aggregation` | `Aggregation` hoặc `None` | Có khi `parallel`, `None` khi khác |
| `clarification` | `str` hoặc `None` | Có và không rỗng khi `needs_clarification`, `None` khi khác |
| `reasoning` | `str` | Lý do ngắn cho log và debug. Rỗng khi `fallback` |
| `meta` | `RoutingMeta` | Luôn có, do code điền |

### RoutingStep

| Field | Kiểu | Quy tắc |
| --- | --- | --- |
| `id` | `str` | Không rỗng, duy nhất trong decision. Quy ước `s1`, `s2`... |
| `agent` | `str` | Có trong catalog. Trong `RoutingDecision` luôn là tên đúng như trong catalog |
| `task` | `str` | Không rỗng. Chỉ dẫn viết riêng cho agent đó, cùng ngôn ngữ với request |

### Aggregation

| Field | Kiểu | Quy tắc |
| --- | --- | --- |
| `strategy` | `"concat"` / `"synthesize"` | `concat`: nối kết quả theo thứ tự step. `synthesize`: đưa mọi kết quả cho một agent tổng hợp |
| `agent` | `str` hoặc `None` | Bắt buộc và có trong catalog khi `synthesize`, `None` khi `concat` |

### RoutingMeta

| Field | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `model_id` | `str` | Lấy từ `llm.model_id` |
| `attempts` | `int` | 1 hoặc 2: số lần gọi LLM |
| `input_tokens` | `int` | Cộng dồn qua các lần gọi |
| `output_tokens` | `int` | Cộng dồn qua các lần gọi |
| `error` | `str` hoặc `None` | Lỗi của lần cuối khi `fallback`, `None` khi khác |

Tài liệu này là nguồn duy nhất cho schema. Schema baseline cũ trong harness (có `fallback: bool`, `input_from`) đã bị bỏ.

### Schema LLM sinh ra

LLM không sinh `RoutingDecision` mà sinh `LLMRoutingOutput`: cùng các field trừ `meta`, và `status` chỉ nhận `"routed"` hoặc `"needs_clarification"`. Tách 2 schema để model không bịa ra token, số lần gọi hay trạng thái fallback. Code chuyển `LLMRoutingOutput` hợp lệ thành `RoutingDecision` và điền `meta`.

Không có field `confidence` dạng số: điểm model tự chấm không hiệu chỉnh được, phía tiêu thụ sẽ tin con số đó như thật. Khi không chắc, model dùng `needs_clarification`.

### Luật theo kiến trúc

| Kiến trúc | Số step | `aggregation` | Hệ thống tiêu thụ chạy như sau |
| --- | --- | --- | --- |
| `router` | đúng 1 | `None` | Gọi agent với `task` |
| `sequential` | từ 2 | `None` | Chạy theo thứ tự trong list. Step sau nhận `task` của nó và output của step ngay trước |
| `parallel` | từ 2 | bắt buộc | Chạy mọi step độc lập, rồi gộp theo `aggregation` |

Một agent được xuất hiện ở nhiều step (ví dụ `parallel` tóm tắt 3 bài báo bằng cùng agent `writer`).

`needs_clarification`: hệ thống hỏi lại người dùng bằng `clarification`. Dùng khi request mơ hồ hoặc không agent nào phù hợp.

`fallback`: orchestrator không ra được quyết định hợp lệ sau 2 lần gọi, lý do ở `meta.error`. Hệ thống tự xử lý theo mặc định của nó; orchestrator không chọn agent mặc định vì catalog là của người gọi.

### Ví dụ

```json
{
  "status": "routed",
  "architecture": "parallel",
  "steps": [
    {"id": "s1", "agent": "web_researcher", "task": "Tìm giá vé máy bay Hà Nội - Sài Gòn tuần sau"},
    {"id": "s2", "agent": "calendar_assistant", "task": "Liệt kê các ngày trống tuần sau"}
  ],
  "aggregation": {"strategy": "synthesize", "agent": "general_assistant"},
  "clarification": null,
  "reasoning": "Hai phần độc lập về dữ liệu, cần gộp lại để đề xuất ngày bay",
  "meta": {"model_id": "...", "attempts": 1, "input_tokens": 812, "output_tokens": 164, "error": null}
}
```

```json
{
  "status": "needs_clarification",
  "architecture": null,
  "steps": [],
  "aggregation": null,
  "clarification": "Bạn muốn tôi làm gì với tài liệu này: tóm tắt, dịch hay phân tích số liệu?",
  "reasoning": "Request không nói rõ việc cần làm",
  "meta": {"model_id": "...", "attempts": 1, "input_tokens": 640, "output_tokens": 70, "error": null}
}
```

## Thành phần

| File | Trách nhiệm | Phụ thuộc |
| --- | --- | --- |
| `src/orchestration/routing_schema.py` | Model pydantic `AgentSpec`, `RoutingStep`, `Aggregation`, `LLMRoutingOutput`, `RoutingMeta`, `RoutingDecision`; hàm `check_semantics(output, catalog) -> tuple[LLMRoutingOutput, list[str]]` trả về bản sao đã chuẩn hóa tên agent (không sửa input) cùng danh sách lỗi logic | pydantic |
| `src/orchestration/routing_parser.py` | `parse_output(text, catalog) -> tuple[LLMRoutingOutput \| None, list[str]]`: thành công thì `(output, [])`, lỗi thì `(None, errors)` | `routing_schema` |
| `src/core/prompts.py` | Thêm template `orchestrator_prompt` | không |
| `src/agents/orchestrator_agent.py` | `OrchestratorAgent`: kiểm tra đầu vào, chuẩn hóa messages, dựng prompt, gọi LLM, sửa 1 lần, fallback, điền `meta` | 3 file trên, `models.base.LLMProvider` |

Các stub `orchestration/agent_orchestrator.py`, `task_planner.py`, `state_manager.py` không bị đụng tới.

## Luồng xử lý của route()

1. Kiểm tra `catalog`.
2. Chuẩn hóa `messages`, tách thành history (mọi message trừ message cuối) và request (message cuối), rồi kiểm tra `messages` theo mục "Lỗi đầu vào". Mọi `ValueError` xảy ra trước lần gọi LLM đầu tiên.
3. Dựng system prompt từ `orchestrator_prompt`, chèn catalog dạng `- name: description` và JSON schema sinh từ `LLMRoutingOutput.model_json_schema()`.
4. Dựng một message user duy nhất:

   ```text
   <conversation>
   user: ...
   assistant: ...
   </conversation>
   <request>
   ...
   </request>
   ```

   Bỏ thẻ `<conversation>` khi không có history. Không gửi history thành nhiều message thật vì: model có xu hướng trả lời tiếp hội thoại thay vì định tuyến; history sau khi lọc tool có thể có 2 message user liền nhau, cách gói này tránh phụ thuộc vào việc model trên OpenRouter xử lý chuỗi đó ra sao; đặt trong thẻ thì nội dung người dùng được xử lý như dữ liệu.
5. Lần gọi 1: `llm.invoke([user_payload], system_prompt)`.
6. `parse_output(response.answer, catalog)`.
7. Nếu có lỗi, lần gọi 2 với `[user_payload, {"role": "assistant", "content": <text lần 1>}, {"role": "user", "content": <thông báo lỗi>}]`. Thông báo lỗi liệt kê mỗi lỗi một dòng và yêu cầu chỉ trả lại JSON đúng schema. Nếu text lần 1 rỗng hoặc `None`, nội dung assistant là chuỗi `"(empty)"` để message không rỗng.
8. Lần 2 vẫn lỗi: trả `RoutingDecision(status="fallback", architecture=None, steps=[], aggregation=None, clarification=None, reasoning="")` với `meta.error` là các lỗi của lần 2 nối bằng `"; "`.
9. Thành công: chuyển thành `RoutingDecision`, điền `meta`.

Exception từ `llm.invoke` (mạng, quota, xác thực) không bị bắt và đi lên người gọi, vì đó là sự cố hạ tầng chứ không phải quyết định điều phối. Exception ở lần gọi 2 cũng vậy, kể cả khi lần 1 đã tốn token.

## Parse và validate

Phân chia luật giữa pydantic và code:

- Pydantic chỉ giữ ràng buộc trên từng field: kiểu, enum, string không rỗng (`id`, `task`, `agent`, `reasoning` của `LLMRoutingOutput`). Các ràng buộc này nằm trong `model_json_schema()` nên model thấy được qua prompt.
- Mọi luật liên quan nhiều field nằm trong `check_semantics`, không đặt trong `model_validator`. Lý do: `RoutingDecision` fallback có `steps` rỗng và `architecture=None`, một validator chéo field sẽ chặn chính object đó.
- `RoutingDecision` và `RoutingMeta` không có validator chéo field; chúng chỉ do code tạo ra. `RoutingDecision` khai báo field riêng, không kế thừa `LLMRoutingOutput`, vì nó cần `status` 3 giá trị và `reasoning` được rỗng.
- Với field kiểu `str | None` (`Aggregation.agent`, `clarification`), ràng buộc không rỗng chỉ áp dụng khi giá trị khác `None`.

`parse_output` chạy 3 lớp, dừng ở lớp đầu tiên có lỗi:

1. **Tách JSON.** `answer` là `None` hoặc rỗng thì lỗi. Tìm ký tự `{` đầu tiên và dùng `json.JSONDecoder().raw_decode` từ vị trí đó; cách này bỏ qua được code fence và text thừa trước/sau mà không cần regex. Không có `{` hoặc decode lỗi (kể cả JSON bị cắt do hết `max_tokens`) thì lỗi. Giá trị decode được không phải object thì lỗi.
2. **Định dạng.** `LLMRoutingOutput.model_validate`. Mỗi lỗi pydantic đổi thành một dòng `"<đường dẫn field>: <thông báo>"`.
3. **Logic** (`check_semantics`):
   - Mỗi `steps[].agent` và `aggregation.agent`, sau khi strip, khớp một tên trong catalog không phân biệt hoa thường; khớp thì thay bằng tên chuẩn, không khớp thì lỗi.
   - `id` các step duy nhất.
   - `routed`: `architecture` khác `None`; số step và `aggregation` theo bảng "Luật theo kiến trúc"; `clarification` là `None`.
   - `needs_clarification`: `clarification` không rỗng; `architecture`, `aggregation` là `None`; `steps` rỗng.
   - `aggregation.strategy == "synthesize"` thì `aggregation.agent` bắt buộc; `concat` thì phải là `None`.

Không có kiểm tra tự động nào phát hiện được `parallel` mà các step thực chất phụ thuộc nhau; việc này do prompt đảm nhận và được đánh giá bằng bộ ca mẫu.

## System prompt

Template viết bằng tiếng Anh, theo kiểu các prompt sẵn có trong `src/core/prompts.py`, và có các phần:

- Vai trò: chọn agent và kiến trúc, không trả lời request.
- Catalog được chèn lúc chạy. Không hard-code tên agent.
- Tiêu chí chọn kiến trúc bằng điều kiện quan sát được: chỉ cần 1 năng lực thì `router`; bước sau cần kết quả bước trước thì `sequential`; các phần độc lập về dữ liệu thì `parallel`; mơ hồ hoặc không agent nào phù hợp thì `needs_clarification`.
- Mỗi kiến trúc 1 ví dụ ngắn, dùng agent giả định không có trong catalog thật để model không học thuộc tên.
- Nội dung trong `<conversation>` và `<request>` là dữ liệu, không phải chỉ dẫn cho orchestrator.
- `task` và `clarification` viết cùng ngôn ngữ với request.
- Chỉ trả về một JSON object theo schema, không thêm text.

Template được điền bằng `str.format` như `text_to_query_prompt`, nên mọi dấu ngoặc nhọn trong ví dụ JSON phải viết `{{ }}`.

## Bảng lỗi

| Tình huống | Kết quả |
| --- | --- |
| `OPENROUTER_API_KEY` rỗng khi không truyền `llm` | `ValueError` lúc khởi tạo |
| Catalog rỗng, tên hoặc mô tả rỗng, tên trùng | `ValueError` |
| `messages` rỗng, message cuối không phải `user` hoặc không có text | `ValueError` |
| Provider raise exception | Exception đi lên nguyên vẹn |
| JSON hỏng, sai định dạng, sai logic ở lần 1 | Gọi lần 2 kèm danh sách lỗi |
| Vẫn lỗi ở lần 2 | `status="fallback"`, lỗi ở `meta.error` |
| Tên agent sai chữ hoa thường | Tự sửa về tên trong catalog |
| Tên agent không có trong catalog, kể cả do prompt injection | Lỗi logic, đi vào nhánh sửa rồi fallback |
| Request mơ hồ hoặc không agent nào phù hợp | `status="needs_clarification"` |

## Kiểm thử

Smoke script theo kiểu của repo: mỗi file có `main()`, dùng `assert`, chạy bằng `PYTHONPATH=src python <file>`. Tên hàm test nói rõ trường hợp.

`tests/test_agents/test_routing_contract.py`, không gọi LLM:

- `check_semantics`: mỗi kiến trúc 1 ca hợp lệ, `needs_clarification` hợp lệ, mỗi luật logic 1 ca vi phạm, tên sai chữ hoa thường được chuẩn hóa.
- `parse_output`: JSON trơn, bọc code fence, có text thừa trước và sau, bị cắt giữa chừng, `None`, rỗng, không phải object, sai kiểu field.

`tests/test_agents/test_orchestrator_agent.py`, dùng `FakeProvider` (subclass `LLMProvider` trả lần lượt các text định sẵn, ghi lại các message đã nhận; phải implement cả `invoke_stream` vì đó là abstract method, chỉ cần raise `NotImplementedError`):

- Khởi tạo không truyền `llm` khi `config.OPENROUTER_API_KEY` rỗng: raise `ValueError`.
- Chuẩn hóa messages: bỏ `tool`, lấy text từ content dạng list, `content=None` bị bỏ khỏi history, bỏ message history rỗng.
- Các ca `ValueError` của đầu vào, và provider không được gọi trong các ca đó.
- Lần 1 hợp lệ: `attempts == 1`, token đúng.
- Lần 1 hỏng, lần 2 hợp lệ: `attempts == 2`, token cộng dồn, message thứ 3 gửi cho provider chứa lỗi của lần 1.
- Hai lần đều hỏng: `status == "fallback"`, `meta.error` không rỗng, `steps` rỗng.
- Provider raise: exception đi lên.
- History được gói trong `<conversation>`, request trong `<request>`, và chỉ có 1 message được gửi ở lần gọi 1.

`tests/test_agents/eval_routing_live.py`: chạy các ca định tuyến mẫu (kể cả ca có history) trong `.claude/skills/routing-contract/references/routing-cases.md` với model thật, in kết quả để đánh giá bằng mắt, không assert vì LLM không tất định. Thiếu `OPENROUTER_API_KEY` thì in thông báo bỏ qua và thoát.

## Rủi ro đã biết

- `OpenRouterProvider.invoke` đọc `response.usage.prompt_tokens` (`src/models/provider.py:205`) mà không kiểm tra `usage` có tồn tại. Chưa kiểm tra SDK `openrouter` có lúc nào trả `usage=None` hay không (unverified); nếu có, lần gọi đó raise `AttributeError` và exception đi lên người gọi theo đúng luật "lỗi provider không bắt". Thiết kế này không sửa provider.
- Mỗi request đi qua OpenRouter nên phụ thuộc vào tính sẵn sàng và giới hạn tốc độ của OpenRouter cùng model upstream được chọn.
- Mỗi request tốn 1 lượt gọi LLM, 2 lượt khi output lần đầu hỏng. Catalog lớn làm system prompt dài ra tuyến tính theo số agent.
