"""Render drafts as Telegram cards, and recover drafts from sent cards."""

from dataclasses import dataclass
from html import escape

from elcheapo.channels.telegram.payload import PayloadError, decode_payload, encode_payload
from elcheapo.models import Draft

ZERO_WIDTH_SPACE = "​"


@dataclass(frozen=True)
class Card:
    """A renderable Telegram message: HTML body plus an inline keyboard."""

    text: str
    reply_markup: dict | None


def render_card(draft: Draft, *, currency: str) -> Card:
    """Render a pending draft, with the payload hidden in a zero-width link."""
    category_line = (
        f"✨ {escape(draft.category)} — new category"
        if draft.is_new_category
        else f"🛒 {escape(draft.category)}"
    )

    details = [part for part in (escape(draft.merchant), _format_date(draft.date)) if part]
    lines = [
        f"🧾 <b>{draft.amount} {escape(currency)}</b>",
        category_line,
        " · ".join(details),
    ]
    if draft.note:
        lines.append(f"<i>{escape(draft.note)}</i>")

    hidden = f'<a href="{escape(encode_payload(draft), quote=True)}">{ZERO_WIDTH_SPACE}</a>'

    return Card(
        text="\n".join(lines) + hidden,
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": "✓ Accept", "callback_data": f"acc:{draft.draft_id}"},
                    {"text": "✗ Discard", "callback_data": f"dsc:{draft.draft_id}"},
                ]
            ]
        },
    )


def draft_from_message(message: dict) -> Draft:
    """Recover the draft carried by a card message.

    Reads the link entity only. The visible text is never parsed, so restyling
    the card cannot break cards that are already out there.
    """
    entities = (message.get("entities") or []) + (message.get("caption_entities") or [])

    for entity in entities:
        if entity.get("type") != "text_link" or "url" not in entity:
            continue
        try:
            return decode_payload(entity["url"])
        except PayloadError:
            continue

    raise PayloadError("message carries no decodable draft payload")


def _format_date(value) -> str:
    return f"{value.day} {value.strftime('%b')} {value.year}"


def render_confirmed(draft: Draft, *, currency: str) -> Card:
    """A committed draft. No payload: this card can no longer be acted on."""
    lines = [
        f"✅ <b>{draft.amount} {escape(currency)}</b>",
        f"🛒 {escape(draft.category)}",
        " · ".join(
            part for part in (escape(draft.merchant), _format_date(draft.date)) if part
        ),
        "<i>logged</i>",
    ]
    return Card(text="\n".join(lines), reply_markup=None)


def render_discarded(draft: Draft, *, currency: str) -> Card:
    return Card(
        text=f"🗑 <s>{draft.amount} {escape(currency)} · {escape(draft.category)}</s>\n<i>discarded</i>",
        reply_markup=None,
    )


def render_error(message: str) -> Card:
    return Card(text=f"⚠️ {escape(message)}", reply_markup=None)
