import time

import httpx
from google import genai
from google.genai import errors, types

from . import config
from .prompts import SYSTEM_PROMPT


class LLMError(Exception):
    """The model could not be reached or refused the request."""


RETRYABLE = {429, 500, 502, 503, 504}
_client = None


def _get_client():
    global _client
    if _client is None:
        if not config.API_KEY:
            raise LLMError("GEMINI_API_KEY is not set (copy .env.example to .env and add your key)")
        _client = genai.Client(
            api_key=config.API_KEY,
            http_options=types.HttpOptions(timeout=int(config.TIMEOUT_S * 1000)),  # milliseconds
        )
    return _client


def generate(data: bytes, mime: str, user_text: str):
    """Send the file plus prompt to the model. Returns (text, tokens_in, tokens_out)."""
    # No temperature set on purpose: Gemini 3 models are meant to run at their default.
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
    )
    contents = [types.Part.from_bytes(data=data, mime_type=mime), user_text]

    last = "unknown error"
    for attempt in range(config.MAX_API_RETRIES + 1):
        try:
            resp = _get_client().models.generate_content(
                model=config.MODEL, contents=contents, config=cfg
            )
            u = resp.usage_metadata
            tin = (u.prompt_token_count or 0) if u else 0
            # thinking tokens are billed as output
            tout = ((u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)) if u else 0
            return resp.text or "", tin, tout
        except errors.APIError as e:
            code = getattr(e, "code", None)
            last = f"API error {code}: {str(e)[:200]}"
            if code not in RETRYABLE:
                raise LLMError(last) from e  # 400/401/402/403/404: retrying cannot help
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = f"network or timeout error: {type(e).__name__}"

        if attempt < config.MAX_API_RETRIES:
            time.sleep(min(5 * 2 ** attempt, 60))

    raise LLMError(f"gave up after {config.MAX_API_RETRIES + 1} tries: {last}")