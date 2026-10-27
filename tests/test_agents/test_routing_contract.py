"""Smoke tests for check_semantics and parse_output. No LLM, no API key needed."""

import json

from orchestration.routing_parser import parse_output
from orchestration.routing_schema import AgentSpec, LLMRoutingOutput, check_semantics

CATALOG = [
    AgentSpec(name="web_researcher", description="Tìm thông tin trên web"),
    AgentSpec(name="data_analyst", description="Phân tích số liệu, vẽ biểu đồ"),
    AgentSpec(name="writer", description="Viết và biên tập văn bản"),
    AgentSpec(name="general_assistant", description="Tổng hợp kết quả từ nhiều nguồn"),
]

ROUTER = {
    "status": "routed",
    "architecture": "router",
    "steps": [{"id": "s1", "agent": "writer", "task": "Viết lại đoạn văn"}],
    "aggregation": None,
    "clarification": None,
    "reasoning": "Một năng lực",
}
SEQUENTIAL = {
    **ROUTER,
    "architecture": "sequential",
    "steps": [
        {"id": "s1", "agent": "web_researcher", "task": "Tìm GDP"},
        {"id": "s2", "agent": "data_analyst", "task": "Vẽ biểu đồ từ dữ liệu bước trước"},
    ],
}
PARALLEL = {
    **ROUTER,
    "architecture": "parallel",
    "steps": [
        {"id": "s1", "agent": "writer", "task": "Tóm tắt bài A"},
        {"id": "s2", "agent": "writer", "task": "Tóm tắt bài B"},
    ],
    "aggregation": {"strategy": "synthesize", "agent": "general_assistant"},
}
CLARIFY = {
    "status": "needs_clarification",
    "architecture": None,
    "steps": [],
    "aggregation": None,
    "clarification": "Bạn muốn làm gì?",
    "reasoning": "Mơ hồ",
}


def semantic_errors(data):
    return check_semantics(LLMRoutingOutput.model_validate(data), CATALOG)[1]


def assert_error(data, fragment):
    errors = semantic_errors(data)
    assert any(fragment in e for e in errors), f"expected {fragment!r} in {errors}"


# check_semantics: valid cases


def test_accepts_valid_router():
    assert semantic_errors(ROUTER) == []


def test_accepts_valid_sequential():
    assert semantic_errors(SEQUENTIAL) == []


def test_accepts_valid_parallel_synthesize():
    assert semantic_errors(PARALLEL) == []


def test_accepts_valid_parallel_concat():
    assert semantic_errors({**PARALLEL, "aggregation": {"strategy": "concat", "agent": None}}) == []


def test_accepts_valid_needs_clarification():
    assert semantic_errors(CLARIFY) == []


def test_canonicalizes_agent_name_case_without_mutating_input():
    data = {
        **PARALLEL,
        "steps": [
            {"id": "s1", "agent": " Writer ", "task": "A"},
            {"id": "s2", "agent": "WEB_RESEARCHER", "task": "B"},
        ],
        "aggregation": {"strategy": "synthesize", "agent": "General_Assistant"},
    }
    original = LLMRoutingOutput.model_validate(data)
    normalized, errors = check_semantics(original, CATALOG)
    assert errors == []
    assert [s.agent for s in normalized.steps] == ["writer", "web_researcher"]
    assert normalized.aggregation.agent == "general_assistant"
    assert original.steps[1].agent == "WEB_RESEARCHER"
    assert original.aggregation.agent == "General_Assistant"


# check_semantics: one violation per rule


def test_rejects_unknown_step_agent():
    assert_error({**ROUTER, "steps": [{"id": "s1", "agent": "admin_tool", "task": "x"}]}, "steps[0].agent")


def test_rejects_unknown_aggregation_agent():
    assert_error({**PARALLEL, "aggregation": {"strategy": "synthesize", "agent": "boss"}}, "aggregation.agent")


def test_rejects_duplicate_step_ids():
    steps = [{"id": "s1", "agent": "writer", "task": "A"}, {"id": "s1", "agent": "writer", "task": "B"}]
    assert_error({**SEQUENTIAL, "steps": steps}, "duplicate step id")


def test_rejects_routed_without_architecture():
    assert_error({**ROUTER, "architecture": None}, "architecture:")


def test_rejects_router_with_two_steps():
    assert_error({**ROUTER, "steps": SEQUENTIAL["steps"]}, "router needs exactly 1 step")


def test_rejects_sequential_with_one_step():
    assert_error({**SEQUENTIAL, "steps": ROUTER["steps"]}, "sequential needs at least 2 steps")


def test_rejects_parallel_with_one_step():
    assert_error({**PARALLEL, "steps": ROUTER["steps"]}, "parallel needs at least 2 steps")


def test_rejects_parallel_without_aggregation():
    assert_error({**PARALLEL, "aggregation": None}, "aggregation: required")


def test_rejects_sequential_with_aggregation():
    assert_error({**SEQUENTIAL, "aggregation": PARALLEL["aggregation"]}, "aggregation: must be null")


def test_rejects_router_with_aggregation():
    assert_error({**ROUTER, "aggregation": PARALLEL["aggregation"]}, "aggregation: must be null")


def test_rejects_routed_with_clarification():
    assert_error({**ROUTER, "clarification": "Hỏi lại"}, "clarification: must be null")


def test_rejects_needs_clarification_without_clarification():
    assert_error({**CLARIFY, "clarification": None}, "clarification: required")


def test_rejects_needs_clarification_with_architecture():
    assert_error({**CLARIFY, "architecture": "router"}, "architecture: must be null")


def test_rejects_needs_clarification_with_aggregation():
    assert_error({**CLARIFY, "aggregation": {"strategy": "concat", "agent": None}}, "aggregation: must be null")


def test_rejects_needs_clarification_with_steps():
    assert_error({**CLARIFY, "steps": ROUTER["steps"]}, "steps: must be empty")


def test_rejects_synthesize_without_agent():
    assert_error({**PARALLEL, "aggregation": {"strategy": "synthesize", "agent": None}}, "required when strategy is synthesize")


def test_rejects_concat_with_agent():
    assert_error({**PARALLEL, "aggregation": {"strategy": "concat", "agent": "writer"}}, "must be null when strategy is concat")


# parse_output


def test_parses_plain_json():
    output, errors = parse_output(json.dumps(ROUTER), CATALOG)
    assert errors == [] and output.steps[0].agent == "writer"


def test_parses_json_in_code_fence():
    output, errors = parse_output(f"```json\n{json.dumps(SEQUENTIAL)}\n```", CATALOG)
    assert errors == [] and output.architecture == "sequential"


def test_parses_json_with_surrounding_text():
    output, errors = parse_output(f"Here is the decision:\n{json.dumps(CLARIFY)}\nHope it helps {{ok}}", CATALOG)
    assert errors == [] and output.status == "needs_clarification"


def test_parse_returns_normalized_agent_names():
    data = {**ROUTER, "steps": [{"id": "s1", "agent": "WRITER", "task": "x"}]}
    output, errors = parse_output(json.dumps(data), CATALOG)
    assert errors == [] and output.steps[0].agent == "writer"


def test_parse_rejects_truncated_json():
    output, errors = parse_output(json.dumps(PARALLEL)[:60], CATALOG)
    assert output is None and len(errors) == 1 and "JSON" in errors[0]


def test_parse_rejects_none():
    output, errors = parse_output(None, CATALOG)
    assert output is None and errors


def test_parse_rejects_empty_string():
    output, errors = parse_output("   ", CATALOG)
    assert output is None and errors


def test_parse_rejects_text_without_json():
    output, errors = parse_output("I think writer should do it.", CATALOG)
    assert output is None and "no JSON object" in errors[0]


def test_parse_rejects_non_object_json():
    output, errors = parse_output("[1, 2]", CATALOG)
    assert output is None and "no JSON object" in errors[0]
    output, errors = parse_output('"writer"', CATALOG)
    assert output is None and "no JSON object" in errors[0]


def test_parse_reports_wrong_field_type_with_path():
    data = {**ROUTER, "steps": [{"id": "s1", "agent": "writer", "task": 5}], "status": "done"}
    output, errors = parse_output(json.dumps(data), CATALOG)
    assert output is None
    assert any(e.startswith("steps.0.task:") for e in errors), errors
    assert any(e.startswith("status:") for e in errors), errors


def test_parse_rejects_empty_required_string():
    data = {**ROUTER, "reasoning": "  "}
    output, errors = parse_output(json.dumps(data), CATALOG)
    assert output is None and any(e.startswith("reasoning:") for e in errors), errors


def test_parse_reports_semantic_errors():
    data = {**ROUTER, "steps": [{"id": "s1", "agent": "admin_tool", "task": "x"}]}
    output, errors = parse_output(json.dumps(data), CATALOG)
    assert output is None and "admin_tool" in errors[0]


def main():
    tests = [obj for name, obj in globals().items() if name.startswith("test_") and callable(obj)]
    for test in tests:
        test()
        print(f"{test.__name__} OK")
    print(f"\nAll {len(tests)} routing contract tests PASSED")


if __name__ == "__main__":
    main()
