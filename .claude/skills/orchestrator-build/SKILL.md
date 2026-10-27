---
name: orchestrator-build
description: "Điều phối đội agent xây dựng orchestrator agent cho agent-core: viết system prompt, implement src/agents/orchestrator_agent.py, review và chạy smoke test. Dùng khi người dùng yêu cầu build, thiết kế, implement, mở rộng orchestrator agent, routing agent, agent điều phối, structured output để chọn agent, hay thêm kiến trúc router/sequential/parallel. Cũng dùng cho yêu cầu tiếp theo: chạy lại, sửa, cập nhật, bổ sung, chỉ làm lại phần prompt/schema/test của orchestrator, dựa trên kết quả trước, cải thiện kết quả. Không dùng cho câu hỏi nhanh về code hiện có hay cho sửa Agent thường trong base_agent.py."
---

# Orchestrator build

Skill này điều phối việc xây orchestrator agent: một agent nhận request và trả `RoutingDecision` (structured output) để hệ thống điều phối tới agent phù hợp. Thiết kế đã duyệt nằm trong `docs/2026-10-27-orchestrator-agent-design.md`; nguyên tắc làm việc nằm trong skill `routing-contract`. Mọi agent trong đội phải load skill đó trước khi làm.

## Chế độ chạy: hỗn hợp

| Bước | Chế độ | Lý do |
| --- | --- | --- |
| 1. Thiết kế hoặc sửa spec (chỉ khi cần) | Subagent | Chỉ cần nhận một bản nháp, rồi người dùng duyệt |
| 2. System prompt | Subagent | Đầu vào cố định (spec đã duyệt), nhận kết quả một lần |
| 3. Implement và review | Persistent agent | Implementer và reviewer phải sửa qua lại nhiều vòng, giữ ngữ cảnh lần review trước |
| 4. Kiểm tra cuối | Agent chính tự làm | Phải tự chạy test và xem output trước khi báo kết quả |

Không dùng Workflow: số bước ít, có điểm dừng chờ người dùng duyệt, và vòng sửa phụ thuộc nội dung review nên không cố định được bằng code.

## Thành phần đội

| Tên gọi | `subagent_type` | Vai trò | Đầu ra |
| --- | --- | --- | --- |
| architect | `Multi-Agent Systems Architect` | Chỉ khi chưa có spec hoặc đổi phạm vi: sửa spec thiết kế | `docs/{YYYY-MM-DD}-orchestrator-agent-design.md` |
| prompt-engineer | `Prompt Engineer` | Viết system prompt và ví dụ cho từng kiến trúc | `_workspace/02_prompt-engineer_system-prompt.md` |
| implementer | `AI Engineer` | Viết code và smoke test theo spec | Code trong `src/`, test trong `tests/test_agents/` |
| reviewer | `Code Reviewer` | Đối chiếu code với spec, chạy smoke test, tìm lỗi | `_workspace/03_reviewer_round{N}.md` |

Model của từng agent ghi trong frontmatter của file agent kèm lý do.

## Quy trình

### Bước 0: Kiểm tra công việc đã có

1. Tìm spec đã duyệt: `docs/*-orchestrator-agent-design.md` mới nhất. Spec hiện tại là `docs/2026-10-27-orchestrator-agent-design.md`. Có spec và yêu cầu nằm trong phạm vi spec thì bỏ qua Bước 1, bắt đầu từ Bước 2. Không có spec, hoặc yêu cầu vượt phạm vi spec (kiến trúc mới, đổi schema, đổi stack), thì chạy Bước 1.
2. Không có `_workspace/` thì chạy từ bước xác định ở mục 1.
3. Có `_workspace/` và người dùng chỉ muốn sửa một phần (ví dụ "sửa lại prompt", "thêm test"), chạy lại đúng bước đó, đưa đường dẫn file cũ vào prompt của agent để nó đọc và chỉ sửa phần liên quan.
4. Có `_workspace/` và đầu vào mới (ví dụ spec vừa đổi), đổi tên thư mục cũ thành `_workspace_{YYYYMMDD-HHMM}/` rồi chạy từ bước xác định ở mục 1.
5. Nếu code orchestrator đã tồn tại trong `src/`, đọc nó trước; implementer chỉ sửa phần lệch với spec.

### Bước 1: Thiết kế hoặc sửa spec (chỉ khi cần)

**Chế độ:** subagent.

Chỉ chạy khi Bước 0 xác định chưa có spec hoặc yêu cầu vượt phạm vi spec. Gọi `Agent(subagent_type: "Multi-Agent Systems Architect")`, không đặt `name`. Prompt gồm: yêu cầu của người dùng, đường dẫn spec hiện có (nếu có), yêu cầu load skill `routing-contract`, đọc `src/models/base.py`, `src/models/provider.py`, `src/core/config.py`. Architect ghi bản nháp vào `_workspace/01_architect_spec-draft.md`, không sửa thẳng file trong `docs/`.

Bản nháp phải có đủ các mục như spec hiện tại: phạm vi, stack, giao diện, đầu vào, đầu ra, thành phần, luồng xử lý, parse và validate, system prompt, bảng lỗi, kiểm thử, rủi ro. Phần thay đổi so với spec cũ phải được liệt kê riêng ở đầu.

**Điểm dừng:** tóm tắt cho người dùng các thay đổi schema và public API, chờ duyệt. Được duyệt thì agent chính ghi bản nháp thành `docs/{YYYY-MM-DD}-orchestrator-agent-design.md` và cập nhật đường dẫn spec ở Bước 0. Không sang Bước 2 khi chưa được duyệt, vì `RoutingDecision` là public API.

### Bước 2: System prompt

**Chế độ:** subagent.

Gọi `Agent(subagent_type: "Prompt Engineer")` với: đường dẫn spec, yêu cầu load skill `routing-contract`, đọc mục "System prompt" của spec, đọc `src/core/prompts.py` để theo đúng kiểu template đang có, đọc `.claude/skills/routing-contract/references/routing-cases.md` để kiểm tiêu chí chọn kiến trúc trên các ca mẫu. Ghi kết quả vào `_workspace/02_prompt-engineer_system-prompt.md`: template sẵn sàng đưa vào `core/prompts.py` (ngoặc nhọn đã viết `{{ }}`), các placeholder và cách điền lúc chạy.

### Bước 3: Implement và review

**Chế độ:** persistent agent.

1. Khởi động trong cùng một message:
   - `Agent(name: "implementer", subagent_type: "AI Engineer")`: prompt gồm đường dẫn spec và `_workspace/02_prompt-engineer_system-prompt.md`, yêu cầu load skill `routing-contract` và `coding-style`, đọc `CLAUDE.md`, chỉ tạo hoặc sửa các file trong mục "Thành phần" và "Kiểm thử" của spec, báo lại danh sách file đã sửa và output test.
   - `Agent(name: "reviewer", subagent_type: "Code Reviewer")`: prompt gồm đường dẫn spec, yêu cầu load skill `routing-contract`, chờ leader báo implementer xong rồi mới review. Không sửa code; chỉ ghi phát hiện vào `_workspace/03_reviewer_round{N}.md`.
2. Khi implementer báo xong, gửi `SendMessage({to: "reviewer"})` kèm danh sách file đã đổi. Reviewer phải: chạy toàn bộ smoke test không cần LLM và dán output, đối chiếu từng dòng của mục "Parse và validate" và "Bảng lỗi" trong spec với code, kiểm ranh giới trong skill `routing-contract`, xếp phát hiện theo mức độ (chặn / nên sửa / gợi ý).
3. Nếu có phát hiện mức "chặn" hoặc "nên sửa", chuyển file review cho implementer qua `SendMessage({to: "implementer"})`. Implementer sửa và báo lại; lặp lại bước 2.
4. Tối đa 3 vòng review. Hết 3 vòng mà vẫn còn mức "chặn" thì dừng, báo người dùng phần còn tồn đọng, không tự quyết thay.
5. Khi reviewer không còn mức "chặn", báo cả hai agent rằng kết quả đã đóng băng: từ đây không sửa file nữa.

Quy tắc liên lạc: leader chuyển tin giữa implementer và reviewer; hai agent không tự gửi tin cho nhau, để leader luôn biết code đang ở phiên bản nào. Mỗi agent báo danh sách tool thực sự dùng được trong lần báo đầu tiên.

### Bước 4: Kiểm tra cuối

Agent chính tự chạy, không tin vào báo cáo của agent:

```bash
PYTHONPATH=src .venv/bin/python tests/test_agents/test_routing_contract.py
PYTHONPATH=src .venv/bin/python tests/test_agents/test_orchestrator_agent.py
PYTHONPATH=src .venv/bin/python tests/test_tools/test_registry.py
```

Test cuối là để chắc thay đổi không làm hỏng tool registry. Nếu có `OPENROUTER_API_KEY`, chạy thêm `PYTHONPATH=src .venv/bin/python tests/test_agents/eval_routing_live.py` và đưa người dùng bảng kết quả so với kết quả mong đợi trong `routing-cases.md`; ca lệch là thông tin để sửa prompt, không phải lỗi test. Không có key thì ghi rõ đã bỏ qua. Báo người dùng: file đã đổi, output test (cả lỗi nếu có), phát hiện "nên sửa"/"gợi ý" còn lại, và mọi thay đổi public API. Không commit.

## Xử lý lỗi

| Tình huống | Cách xử lý |
| --- | --- |
| Một subagent lỗi hoặc trả kết quả rỗng | Thử lại 1 lần với cùng prompt. Lỗi lần nữa thì báo người dùng, không tự viết thay phần thiết kế |
| Persistent agent không phản hồi | Hỏi trạng thái bằng `SendMessage`. Vẫn không được thì khởi động cùng loại với tên mới (ví dụ `implementer-2`), đưa đường dẫn spec, file review gần nhất và danh sách file đã sửa |
| Hết quota, hết hạn xác thực, bị từ chối quyền | Không thử lại. Mở file trong `_workspace/` và `git diff` để xem thực tế làm tới đâu, ghi phần còn thiếu vào `_workspace/99_leader_blocked.md`, báo người dùng |
| Thiếu `OPENROUTER_API_KEY` khi chạy `eval_routing_live.py` | Ghi rõ ca đó bị bỏ qua và vì sao. Không tính là đạt |
| Implementer muốn sửa file ngoài danh sách trong mục "Thành phần" của spec | Dừng, hỏi người dùng. Đặc biệt với `models/provider.py`, `models/base.py`, `agents/base_agent.py` |
| Reviewer và implementer bất đồng về một luật | Giữ cả hai ý kiến trong file review, đưa người dùng quyết |

Khi agent chính lấp chỗ trống cho agent bị dừng, chỉ ghi những gì tự kiểm được (file nào đã đổi, test nào chạy ra gì). Không đoán thay lý do hay phán đoán của agent.

## Kịch bản kiểm thử

### Luồng bình thường

1. Người dùng: "build orchestrator agent cho 3 kiến trúc router, sequential, parallel".
2. Bước 0 thấy spec đã duyệt và không có `_workspace/`, nên bỏ qua Bước 1.
3. Bước 2 prompt-engineer ghi `02_prompt-engineer_system-prompt.md`.
4. Bước 3 implementer viết code và test; reviewer vòng 1 tìm 2 lỗi "nên sửa"; implementer sửa; vòng 2 không còn lỗi chặn.
5. Bước 4 agent chính chạy 3 smoke script, tất cả pass, báo người dùng.

### Luồng lỗi

1. Ở Bước 3, reviewer vòng 3 vẫn báo "chặn": validator chấp nhận `sequential` có step trỏ tới step đứng sau.
2. Leader dừng vòng lặp, báo người dùng lỗi tồn đọng kèm file `_workspace/03_reviewer_round3.md`.
3. Người dùng chọn tự sửa hoặc chạy lại riêng Bước 3; khi chạy lại, Bước 0 chọn nhánh "chỉ sửa một phần".

### Luồng chạy lại một phần

1. Người dùng: "sửa lại prompt của orchestrator, model hay chọn parallel khi đáng lẽ là sequential".
2. Bước 0 thấy `_workspace/` nên chỉ chạy Bước 2 với file prompt cũ và góp ý, rồi Bước 3 chỉ để implementer cập nhật `core/prompts.py` và reviewer kiểm lại.
