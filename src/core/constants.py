class ModelId:
    CLAUDE_3_HAIKU = "anthropic.claude-3-haiku-20240307-v1:0"
    CLAUDE_3_5_HAIKU = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    CLAUDE_3_5_SONNET_V1 = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    CLAUDE_3_5_SONNET_V2 = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"

    NEMOTRON_NANO_12B_V2_VL = "nvidia/nemotron-nano-12b-v2-vl:free"
    NEMOTRON_3_NANO_30B_A3B = "nvidia/nemotron-3-nano-30b-a3b:free"
    MIMO_V2_FLASH = "xiaomi/mimo-v2-flash:free"


class Region:
    AP_SOUTHEAST_1 = "ap-southeast-1"


message = [
    {
        "content": "string",
        "file": {
            "base64": "string",
            "fileName": "string",
            "mediaType": "string",
            "isText": "boolean",
        },
    }
]


model = ModelId()
region = Region()
