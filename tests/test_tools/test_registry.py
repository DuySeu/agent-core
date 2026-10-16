import logging

from tools.base_tool import Tool
from tools.tool_registry import registry, ToolRegistry

logging.basicConfig(level=logging.INFO)

EXPECTED = {"generate_OTP", "generate_graph_data", "get_time", "web_search"}


def test_discovery():
    names = set(registry.all_names())
    assert EXPECTED <= names, f"missing tools: {EXPECTED - names}"
    print("discovery OK:", sorted(names))


def test_get():
    t = registry.get("generate_OTP")
    assert t.name == "generate_OTP"
    assert t.schema == {
        "name": t.name,
        "description": t.description,
        "input_schema": t.input_schema,
    }
    assert callable(t.func)
    print("get OK")


def test_get_many():
    tools = registry.get_many(["generate_OTP", "get_time"])
    assert [t.name for t in tools] == ["generate_OTP", "get_time"]
    print("get_many OK")


def test_unknown_raises():
    try:
        registry.get("does_not_exist")
    except ValueError as e:
        print("unknown-name raises OK:", str(e)[:50])
    else:
        raise AssertionError("expected ValueError for unknown tool")


def test_duplicate_raises():
    reg = ToolRegistry()  # fresh registry, no global side effects
    schema = {"type": "object", "properties": {}}
    reg.register(Tool("dup", "desc", schema, lambda: None))
    try:
        reg.register(Tool("dup", "desc", schema, lambda: None))
    except ValueError as e:
        print("duplicate-name raises OK:", str(e)[:50])
    else:
        raise AssertionError("expected ValueError for duplicate name")


def main():
    test_discovery()
    test_get()
    test_get_many()
    test_unknown_raises()
    test_duplicate_raises()
    print("\nAll registry tests PASSED ✅")


if __name__ == "__main__":
    main()
