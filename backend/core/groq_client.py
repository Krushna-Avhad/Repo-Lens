"""
Centralised Groq client used by all agents.
Safe to import even before `pip install groq` — errors are deferred to call time.
"""
from __future__ import annotations
import json
import re
from typing import Any, AsyncGenerator

from core.config import settings

# ── Lazy-load the groq SDK ─────────────────────────────────────────────────
_groq = None

def _get_client():
    global _groq
    if _groq is not None:
        return _groq
    if not settings.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to backend/.env and restart."
        )
    try:
        from groq import AsyncGroq
        _groq = AsyncGroq(api_key=settings.GROQ_API_KEY)
        return _groq
    except ImportError:
        raise RuntimeError(
            "groq package not installed. Run: pip install groq"
        )


# ── Core helpers ────────────────────────────────────────────────────────────

async def chat(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    """Single-turn chat completion. Returns the full response string."""
    client = _get_client()
    kwargs: dict[str, Any] = dict(
        model=model or settings.GROQ_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


async def stream_chat(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """Streaming chat completion. Yields text chunks."""
    client = _get_client()
    resp = await client.chat.completions.create(
        model=model or settings.GROQ_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    async for chunk in resp:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


async def fast_chat(messages: list[dict], max_tokens: int = 512) -> str:
    """Uses the smaller/faster model for lightweight tasks."""
    return await chat(
        messages,
        model=settings.GROQ_FAST_MODEL,
        max_tokens=max_tokens,
    )


def extract_json(text: str) -> Any:
    """
    Extract a JSON object/array from an LLM response that may contain
    surrounding prose or markdown code fences.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(
        r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL
    )
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    brace = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON found in LLM response:\n{text[:300]}")
