import os
import time
from typing import List, Type, TypeVar

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, ValidationError


# =========================================================
# 1. ENVIRONMENT
# =========================================================
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY not found. Check your .env file."
    )


# =========================================================
# 2. GEMINI CLIENT
# =========================================================
client = genai.Client(
    api_key=API_KEY,
    http_options={
        "timeout": 120000
    },
)


# =========================================================
# 3. MODEL CONFIGURATION
# =========================================================
# Lightweight model first.
# Stronger models are fallbacks.
DEFAULT_MODEL_CHAIN = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
]


def get_model_chain() -> List[str]:
    """
    Allows an optional custom model chain from .env.

    Example:
    TRACEX_MODEL_CHAIN=gemini-3.5-flash-lite,gemini-3.6-flash
    """

    configured = os.getenv("TRACEX_MODEL_CHAIN", "").strip()

    if not configured:
        return DEFAULT_MODEL_CHAIN.copy()

    models = [
        model.strip()
        for model in configured.split(",")
        if model.strip()
    ]

    return models or DEFAULT_MODEL_CHAIN.copy()


# =========================================================
# 4. GENERIC TYPE
# =========================================================
T = TypeVar("T", bound=BaseModel)


# =========================================================
# 5. ERROR CLASSIFICATION
# =========================================================
def classify_error(error: Exception) -> str:
    """
    Classifies an API failure.

    Returns:
        quota
        transient
        validation
        permanent
    """

    message = str(error).lower()

    # -----------------------------------------------------
    # Quota / daily limit
    # -----------------------------------------------------
    quota_keywords = [
        "requests per day",
        "per day on free tier",
        "daily quota",
        "quota exceeded",
        "quota_exceeded",
        "too_many_requests",
        "rate limit exceeded",
    ]

    if any(
        keyword in message
        for keyword in quota_keywords
    ):
        return "quota"

    # -----------------------------------------------------
    # Temporary service issue
    # -----------------------------------------------------
    transient_keywords = [
        "503",
        "service unavailable",
        "service_unavailable",
        "high demand",
        "temporarily unavailable",
        "timeout",
        "deadline exceeded",
        "internal server error",
        "resource exhausted",
        "429",
        "rate limit",
        "rate_limit",
    ]

    if any(
        keyword in message
        for keyword in transient_keywords
    ):
        return "transient"

    return "permanent"


# =========================================================
# 6. STRUCTURED AI GENERATOR
# =========================================================
def generate_structured(
    prompt: str,
    response_model: Type[T],
    agent_name: str = "TraceX Agent",
    max_attempts_per_model: int = 2,
) -> T:
    """
    Sends a prompt to Gemini and returns a validated
    Pydantic object.

    Features:
    - model fallback
    - bounded retry
    - quota detection
    - structured JSON validation
    """

    model_chain = get_model_chain()

    last_error: Exception | None = None

    # -----------------------------------------------------
    # Try every model
    # -----------------------------------------------------
    for model_name in model_chain:

        print(
            f"\n🤖 {agent_name}: "
            f"trying {model_name}"
        )

        # -------------------------------------------------
        # Retry same model for transient failures
        # -------------------------------------------------
        for attempt in range(
            1,
            max_attempts_per_model + 1,
        ):

            try:

                print(
                    f"   Attempt "
                    f"{attempt}/{max_attempts_per_model}"
                )

                interaction = client.interactions.create(
                    model=model_name,
                    input=prompt,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": (
                            response_model.model_json_schema()
                        ),
                    },
                )

                # -------------------------------------------------
                # Validate response
                # -------------------------------------------------
                result = response_model.model_validate_json(
                    interaction.output_text
                )

                print(
                    f"✅ {agent_name}: "
                    f"completed with {model_name}"
                )

                return result

            except ValidationError as error:

                print(
                    f"❌ {agent_name}: "
                    f"invalid structured output."
                )

                raise RuntimeError(
                    f"{agent_name} received invalid "
                    f"structured output from Gemini."
                ) from error

            except Exception as error:

                last_error = error

                error_type = classify_error(error)

                # =================================================
                # QUOTA
                # =================================================
                if error_type == "quota":

                    print(
                        f"⚠️ {agent_name}: "
                        f"{model_name} quota unavailable."
                    )

                    print(
                        "➡️ Skipping this model."
                    )

                    break

                # =================================================
                # TRANSIENT
                # =================================================
                if error_type == "transient":

                    print(
                        f"⚠️ {agent_name}: "
                        f"temporary problem."
                    )

                    if attempt < max_attempts_per_model:

                        wait_time = 2 ** attempt

                        print(
                            f"⏳ Waiting "
                            f"{wait_time} seconds..."
                        )

                        time.sleep(wait_time)

                        continue

                    print(
                        "➡️ Retry limit reached. "
                        "Moving to next model."
                    )

                    break

                # =================================================
                # PERMANENT
                # =================================================
                print(
                    f"❌ {agent_name}: "
                    f"non-retryable error."
                )

                raise RuntimeError(
                    f"{agent_name} failed with "
                    f"{model_name}: {error}"
                ) from error

    # =========================================================
    # ALL MODELS FAILED
    # =========================================================
    raise RuntimeError(
        f"{agent_name}: all configured Gemini models "
        f"were unavailable."
    ) from last_error


# =========================================================
# 7. SIMPLE TEXT GENERATOR
# =========================================================
def generate_text(
    prompt: str,
    agent_name: str = "TraceX Agent",
) -> str:
    """
    Generates normal text output.

    Useful for:
    - summaries
    - action plans
    - UI explanations
    - draft messages
    """

    model_chain = get_model_chain()

    last_error: Exception | None = None

    for model_name in model_chain:

        print(
            f"\n🤖 {agent_name}: "
            f"trying {model_name}"
        )

        for attempt in range(1, 3):

            try:

                interaction = client.interactions.create(
                    model=model_name,
                    input=prompt,
                )

                output = (
                    interaction.output_text
                    .strip()
                )

                if not output:
                    raise ValueError(
                        "Gemini returned empty output."
                    )

                print(
                    f"✅ {agent_name}: "
                    f"completed with {model_name}"
                )

                return output

            except Exception as error:

                last_error = error

                error_type = classify_error(error)

                if error_type == "quota":

                    print(
                        f"⚠️ {model_name} quota unavailable."
                    )

                    break

                if error_type == "transient":

                    if attempt < 2:

                        wait_time = 2 ** attempt

                        print(
                            f"⏳ Retrying in "
                            f"{wait_time} seconds..."
                        )

                        time.sleep(wait_time)

                        continue

                    break

                raise RuntimeError(
                    f"{agent_name} failed: {error}"
                ) from error

    raise RuntimeError(
        f"{agent_name}: all configured Gemini models "
        f"were unavailable."
    ) from last_error


# =========================================================
# 8. SERVICE STATUS
# =========================================================
def get_service_status() -> dict:
    """
    Returns basic information useful for the dashboard.
    """

    return {
        "provider": "Google Gemini",
        "configured_models": get_model_chain(),
        "status": "READY",
    }


# =========================================================
# 9. LOCAL TEST
# =========================================================
class AIServiceTestResponse(BaseModel):

    status: str
    message: str


if __name__ == "__main__":

    print("\n")
    print("===============================================")
    print("       TRACEX AI — CENTRAL AI SERVICE")
    print("===============================================\n")

    print("Configured model chain:")

    for index, model in enumerate(
        get_model_chain(),
        start=1,
    ):
        print(f"{index}. {model}")

    print("\nTesting central Gemini service...")

    test_prompt = """
You are testing the TraceX AI central service.

Return:
status = SUCCESS
message = TraceX central AI service is working
"""

    try:

        result = generate_structured(
            prompt=test_prompt,
            response_model=AIServiceTestResponse,
            agent_name="AI Service Test",
        )

        print("\n-----------------------------------------------")
        print("TEST RESULT")
        print("-----------------------------------------------")

        print(
            result.model_dump_json(
                indent=2
            )
        )

        print(
            "\n✅ Central AI Service is working."
        )

    except Exception as error:

        print("\n❌ Central AI Service failed.")
        print(f"Error: {error}")