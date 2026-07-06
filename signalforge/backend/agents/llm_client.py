from openai import AsyncOpenAI
from backend.config import settings
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PRIMARY_MODEL  = "google/gemma-4-26b-a4b-it:free"
FALLBACK_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def get_llm_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "https://signalforge.local",
            "X-Title": "SignalForge",
        },
    )


async def call_llm(
    system: str,
    user: str,
    max_tokens: int = 512,
) -> str:
    """
    Call LLM with automatic fallback across PRIMARY and FALLBACK models.

    ALWAYS returns a plain str. NEVER returns None. NEVER raises.

    OpenRouter free models return HTTP 200 with content=None when
    overloaded. Every attribute access on the response is guarded
    with an explicit None check before any string operation.
    """
    client = get_llm_client()

    for attempt, model in enumerate([PRIMARY_MODEL, FALLBACK_MODEL]):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )

            # Guard: choices list may be None or empty
            choices = getattr(response, "choices", None)
            if not choices:
                logger.warning(
                    "llm_client: %s returned no choices (attempt %d)",
                    model, attempt + 1,
                )
                continue

            # Guard: message may be None
            message = getattr(choices[0], "message", None)
            if message is None:
                logger.warning(
                    "llm_client: %s returned None message (attempt %d)",
                    model, attempt + 1,
                )
                continue

            # Guard: content may be None — this is the confirmed crash site
            content = getattr(message, "content", None)
            if content is None:
                logger.warning(
                    "llm_client: %s returned None content (attempt %d) "
                    "— model overloaded or refused",
                    model, attempt + 1,
                )
                continue

            # Safe to call string methods now that None is excluded
            content = str(content)

            # Strip DeepSeek R1 chain-of-thought <thought> blocks
            if "thought" in content and "*/" in content:
                parts = content.split("*/", 1)
                content = parts[1] if len(parts) > 1 else content

            content = content.strip()

            if not content:
                logger.warning(
                    "llm_client: %s returned empty string after strip (attempt %d)",
                    model, attempt + 1,
                )
                continue

            if attempt > 0:
                logger.info("llm_client: fallback to %s succeeded", model)

            return content

        except Exception as exc:
            logger.warning(
                "llm_client: %s raised exception (attempt %d): %s",
                model, attempt + 1, exc,
            )

    logger.error(
        "llm_client: both %s and %s failed — returning empty string",
        PRIMARY_MODEL, FALLBACK_MODEL,
    )
    return ""


class LLMClient:
    def __init__(self):
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not set in environment variables")

        self.client = AsyncOpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )
        self.model = settings.LLM_MODEL

    async def generate_completion(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Generate a completion using the LLM."""
        try:
            logger.info("Calling LLM using model %s", self.model)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            # Guard against None content
            content = getattr(response.choices[0].message, "content", None)
            if content is None:
                logger.warning("LLM returned None content in generate_completion")
                return ""
            return str(content).strip()
        except Exception as e:
            logger.error(f"Error generating LLM completion: {e}")
            raise

    async def generate_structured_completion(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Generate a completion with optional system message."""
        try:
            messages = []
            if system_message:
                messages.append({"role": "system", "content": system_message})
            messages.append({"role": "user", "content": prompt})

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            # Guard against None content
            content = getattr(response.choices[0].message, "content", None)
            if content is None:
                logger.warning("LLM returned None content in generate_structured_completion")
                return ""
            return str(content).strip()
        except Exception as e:
            logger.error(f"Error generating structured LLM completion: {e}")
            raise


# Global LLM client instance
llm_client = LLMClient()