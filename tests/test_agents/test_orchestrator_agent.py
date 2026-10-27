"""Smoke tests for OrchestratorAgent with a FakeProvider. No LLM, no API key needed."""

import json

from agents.orchestrator_agent import OrchestratorAgent
from core.config import config
from models.base import LLMProvider, LLMResponse
from orchestration.routing_parser import parse_output
from orchestration.routing_schema import AgentSpec

CATALOG = [
    AgentSpec(name="web_researcher", description="Tìm thông tin trên web"),
    AgentSpec(name="data_analyst", description="Phân tích số liệu, vẽ biểu đồ"),
]
VALID = json.dumps(
    {
        "status": "routed",
        "architecture": "router",
        "steps": [{"id": "s1", "agent": "Data_Analyst", "task": "Vẽ biểu đồ GDP"}],
        "aggregation": None,
        "clarification": None,
        "reasoning": "Một năng lực",
    }
)
REQUEST = [{"role": "user", "content": "Vẽ biểu đồ GDP"}]
# Valid format, two logic errors: unknown agent and clarification on a routed decision
TWO_ERRORS = json.dumps(
    {
        **json.loads(VALID),
        "steps": [{"id": "s1", "agent": "admin_tool", "task": "x"}],
        "clarification": "Hỏi lại?",
    }
)


# Returns scripted answers in order and records every call it receives
class FakeProvider(LLMProvider):
    def __init__(self, answers):
        super().__init__("fake/model", {})
        self.answers = list(answers)
        self.calls = []

    def invoke(self, messages, system_prompt, tools=None):
        self.calls.append({"messages": messages, "system_prompt": system_prompt})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return LLMResponse(answer=answer, input_tokens=100, output_tokens=20)

    def invoke_stream(self, messages, system_prompt, tools=None):
        raise NotImplementedError


def make(answers):
    llm = FakeProvider(answers)
    return OrchestratorAgent(model_id="fake/model", inference_config={}, llm=llm), llm


def expect_value_error(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_init_without_llm_raises_when_api_key_missing():
    saved = config.OPENROUTER_API_KEY
    config.OPENROUTER_API_KEY = ""
    try:
        expect_value_error(lambda: OrchestratorAgent(model_id="x/y", inference_config={}))
    finally:
        config.OPENROUTER_API_KEY = saved


def test_normalizes_history_and_wraps_it_in_tags():
    orchestrator, llm = make([VALID])
    messages = [
        {"role": "user", "content": "  Tìm GDP Việt Nam  "},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "t1"}]},
        {"role": "tool", "tool_call_id": "t1", "content": "RAW TOOL OUTPUT"},
        {"role": "assistant", "content": [{"type": "text", "text": "Bảng GDP"}, {"type": "image", "source": {}}, {"type": "text", "text": "2020-2024"}]},
        {"role": "user", "content": "   "},
        {"role": "user", "content": [{"type": "tool_result", "content": "x"}]},
        {"role": "user", "content": "Giờ vẽ biểu đồ cho nó"},
    ]
    orchestrator.route(messages, CATALOG)

    sent = llm.calls[0]["messages"]
    assert len(sent) == 1 and sent[0]["role"] == "user"
    assert sent[0]["content"] == (
        "<conversation>\n"
        "user: Tìm GDP Việt Nam\n"
        "assistant: Bảng GDP\n2020-2024\n"
        "</conversation>\n"
        "<request>\nGiờ vẽ biểu đồ cho nó\n</request>"
    ), sent[0]["content"]


def test_omits_conversation_tag_without_history():
    orchestrator, llm = make([VALID])
    orchestrator.route(REQUEST, CATALOG)
    assert llm.calls[0]["messages"] == [{"role": "user", "content": "<request>\nVẽ biểu đồ GDP\n</request>"}]


def test_system_prompt_contains_catalog_and_schema():
    orchestrator, llm = make([VALID])
    orchestrator.route(REQUEST, CATALOG)
    system_prompt = llm.calls[0]["system_prompt"]
    assert "- web_researcher: Tìm thông tin trên web" in system_prompt
    assert "- data_analyst: Phân tích số liệu, vẽ biểu đồ" in system_prompt
    assert '"needs_clarification"' in system_prompt


def test_rejects_invalid_input_without_calling_provider():
    cases = [
        (REQUEST, []),
        (REQUEST, [*CATALOG, AgentSpec(name="WEB_RESEARCHER", description="dup")]),
        ([], CATALOG),
        ([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}], CATALOG),
        ([{"role": "user", "content": None}], CATALOG),
        ([{"role": "user", "content": [{"type": "image", "source": {}}]}], CATALOG),
        ([{"role": "user", "content": "   "}], CATALOG),
        ([{"role": "user", "content": "hi"}, {"role": "tool", "content": "out"}], CATALOG),
    ]
    for messages, catalog in cases:
        orchestrator, llm = make([VALID])
        expect_value_error(lambda: orchestrator.route(messages, catalog))
        assert llm.calls == [], (messages, catalog)


def test_agent_spec_rejects_empty_name_or_description():
    expect_value_error(lambda: AgentSpec(name="  ", description="x"))
    expect_value_error(lambda: AgentSpec(name="x", description=""))


def test_agent_spec_stores_stripped_fields():
    spec = AgentSpec(name="  writer ", description=" Viết văn bản  ")
    assert (spec.name, spec.description) == ("writer", "Viết văn bản")


def test_agent_spec_rejects_assignment_after_creation():
    spec = AgentSpec(name="writer", description="Viết văn bản")
    expect_value_error(lambda: setattr(spec, "name", ""))
    assert spec.name == "writer"


def test_rejects_duplicate_names_after_strip_without_calling_provider():
    catalog = [AgentSpec(name="writer", description="a"), AgentSpec(name=" Writer ", description="b")]
    orchestrator, llm = make([VALID])
    expect_value_error(lambda: orchestrator.route(REQUEST, catalog))
    assert llm.calls == []


def test_valid_first_attempt_returns_routed_decision():
    orchestrator, llm = make([VALID])
    decision = orchestrator.route(REQUEST, CATALOG)
    assert decision.status == "routed" and decision.architecture == "router"
    assert decision.steps[0].agent == "data_analyst"
    assert decision.meta.attempts == 1
    assert (decision.meta.input_tokens, decision.meta.output_tokens) == (100, 20)
    assert decision.meta.model_id == "fake/model" and decision.meta.error is None
    assert len(llm.calls) == 1


def test_repairs_after_invalid_first_attempt():
    bad = json.dumps({**json.loads(VALID), "steps": [{"id": "s1", "agent": "admin_tool", "task": "x"}]})
    orchestrator, llm = make([bad, VALID])
    decision = orchestrator.route(REQUEST, CATALOG)
    assert decision.status == "routed" and decision.meta.attempts == 2
    assert (decision.meta.input_tokens, decision.meta.output_tokens) == (200, 40)

    second = llm.calls[1]["messages"]
    assert len(second) == 3
    assert second[0] == llm.calls[0]["messages"][0]
    assert second[1] == {"role": "assistant", "content": bad}
    assert second[2]["role"] == "user" and "steps[0].agent" in second[2]["content"] and "admin_tool" in second[2]["content"]


def test_repair_message_lists_one_error_per_line_and_asks_for_json_only():
    orchestrator, llm = make([TWO_ERRORS, VALID])
    orchestrator.route(REQUEST, CATALOG)

    expected_errors = parse_output(TWO_ERRORS, CATALOG)[1]
    assert len(expected_errors) == 2, expected_errors
    content = llm.calls[1]["messages"][2]["content"]
    lines = content.splitlines()
    for error in expected_errors:
        assert error in lines, (error, content)
    assert "JSON object" in content and "no text before or after" in content


def test_repair_uses_placeholder_when_first_answer_empty():
    orchestrator, llm = make([None, VALID])
    decision = orchestrator.route(REQUEST, CATALOG)
    assert decision.meta.attempts == 2
    assert llm.calls[1]["messages"][1] == {"role": "assistant", "content": "(empty)"}


def test_falls_back_after_two_invalid_outputs():
    orchestrator, _ = make(["not json", TWO_ERRORS])
    decision = orchestrator.route(REQUEST, CATALOG)
    assert decision.status == "fallback"
    assert decision.steps == [] and decision.architecture is None and decision.aggregation is None
    assert decision.clarification is None and decision.reasoning == ""
    assert decision.meta.attempts == 2
    # meta.error holds only attempt 2's errors, joined by "; "
    assert decision.meta.error == "; ".join(parse_output(TWO_ERRORS, CATALOG)[1]), decision.meta.error
    assert decision.meta.error.count("; ") >= 1
    assert "no JSON object" not in decision.meta.error
    assert (decision.meta.input_tokens, decision.meta.output_tokens) == (200, 40)


def test_provider_exception_propagates():
    for answers in ([RuntimeError("network down")], ["not json", RuntimeError("quota")]):
        orchestrator, _ = make(answers)
        try:
            orchestrator.route(REQUEST, CATALOG)
        except RuntimeError:
            continue
        raise AssertionError("expected RuntimeError to propagate")


def test_same_input_sends_identical_llm_input():
    orchestrator, llm = make([VALID, VALID])
    orchestrator.route(REQUEST, CATALOG)
    orchestrator.route(REQUEST, CATALOG)
    assert llm.calls[0] == llm.calls[1]


def main():
    tests = [obj for name, obj in globals().items() if name.startswith("test_") and callable(obj)]
    for test in tests:
        test()
        print(f"{test.__name__} OK")
    print(f"\nAll {len(tests)} orchestrator agent tests PASSED")


if __name__ == "__main__":
    main()
