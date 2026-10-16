import logging
from agents.base_agent import Agent
from core.constants import model

# Setup logging
logging.basicConfig(level=logging.INFO)


def main():
    print("Testing Agent with Tool Calling (name-based tools)...")

    # Configuration
    inference_config = {
        "max_tokens": 1000,
        "temperature": 0.7,
        "top_p": 0.9,
    }

    # Initialize Agent — just name the tools implemented in tools/implementations
    agent = Agent(
        system_prompt="You are a helpful assistant. Use tools when needed.",
        inference_config=inference_config,
        provider="openrouter",
        model_id=model.NEMOTRON_3_NANO_30B_A3B,  # a model that supports function calling
        max_history=10,
        tools=["generate_OTP"],
    )

    # Tool wiring is resolved from the registry (no network needed to check this)
    assert [t["name"] for t in agent.tools] == ["generate_OTP"], agent.tools
    assert "generate_OTP" in agent.tool_registry
    print(f"Provider: {agent.provider} | tools: {[t['name'] for t in agent.tools]}")

    user_message = "Give me OTP code to subscribe my 5G packet"

    print(f"User: {user_message}")
    print("Assistant: ", end="", flush=True)

    # Test invoke_stream (needs OPENROUTER_API_KEY for the live model call)
    try:
        for chunk in agent.invoke_stream(user_message):
            print(chunk, end="", flush=True)
    except Exception as e:
        print(f"\nError during stream: {e}")

    print("\n\nTest complete.")


if __name__ == "__main__":
    main()
