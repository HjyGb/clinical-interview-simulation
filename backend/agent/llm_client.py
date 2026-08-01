"""LLM API client — OpenAI-compatible wrapper for 阿里百炼 DashScope."""

import asyncio
from collections.abc import AsyncIterator

from loguru import logger
from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Get or lazily-create the shared AsyncOpenAI client singleton."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    return _client


async def chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    max_retries: int = 3,
) -> str:
    """Send a chat completion request and return the full response text.

    Retries on transient errors with exponential backoff.
    """
    model = model or settings.llm_model_pro
    client = get_client()

    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or ""
            usage = response.usage
            if usage:
                logger.debug(
                    f"[LLM] model={model} tokens_in={usage.prompt_tokens} "
                    f"tokens_out={usage.completion_tokens} total={usage.total_tokens}"
                )
            return content
        except Exception as e:
            delay = 2 ** attempt
            logger.warning(f"[LLM] attempt {attempt+1}/{max_retries} failed: {e}, retry in {delay}s")
            if attempt == max_retries - 1:
                logger.error(f"[LLM] all {max_retries} attempts failed: {e}")
                raise
            await asyncio.sleep(delay)

    raise RuntimeError("unreachable")


async def chat_stream(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    max_retries: int = 3,
) -> AsyncIterator[str]:
    """Stream a chat completion, yielding tokens one by one.

    Retries on transient errors (note: partial stream cannot be retried
    without re-sending — caller should handle).
    """
    model = model or settings.llm_model_pro
    client = get_client()

    last_error = None
    for attempt in range(max_retries):
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
            return  # success — exit generator
        except Exception as e:
            last_error = e
            delay = 2 ** attempt
            logger.warning(f"[LLM-stream] attempt {attempt+1}/{max_retries} failed: {e}, retry in {delay}s")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)

    logger.error(f"[LLM-stream] all {max_retries} attempts failed: {last_error}")
    raise last_error  # type: ignore[misc]
