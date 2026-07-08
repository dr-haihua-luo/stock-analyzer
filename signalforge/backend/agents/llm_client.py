from openai import AsyncOpenAI
from backend.config import settings
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# PRIMARY_MODEL  = "google/gemma-4-26b-a4b-it:free"
# FALLBACK_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


class LLMClient:
    def __init__(self):
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not set in environment variables")

        self.client = AsyncOpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            default_headers={
                "HTTP-Referer": "https://signalforge.local",
                "X-Title": "SignalForge",
            },
        )
        self.model = settings.PRIMARY_MODEL
        self.fallback_model = settings.FALLBACK_MODEL

    async def _try_llm_call(
        self,
        messages: list,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Optional[str]:
        """
        Attempt a single LLM call, returning None on failure.
        Does NOT raise exceptions - all errors are guarded and logged.
        """
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            # Guard: choices list may be None or empty
            choices = getattr(response, "choices", None)
            if not choices:
                logger.warning("LLM %s returned no choices", model)
                return None

            # Guard: message may be None
            message = getattr(choices[0], "message", None)
            if message is None:
                logger.warning("LLM %s returned None message", model)
                return None

            # Guard: content may be None — OpenRouter returns this when overloaded
            content = getattr(message, "content", None)
            if content is None:
                logger.warning(
                    "LLM %s returned None content — model overloaded or refused",
                    model,
                )
                return None

            content = str(content).strip()

            if not content:
                logger.warning("LLM %s returned empty string after strip", model)
                return None

            return content

        except Exception as exc:
            logger.warning("LLM %s raised exception: %s", model, exc)
            return None


    async def generate_structured_completion(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        max_tokens: int = 10000,
        temperature: float = 0.1,
    ) -> str:
        """
        Generate a completion with optional system message.
        Uses primary/fallback model fallback for resilience.

        ALWAYS returns a plain str. NEVER returns None. NEVER raises.
        """
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        for attempt, model in enumerate([self.model, self.fallback_model]):
            logger.info("Calling LLM with model %s", model)
            result = await self._try_llm_call(messages, model, max_tokens, temperature)
            if result is not None:
                if attempt > 0:
                    logger.info("LLM fallback succeeded for generate_structured_completion")
                return result

        logger.error("LLM call failed for generate_structured_completion — returning empty string")
        return ""


# Global LLM client instance
llm_client = LLMClient()