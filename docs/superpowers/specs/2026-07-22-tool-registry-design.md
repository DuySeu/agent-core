# Design: Name-based Tool Registry

**Date:** 2026-07-22
**Status:** Approved (pending spec review)
**Scope:** `src/tools/`, `src/agents/base_agent.py`, `tests/`

## Problem

Defining an agent currently requires manually pairing a tool schema with its
implementation function:

```python
agent.add_tool(generate_OTP_tool, generate_OTP)
```

We want an agent to reference tools **by name only**:

```python
agent = Agent(..., tools=["web_search", "generate_OTP"])
```

The existing tools also block this because they are inconsistent and partly
incompatible with the current `Agent`:

- **Schema shape differs:** `generate_OTP_tool` is a `dict`; `web_search_tool`,
  `generate_chart_tool`, and `get_realtime_tool` are `list`-wrapped. `Agent.add_tool`
  reads `tool["name"]`, so the list-wrapped ones fail today.
- **Function signatures differ:** `generate_OTP()` takes no args, while
  `execute_chart(tool_name, tool_input)`, `execute_web_search(tool_name, tool_input)`,
  and `get_time(tool_name, tool_input)` take two positional args. The `Agent`
  loop invokes tools as `func(**arguments)` (arguments = the model's parsed JSON
  tool input), so only `generate_OTP` works right now; the others raise
  `TypeError`.

## Goals

- Reference tools by their **schema `name`** (the identifier the LLM emits in
  `tool_calls`) — a single source of truth, no secondary mapping.
- One uniform standard every tool file follows: declare a `SCHEMA` dict and a
  decorated function.
- A registry that maps `name → tool`, populated automatically by importing the
  implementations package (decorator side-effect).
- Normalize all existing tools to the standard so they actually run through the
  `Agent`.

## Non-goals

- Input validation against `input_schema` (deferred; can be added later in
  `BaseTool`/`Tool.run`).
- Implementing `get_time` behavior (stays a stub; only its signature is
  normalized).
- Changing the provider layer or the tool-calling loop itself.

## Architecture

Fills the two existing stubs from `docs/project_structure.jpg` (`base_tool.py`
"Base tool class", `tool_registry.py` "Tool registry") plus the implementations
package init. No files are added outside the documented structure.

### `src/tools/base_tool.py` — tool contract + decorator

```python
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
    """Decorator: register the decorated function as a Tool built from `schema`,
    and return the function unchanged so it stays directly callable."""
    def decorator(func: Callable) -> Callable:
        # lazy import avoids a base_tool <-> tool_registry import cycle
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
```

### `src/tools/tool_registry.py` — the registry

`tool_registry.py` top-imports `Tool` from `base_tool` (needed for the type
annotations below). This is safe and does **not** create a cycle: `base_tool`
only imports `registry` *lazily* inside the decorator body, so importing
`base_tool` at the top of `tool_registry` pulls in no reverse dependency.

```python
from typing import Dict
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
        self._discovered = True
        import tools.implementations  # noqa: F401  (import side-effect)

    def get(self, name: str) -> Tool:
        self.discover()
        if name not in self._tools:
            raise ValueError(
                f"Unknown tool {name!r}. Available: {self.all_names()}"
            )
        return self._tools[name]

    def get_many(self, names):
        return [self.get(n) for n in names]

    def all_names(self):
        self.discover()
        return sorted(self._tools)

registry = ToolRegistry()
```

Note: `discover()` sets `_discovered = True` *before* importing, so a partially
failing import cannot cause repeated re-import attempts.

### `src/tools/implementations/__init__.py` — auto-import

Dynamically import every `*_tool.py` module in the package so their `@tool`
decorators execute. Wrap each import in try/except so one broken module (e.g. a
missing optional dependency) is skipped with a warning instead of taking down
the whole registry.

```python
import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)

for _module in pkgutil.iter_modules(__path__):
    if _module.name.endswith("_tool"):
        try:
            importlib.import_module(f"{__name__}.{_module.name}")
        except Exception as e:  # optional dep missing, etc.
            logger.warning("Skipping tool module %s: %s", _module.name, e)
```

### `src/agents/base_agent.py` — name-based tools

- `__init__(..., tools: Optional[List[str]] = None)`: for each name,
  `registry.get(name)`; collect `.schema` into `self.tools` (list of dicts the
  providers iterate) and `.func` into `self.tool_registry` (name → callable).
- `add_tool(name: str)`: resolve one tool by name from the registry (same
  effect). Replaces the old `add_tool(schema, func)` signature.
- **Deduplicate by name.** Resolution (both the constructor list and repeated
  `add_tool`) is idempotent: if a name is already present in
  `self.tool_registry`, skip it rather than appending a second copy of the schema
  into `self.tools` — providers can reject duplicate tool definitions.
- The multi-turn tool-calling loop is unchanged; it already calls
  `self.tool_registry[name](**arguments)`.

## Tool authoring standard

Each `implementations/<x>_tool.py`:

1. Defines a module-level `SCHEMA` **dict** in Anthropic format
   (`name` / `description` / `input_schema`).
2. Defines a function decorated with `@tool(SCHEMA)` whose parameters are
   **explicit keyword arguments, one per top-level key in `input_schema.properties`**
   (optional ones have defaults). This is the single canonical pattern — no
   `**kwargs` catch-all — so every normalized tool looks the same and
   `func(**arguments)` binds cleanly. A tool with an empty `input_schema`
   (no properties) takes no parameters.
3. Lazy-imports heavy/optional dependencies **inside** the function.

Every `SCHEMA` uses the same `input_schema` shape:
`{"type": "object", "properties": {...}, "required": [...]}`. Tools with no
input (e.g. OTP) use `"properties": {}` and omit `required`.

## Normalizing existing tools

| File | SCHEMA var | Function (new signature) | Notes |
|------|-----------|--------------------------|-------|
| `web_search_tool.py` | `SCHEMA` (was list `web_search_tool`) | `web_search(query, numResults=3)` | lazy-import `DDGS`; see return semantics below |
| `chart_tool.py` | `SCHEMA` (was list `generate_chart_tool`) | `generate_graph_data(chartType, config, data, chartConfig)` | explicit params; body reuses existing transform, returns the processed chart dict |
| `otp_tool.py` | `SCHEMA` (was dict `generate_OTP_tool`) | `generate_OTP()` | unchanged behavior; SCHEMA gets `"properties": {}` |
| `time_tool.py` | `SCHEMA` (was list `get_realtime_tool`) | `get_time(location, unit="%H:%M:%S")` | stays a stub (returns `None`, no behavior) |
| `calendar_tool.py`, `email_tool.py` | — | — | empty stubs; register nothing |

Function names may match the schema `name` for readability, but the registry
maps by schema `name` regardless of `func.__name__`.

**`web_search` return semantics.** `numResults` is wired through to
`DDGS().text(query, max_results=numResults)` (replacing the current hardcoded
`5`). The function **returns the text-results list** (list of `{title, href,
body}` dicts) — that value is what the Agent stringifies back into the
conversation. The current debug `print(...)` calls and the separate
`ddgs.chat(query)` call are dropped so the return value is the single, defined
result.

## Data flow

1. First registry access → `discover()` imports `tools.implementations` →
   `__init__` imports each `*_tool.py` → each `@tool(SCHEMA)` runs →
   `registry.register(Tool(...))`.
2. `Agent(tools=[...])` → `registry.get(name)` per name → `self.tools` (schemas)
   and `self.tool_registry` (name → func) populated.
3. Runtime → model emits `tool_call(name, arguments)` → Agent calls
   `self.tool_registry[name](**arguments)` → result appended to history.

## Error handling

- **Unknown tool name** at `Agent(tools=[...])` / `add_tool(name)` →
  `ValueError` immediately (fail fast), listing `registry.all_names()`.
- **Module import failure** during discovery (e.g. `duckduckgo-search` not
  installed) → warning logged, module skipped; the tool is simply absent, so
  referencing it produces the unknown-tool error listing what *is* available.
- **Duplicate tool name** at registration → `ValueError`.

## Testing

- `tests/test_tools/test_registry.py` (new): discovery finds the expected tools;
  `get` / `get_many` return correct schema+func; unknown name raises;
  duplicate registration raises.
- `tests/test_agents/test_agent.py` (update): switch to `tools=["generate_OTP"]`;
  verify `self.tools` / `self.tool_registry` are populated from the registry.
- Style: runnable smoke scripts (`PYTHONPATH=src python tests/...`), matching the
  repo convention.

## Backward compatibility / breaking changes

- `Agent.add_tool(schema, func)` → `Agent.add_tool(name)`: **breaking**. The one
  in-repo caller (`tests/test_agents/test_agent.py`) is updated in this change.
- Existing tool module-level names (`web_search_tool`, `generate_chart_tool`,
  `get_realtime_tool`, `generate_OTP_tool`) are renamed to `SCHEMA`. No other
  code imports them after this change.
