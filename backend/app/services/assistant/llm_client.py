"""Thin wrapper around Gemini, used ONLY to phrase the grounded prompt (reasoning_prompt.py) in plain
language. All facts come from the prompt. The key is read from the environment at call time."""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)
MODEL = "gemini-2.0-flash"
_client = None


def _get_client():  # noqa: ANN202 - returns a google.genai.Client
    global _client
    if _client is None:
        from google import genai  # optional dependency: pip install -e ".[llm]"

        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=key)
    return _client


def generate_explanation(prompt: str) -> str:
    try:
        response = _get_client().models.generate_content(model=MODEL, contents=prompt)
        return (response.text or "").strip()
    except Exception:  # never surface provider error text (could echo request details) to users
        log.exception("LLM explanation failed")
        return "(AI explanation unavailable)"
