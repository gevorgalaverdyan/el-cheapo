"""Retrying calls that failed for reasons that tend to pass.

Gemini returns 503 UNAVAILABLE under load often enough that a single attempt
makes the bot look broken when it isn't.
"""

import asyncio
import re
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

TRANSIENT_CODES = {408, 429, 500, 502, 503, 504}
TRANSIENT_MARKERS = (
    "UNAVAILABLE",
    "RESOURCE_EXHAUSTED",
    "DEADLINE_EXCEEDED",
    "INTERNAL",
)

# Longer than this and waiting is worse than telling the user to try again.
MAX_SUGGESTED_DELAY = 65.0

_DELAY_PATTERNS = (
    re.compile(r"retryDelay['\"]?\s*:\s*['\"]?([\d.]+)s"),
    re.compile(r"retry in ([\d.]+)\s*s", re.IGNORECASE),
)


def retry_delay_for(error: BaseException) -> float | None:
    """How long the server asked us to wait, if it said.

    Rate limit responses carry a concrete delay. Guessing with exponential
    backoff when the server has told you the answer just wastes attempts --
    a 0.5s retry against a 58s quota window always fails.
    """
    text = str(error)
    for pattern in _DELAY_PATTERNS:
        match = pattern.search(text)
        if match:
            return min(float(match.group(1)), MAX_SUGGESTED_DELAY)
    return None


def is_transient(error: BaseException) -> bool:
    """Whether retrying this error has any chance of a different outcome."""
    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code in TRANSIENT_CODES

    text = str(error)
    return any(marker in text for marker in TRANSIENT_MARKERS)


async def with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run `operation`, retrying transient failures with exponential backoff.

    Permanent failures -- a bad request, a bad key -- are raised immediately
    rather than retried three times to the same conclusion.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as error:
            if attempt == attempts or not is_transient(error):
                raise
            suggested = retry_delay_for(error)
            await sleep(
                suggested if suggested is not None else base_delay * 2 ** (attempt - 1)
            )

    raise AssertionError("unreachable")
