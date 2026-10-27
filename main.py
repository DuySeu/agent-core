"""Manual runner for testing individual components.

python main.py orchestrator
"""

from __future__ import annotations

import sys
from pathlib import Path

# src/ is the import root; adding it here lets `python main.py` run without PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agents.orchestrator_agent import OrchestratorAgent
from core.constants import model
from orchestration.routing_schema import AgentSpec

# Edit these to try another model or request
ORCHESTRATOR_MODEL_ID = model.NEMOTRON_3_5_SUPER_VL
ORCHESTRATOR_MESSAGES = [
    {
        "role": "user",
        "content": "Tìm số liệu GDP Việt Nam 5 năm gần nhất rồi vẽ biểu đồ",
    },
]

DEMO_CATALOG = [
    AgentSpec(name="web_researcher", description="Tìm thông tin trên web"),
    AgentSpec(name="data_analyst", description="Phân tích số liệu, vẽ biểu đồ"),
    AgentSpec(name="writer", description="Viết và biên tập văn bản"),
    AgentSpec(name="calendar_assistant", description="Lịch và thời gian"),
    AgentSpec(
        name="general_assistant",
        description="Trả lời chung, tổng hợp kết quả từ nhiều nguồn",
    ),
]


def run_orchestrator() -> None:
    orchestrator = OrchestratorAgent(
        model_id=ORCHESTRATOR_MODEL_ID,
        inference_config={"max_tokens": 1024, "temperature": 0},
    )
    print(f"Model: {ORCHESTRATOR_MODEL_ID}")
    print("Catalog: " + ", ".join(spec.name for spec in DEMO_CATALOG))
    print(f"Request: {ORCHESTRATOR_MESSAGES[-1]['content']}")
    decision = orchestrator.route(ORCHESTRATOR_MESSAGES, DEMO_CATALOG)
    print(decision.model_dump_json(indent=2))


COMMANDS = {"orchestrator": run_orchestrator}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"Usage: python main.py <{'|'.join(COMMANDS)}>")
    # Missing OPENROUTER_API_KEY or invalid input surfaces as ValueError; provider errors keep their traceback
    try:
        COMMANDS[sys.argv[1]]()
    except ValueError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
