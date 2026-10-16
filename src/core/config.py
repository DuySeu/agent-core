import os
from dotenv import load_dotenv

# Load dot environment
load_dotenv()


# Setup class configs
class Config:
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID") or ""
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY") or ""
    AWS_ROLE_ARN = os.getenv("AWS_ROLE_ARN") or ""
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or ""
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") or ""


config = Config()
