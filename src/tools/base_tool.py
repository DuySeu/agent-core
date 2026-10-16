"""Base tool class.

A tool is a plain function plus its Anthropic-format schema. Declare one with
the ``@tool(SCHEMA)`` decorator in a module under ``tools/implementations/``:

    from tools.base_tool import tool

    SCHEMA = {
        "name": "web_search",
        "description": "...",
        "input_schema": {"type": "object", "properties": {...}, "required": [...]},
    }

    @tool(SCHEMA)
    def web_search(query, numResults=3):
        ...

The decorator registers the tool by its schema ``name`` and returns the function
unchanged, so it stays directly callable.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    func: Callable

    @property
    def schema(self) -> Dict[str, Any]:
        """Anthropic-format schema consumed by the providers."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def run(self, **kwargs):
        return self.func(**kwargs)


def tool(schema: Dict[str, Any]) -> Callable:
    """Register the decorated function as a Tool built from ``schema``.

    Returns the function unchanged so it remains directly callable.
    """

    def decorator(func: Callable) -> Callable:
        # Lazy import avoids a base_tool <-> tool_registry import cycle.
        from tools.tool_registry import registry

        registry.register(
            Tool(
                name=schema["name"],
                description=schema.get("description", ""),
                input_schema=schema.get("input_schema", {"type": "object"}),
                func=func,
            )
        )
        return func

    return decorator
