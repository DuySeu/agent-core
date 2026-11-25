import logging
from core.wiring import build_llm
from core.constants import model

# Setup logging
logging.basicConfig(level=logging.INFO)


def main():
    print("Testing Agent invoke_stream...")

    # Configuration
    inference_config = {
        "max_tokens": 1000,
        "temperature": 0.7,
        "top_p": 0.9,
    }

    # Initialize Agent
    # The provider defaults to "bedrock" in core.py.
    # To test OpenAI/OpenRouter, ensure OPENROUTER_API_KEY is set in .env or config
    # and set agent.provider = "openai" manually or via constructor if refactored.

    llm = build_llm("openai", inference_config["max_tokens"])
    model_id = model.MIMO_V2_FLASH

    print(f"Provider: {llm.name}")

    user_message = "Tell me a short story about a brave coder."

    print(f"User: {user_message}")
    print("Assistant: ", end="", flush=True)

    # Test invoke_stream
    try:
        for chunk in llm.invoke_stream(
            model_id, [{"role": "user", "content": user_message}], "you are a helpful assistant"
        ):
            if chunk.delta:
                print(chunk.delta, end="", flush=True)
    except Exception as e:
        print(f"\nError during stream: {e}")

    print("\n\nTest complete.")


if __name__ == "__main__":
    main()
