import logging

from tools.base_tool import tool

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# Tool schema (Anthropic format)
SCHEMA = {
    "name": "generate_graph_data",
    "description": "Generate structured JSON data for creating financial charts and graphs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "chartType": {
                "type": "string",
                "enum": ["bar", "multiBar", "line", "pie", "area", "stackedArea"],
                "description": "The type of chart to generate",
            },
            "config": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "totalLabel": {"type": "string"},
                    "xAxisKey": {"type": "string"},
                    "yAxisKey": {"type": "string"},
                },
                "required": ["title", "description"],
            },
            "data": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
            "chartConfig": {
                "type": "object",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "stacked": {"type": "boolean"},
                    },
                    "required": ["label"],
                },
            },
        },
        "required": ["chartType", "config", "data", "chartConfig"],
    },
}


@tool(SCHEMA)
def generate_graph_data(chartType, config, data, chartConfig):
    chart_data = {
        "chartType": chartType,
        "config": config,
        "data": data,
        "chartConfig": chartConfig,
    }

    # Transform data format for pie chart
    for item in chart_data.get("data", []):
        # Find the key that represents the segment (category/label)
        segment_key = next(
            (
                key
                for key in item.keys()
                if key.lower() in ["sex", "category", "label", "name", "type"]
            ),
            None,
        )
        # Find the key that represents the value (numeric data)
        value_key = next(
            (
                key
                for key in item.keys()
                if key.lower() in ["expenses", "value", "amount", "count"]
            ),
            None,
        )

        if segment_key and value_key:
            item["segment"] = item.pop(segment_key)
            item["value"] = item.pop(value_key)

    processed_chart_config = {}
    for index, (key, cfg) in enumerate(chart_data.get("chartConfig", {}).items()):
        processed_chart_config[key] = {
            **cfg,
            "color": f"hsl(var(--chart-{index + 1}))",
        }

    # Return updated chart data with processed config
    return {**chart_data, "chartConfig": processed_chart_config}
