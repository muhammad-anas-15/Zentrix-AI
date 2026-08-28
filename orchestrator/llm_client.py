"""
Thin wrapper around Gemini API — used ONLY for final plain-language
phrasing. All facts come from the grounded prompt (reasoning_prompt.py);
the LLM's job is just to phrase them simply, not to invent content.
"""
import os
from google import genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_client = None


def _get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set in environment")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def generate_explanation(prompt: str) -> str:
    try:
        client = _get_client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        return f"(AI explanation unavailable: {e})"


if __name__ == "__main__":
    test_prompt = "Explain in one sentence why the sky is blue, simply."
    print(generate_explanation(test_prompt))