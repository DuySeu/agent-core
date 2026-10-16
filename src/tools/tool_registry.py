"""Tool registry.

Maps a tool's schema ``name`` to its :class:`Tool`. Tools self-register via the
``@tool`` decorator; :meth:`ToolRegistry.discover` imports the implementations
package once so those decorators run.

The top-level ``from tools.base_tool import Tool`` is cycle-safe: ``base_tool``
only imports this ``registry`` lazily, inside the decorator body.
"""

from typing import Dict, List

from tools.base_tool import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._discovered = False

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool

    def discover(self) -> None:
        """Import the implementations package once so @tool decorators run."""
        if self._discovered:
            return
        # Set the flag before importing so a partial failure does not trigger
        # repeated re-import attempts.
        self._discovered = True
        import tools.implementations  # noqa: F401  (import side-effect)

    def get(self, name: str) -> Tool:
        self.discover()
        if name not in self._tools:
            raise ValueError(f"Unknown tool {name!r}. Available: {self.all_names()}")
        return self._tools[name]

    def get_many(self, names: List[str]) -> List[Tool]:
        return [self.get(name) for name in names]

    def all_names(self) -> List[str]:
        self.discover()
        return sorted(self._tools)


registry = ToolRegistry()
