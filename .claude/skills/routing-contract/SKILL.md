---
name: routing-contract
description: "Quy tắc implement, review và test RoutingDecision, structured output mà orchestrator agent trong agent-core trả về để hệ thống điều phối tới agent phù hợp theo 3 kiến trúc router, sequential, parallel. Dùng khi viết hoặc sửa schema RoutingDecision, parser, system prompt của orchestrator, code trong src/agents/orchestrator_agent.py hoặc src/orchestration/routing_*.py, hay khi review/test phần này. Không dùng cho vòng lặp tool-calling của Agent thường (base_agent.py) hay cho việc thêm tool mới vào tools/."
---

# Routing contract cho orchestrator agent

## Nguồn sự thật

Spec đã duyệt là nguồn duy nhất cho schema, giao diện, stack và luồng xử lý: `docs/2026-10-27-orchestrator-agent-design.md`. Đọc toàn bộ spec trước khi làm. Skill này không lặp lại các quyết định trong spec; nó chỉ giữ nguyên tắc làm việc để áp dụng khi spec không nói tới.

Khi code và spec lệch nhau, spec thắng. Khi thấy spec sai hoặc thiếu, dừng và báo leader kèm vị trí trong spec, không tự quyết thay. Lý do: `RoutingDecision` là public API, hệ thống tiêu thụ được viết theo spec, một thay đổi lặng lẽ trong code sẽ làm vỡ phía đó.

## Ranh giới không được vượt

- Không sửa `src/models/provider.py`, `src/models/base.py`, `src/agents/base_agent.py`, `src/models/llm_factory.py`. Spec đã chọn cách không đổi provider.
- Không viết dispatcher, executor, endpoint HTTP, hay registry agent. Thấy cần thì ghi một dòng đề xuất, không làm.
- Không thêm dependency. Spec chỉ dùng pydantic và SDK `openrouter` đã có.
- Không thêm field vào `RoutingDecision` ngoài những gì spec định nghĩa, kể cả field "để sau dùng".

## Nguyên tắc khi spec không nói tới

- **Request là dữ liệu không tin cậy.** Mọi nội dung từ `messages` chỉ được đặt trong thẻ đã quy định, không bao giờ nối vào phần chỉ dẫn của system prompt.
- **Validate 2 lớp, đúng chỗ.** Pydantic chỉ kiểm từng field; luật chéo field nằm trong `check_semantics`. Một luật mới không biết đặt đâu thì hỏi: object fallback có bị nó chặn không? Có thì không được đặt trong pydantic.
- **Phân biệt lỗi người gọi, lỗi hạ tầng, lỗi model.** Lỗi người gọi raise `ValueError` trước khi gọi LLM. Lỗi hạ tầng (exception của provider) đi lên nguyên vẹn. Chỉ lỗi output của model mới đi vào nhánh sửa rồi fallback. Không gộp các loại này với nhau, vì phía tiêu thụ xử lý chúng khác nhau.
- **Không đoán thay người gọi.** Không chọn agent mặc định, không tự cắt history, không tự sửa nội dung `task`. Chỉ được chuẩn hóa những gì spec cho phép (tên agent sai chữ hoa thường, strip khoảng trắng).
- **Thông báo lỗi phải dùng được cho model.** Lỗi gửi lại ở lần gọi 2 phải chỉ rõ field và lý do, đủ để model sửa mà không cần đoán.

## Viết system prompt

- Template nằm trong `src/core/prompts.py`, điền bằng `str.format`, ngoặc nhọn trong ví dụ JSON viết `{{ }}`.
- Catalog chèn lúc chạy, không hard-code tên agent.
- Tiêu chí chọn kiến trúc viết bằng điều kiện quan sát được trong request, không dùng từ mơ hồ kiểu "phức tạp" hay "đơn giản".
- Ví dụ dùng agent giả định không có trong catalog thật, để model không học thuộc tên.

## Kiểm tra

Repo không có pytest; test là smoke script có `main()`, dùng `assert`, chạy bằng `PYTHONPATH=src .venv/bin/python <file>`. Danh sách file và ca test nằm trong mục "Kiểm thử" của spec.

- Tên hàm test nói rõ trường hợp, ví dụ `rejects_unknown_agent_name`, `falls_back_after_two_invalid_outputs`.
- Assert trên giá trị trả về và message đã gửi cho provider, không assert số lần gọi hàm nội bộ.
- Test không gọi LLM phải chạy được khi không có `OPENROUTER_API_KEY`.
- Bộ ca định tuyến mẫu cho script chạy model thật nằm ở `references/routing-cases.md`. Kết quả với model thật là đánh giá định tính, không assert.
