import logging
import random

from tools.base_tool import tool

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# Tool schema (Anthropic format)
SCHEMA = {
    "name": "generate_OTP",
    "description": "Generate a one-time password (OTP) and give it to user",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


@tool(SCHEMA)
def generate_OTP():
    # Generate OTP code
    otp_digits = [str(random.randint(0, 9)) for _ in range(6)]

    # Format as "**XXX-XXX**"
    otp_code = f"**{(''.join(otp_digits[:3]))}-{(''.join(otp_digits[3:]))}**"

    print("Executing OTP tool...")
    return {"otp": otp_code}
