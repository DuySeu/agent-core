from tools.base_tool import tool

# Tool schema (Anthropic format)
SCHEMA = {
    "name": "get_time",
    "description": "Get the current time in a given location",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The city and state, e.g. San Francisco, CA",
            },
            "unit": {
                "type": "string",
                "enum": ["%H:%M:%S"],
                "description": 'The unit of hour is "%H:%M:%S"',
            },
        },
        "required": ["location"],
    },
}


@tool(SCHEMA)
def get_time(location, unit="%H:%M:%S"):
    """Execute the get_time tool. (Not implemented yet.)"""
    return None
