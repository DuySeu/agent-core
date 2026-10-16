# Implementation Plan: Name-based Tool Registry

**Spec:** `docs/superpowers/specs/2026-07-22-tool-registry-design.md`
**Date:** 2026-07-22

Ordered phases. Each phase ends with a verification step; do not advance until it
passes. Run everything with `PYTHONPATH=src` using the project venv
(`.venv/bin/python`).

## Phase 1 — `src/tools/base_tool.py`

Implement the `Tool` dataclass (`name`, `description`, `input_schema`, `func`;
`.schema` property → `{name, description, input_schema}`; `.run(**kwargs)`), and
the `tool(schema)` decorator that builds a `Tool` and registers it (lazy
`from tools.tool_registry import registry` inside the decorator to avoid a
cycle), returning the function unchanged.

**Verify:** `PYTHONPATH=src python -c "from tools.base_tool import Tool, tool; print('ok')"`

## Phase 2 — `src/tools/tool_registry.py`

Implement `ToolRegistry` (`register` with duplicate-name `ValueError`; `get` with
unknown-name `ValueError` listing `all_names()`; `get_many`; `all_names`;
idempotent `discover()` that sets `_discovered=True` before
`import tools.implementations`) and the module-level `registry` singleton.

**Verify:** `PYTHONPATH=src python -c "from tools.tool_registry import registry; print(registry.all_names())"`
(prints the discovered tool names).

## Phase 3 — `src/tools/implementations/__init__.py`

Dynamically import every `*_tool.py` via `pkgutil.iter_modules`, each wrapped in
try/except that logs a warning and skips on failure.

**Verify:** covered by Phase 2's `all_names()` call — a missing optional dep
(e.g. `duckduckgo-search`) must produce a warning and a shorter list, not a crash.

## Phase 4 — Normalize the four existing tools

For each `implementations/*_tool.py`: rename the module-level schema var to
`SCHEMA` (a **dict**), decorate the function with `@tool(SCHEMA)`, and give the
function explicit kwargs matching `input_schema.properties`:

- `otp_tool.py` — `SCHEMA` dict with `"properties": {}`; `generate_OTP()` unchanged.
- `web_search_tool.py` — `web_search(query, numResults=3)`; lazy-import `DDGS`;
  `DDGS().text(query, max_results=numResults)`; return the text-results list;
  drop the `print(...)` calls and the `ddgs.chat(query)` call.
- `chart_tool.py` — `generate_graph_data(chartType, config, data, chartConfig)`;
  reuse the existing transform; return the processed chart dict.
- `time_tool.py` — `get_time(location, unit="%H:%M:%S")`; remains a stub
  (returns `None`).

`calendar_tool.py` / `email_tool.py` stay empty (register nothing).

**Verify:** `PYTHONPATH=src python -c "from tools.tool_registry import registry; print(sorted(registry.all_names()))"`
→ includes `generate_OTP`, `generate_graph_data`, `get_time`, and `web_search`
(the last only if `duckduckgo-search` is installed; otherwise a warning + absent).

## Phase 5 — `src/agents/base_agent.py`

Add `tools: Optional[List[str]] = None` to `__init__`; resolve each name via
`registry.get(name)`, populating `self.tools` (schemas) and `self.tool_registry`
(name → func), deduping by name. Change `add_tool(name: str)` to resolve one tool
by name (same dedupe). Leave the tool-calling loop untouched.

**Verify:**
```python
PYTHONPATH=src python -c "
from agents.base_agent import Agent
a = Agent(system_prompt='x', inference_config={}, provider='openrouter', model_id='m', tools=['generate_OTP'])
assert a.tools and a.tools[0]['name']=='generate_OTP'
assert 'generate_OTP' in a.tool_registry
try:
    Agent(system_prompt='x', inference_config={}, provider='openrouter', model_id='m', tools=['nope'])
    raise SystemExit('should have raised')
except ValueError as e:
    print('unknown-tool raises OK:', str(e)[:40])
"
```

## Phase 6 — Tests

- New `tests/test_tools/test_registry.py`: discovery finds expected tools;
  `get`/`get_many` return correct schema+func; unknown name raises; duplicate
  registration raises. Runnable-script style with a `main()`.
- Update `tests/test_agents/test_agent.py`: use `Agent(tools=["generate_OTP"])`
  instead of `add_tool(generate_OTP_tool, generate_OTP)`; drop the old import.

**Verify:** `PYTHONPATH=src python tests/test_tools/test_registry.py` and
`PYTHONPATH=src python tests/test_agents/test_agent.py` both run clean (the agent
test needs `OPENROUTER_API_KEY` for the live model call; the registry wiring
asserts run without network).

## Phase 7 — Final check & docs

- `PYTHONPATH=src python -m py_compile $(find src -name '*.py')` — full compile.
- Update `docs/architecture.md` tools/ section: `base_tool.py` and
  `tool_registry.py` become ✅, note the `@tool` + `tools=[names]` flow.

## Rollback note

Not a git repo. Before editing, the current tool files are preserved in the spec
and this plan; the change is additive to the two stubs plus signature edits to
four tool files and `base_agent.py` — reversible by hand if needed.
