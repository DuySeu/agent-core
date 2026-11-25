"""Build the LLM provider named by a provider string."""

from __future__ import annotations

from core.config import config
from core.constants import region
from models.llm_factory import LLMProvider
from models.provider import BedrockProvider, OpenAIProvider, OpenRouterProvider

# Text of an OpenRouter 429 that means the daily free-model cap, not a per-minute limit
OPENROUTER_DAILY_CAP_PATTERN = "free-models-per-day"
# boto3 has no per-call timeout; this is botocore's default read timeout
BEDROCK_READ_TIMEOUT_S = 60.0


# "openai" and "openrouter" pick those providers, anything else is Bedrock (needs max_tokens)
def build_llm(provider: str, max_tokens: int) -> LLMProvider:
    if provider == "openai":
        return OpenAIProvider(config.OPENAI_API_KEY)
    if provider == "openrouter":
        return OpenRouterProvider(config.OPENROUTER_API_KEY, OPENROUTER_DAILY_CAP_PATTERN)
    return BedrockProvider(
        region=region.AP_SOUTHEAST_1,
        access_key=config.AWS_ACCESS_KEY_ID,
        secret_key=config.AWS_SECRET_ACCESS_KEY,
        role_arn=config.AWS_ROLE_ARN,
        read_timeout_s=BEDROCK_READ_TIMEOUT_S,
        max_tokens=max_tokens,
    )
