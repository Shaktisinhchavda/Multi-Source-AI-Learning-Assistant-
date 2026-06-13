"""Shared Gemini API helpers."""

import asyncio
import email.utils
from datetime import datetime, timezone

import httpx


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def post_json_with_retries(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    payload: dict,
    settings,
    operation: str,
) -> dict:
    """POST JSON to Gemini with retry/backoff and sanitized errors."""
    max_retries = max(0, settings.gemini_max_retries)

    for attempt in range(max_retries + 1):
        response = await client.post(url, params=params, json=payload)

        if response.status_code not in RETRYABLE_STATUS_CODES:
            return _json_or_raise(response, operation)

        if attempt >= max_retries:
            _raise_gemini_error(response, operation)

        await asyncio.sleep(_retry_delay(response, attempt, settings))

    raise RuntimeError("Unreachable Gemini retry state.")


def _json_or_raise(response: httpx.Response, operation: str) -> dict:
    """Return JSON or raise a sanitized API error."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _raise_gemini_error(exc.response, operation)
    return response.json()


def _raise_gemini_error(response: httpx.Response, operation: str) -> None:
    """Raise an error that never includes the API key query string."""
    detail = extract_error_message(response)
    if response.status_code == 429:
        detail = (
            "Gemini rate limit reached. Please wait a bit and try again. "
            f"Details: {detail}"
        )
    raise ValueError(
        f"Gemini {operation} request failed with HTTP "
        f"{response.status_code}: {detail}"
    )


def extract_error_message(response: httpx.Response) -> str:
    """Return a concise API error without leaking query params/API keys."""
    try:
        data = response.json()
        return data.get("error", {}).get("message", response.reason_phrase)
    except ValueError:
        return response.reason_phrase


def _retry_delay(response: httpx.Response, attempt: int, settings) -> float:
    """Compute Retry-After-aware exponential backoff."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        parsed = _parse_retry_after(retry_after)
        if parsed is not None:
            return min(parsed, settings.gemini_retry_max_seconds)

    delay = settings.gemini_retry_base_seconds * (2 ** attempt)
    return min(delay, settings.gemini_retry_max_seconds)


def _parse_retry_after(value: str) -> float | None:
    """Parse Retry-After seconds or HTTP date."""
    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        retry_at = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)

    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
