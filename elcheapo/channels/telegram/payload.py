"""Encode a draft into the card message, and read it back.

The draft rides inside the card as the URL of a zero-width link. Telegram
returns the full message with its entities on a callback, so the draft comes
back from the entity URL -- never parsed from the visible text. That separation
is the point: the card's layout can change freely without breaking cards that
were already sent.
"""

import base64
import json
from datetime import date as Date
from decimal import Decimal

from elcheapo.models import Draft

SCHEMA_VERSION = "d1"
_BASE_URL = "https://t.me/"


class PayloadError(ValueError):
    """The payload is absent, malformed, or of an unrecognised schema version."""


def encode_payload(draft: Draft) -> str:
    """Return the URL carrying `draft`, for use as the card's hidden link."""
    compact = {
        "i": draft.draft_id,
        "a": str(draft.amount),
        "c": draft.category,
        "n": draft.is_new_category,
        "m": draft.merchant,
        "t": draft.note,
        "d": draft.date.isoformat(),
        "s": draft.source,
    }
    raw = json.dumps(compact, separators=(",", ":"), ensure_ascii=False)
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{_BASE_URL}#{SCHEMA_VERSION}.{encoded}"


def decode_payload(url: str) -> Draft:
    """Recover the draft from a card's hidden link URL."""
    _, separator, fragment = url.partition("#")
    if not separator:
        raise PayloadError("no payload fragment in URL")

    version, separator, encoded = fragment.partition(".")
    if not separator:
        raise PayloadError("malformed payload fragment")
    if version != SCHEMA_VERSION:
        raise PayloadError(
            f"payload schema {version!r} is not supported (expected {SCHEMA_VERSION!r})"
        )

    padding = "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        compact = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PayloadError("payload is not decodable") from exc

    try:
        return Draft(
            draft_id=compact["i"],
            amount=Decimal(compact["a"]),
            category=compact["c"],
            is_new_category=compact["n"],
            merchant=compact["m"],
            note=compact["t"],
            date=Date.fromisoformat(compact["d"]),
            source=compact["s"],
        )
    except (KeyError, ValueError, ArithmeticError) as exc:
        raise PayloadError("payload fields are invalid") from exc
