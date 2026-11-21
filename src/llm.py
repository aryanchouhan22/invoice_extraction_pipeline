import time

from google import genai
from google.genai import errors, types

from . import config
from .prompts import SYSTEM_PROMPT


class LLMError(Exception):
    """The model could not be reached or refused the request."""


RETRYABLE = {429, 500, 502, 503, 504}
NETWORK_ERROR_NAMES = {"TimeoutException", "TransportError", "TimeoutError", "ConnectionError"}
_client = None


def _is_network_error(e):
    # Match by class name: the SDK may use httpx or a renamed copy of it (httpx2)
    return any(c.__name__ in NETWORK_ERROR_NAMES for c in type(e).__mro__)


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
        except Exception as e:
            if not _is_network_error(e):
                raise LLMError(f"unexpected error: {type(e).__name__}: {str(e)[:200]}") from e
            last = f"network or timeout error: {type(e).__name__}"

        if attempt < config.MAX_API_RETRIES:
            time.sleep(min(5 * 2 ** attempt, 60))

    raise LLMError(f"gave up after {config.MAX_API_RETRIES + 1} tries: {last}")