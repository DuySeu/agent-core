import logging

from core.config import config
from tools.base_tool import tool

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# Tool schema (Anthropic format)
SCHEMA = {
    "name": "web_search",
    "description": "Search the web for Vietnamobile static information.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the web.",
            },
            "numResults": {
                "type": "integer",
                "description": "The number of search results to retrieve.",
                "default": 3,
            },
        },
        "required": ["query"],
    },
}


@tool(SCHEMA)
def web_search(query, numResults=3):
    # Lazy import: tavily-python is an optional dependency.
    from tavily import TavilyClient

    client = TavilyClient(api_key=config.TAVILY_API_KEY)
    response = client.search(query, max_results=numResults)
    return response["results"]
