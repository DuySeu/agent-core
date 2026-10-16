import logging
from models.llm_factory import LLM
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

    llm = LLM(
        system_prompt="you are a helpful assistant",
        inference_config=inference_config,
        provider="openai",
        model_id=model.MIMO_V2_FLASH,
    )

    print(f"Provider: {llm.provider}")

    user_message = "Tell me a short story about a brave coder."

    print(f"User: {user_message}")
    print("Assistant: ", end="", flush=True)

    # Test invoke_stream
    try:
        for chunk in llm.invoke_stream(user_message):
            print(chunk, end="", flush=True)
    except Exception as e:
        print(f"\nError during stream: {e}")

    print("\n\nTest complete.")


if __name__ == "__main__":
    main()
