from datetime import date
from decimal import Decimal

import pytest

from elcheapo.channels.telegram.cards import draft_from_message, render_card
from elcheapo.channels.telegram.payload import PayloadError, encode_payload
from elcheapo.models import Draft


def a_draft(**overrides) -> Draft:
    fields = dict(
        draft_id="7k2m9x",
        amount=Decimal("45.20"),
        category="Groceries",
        is_new_category=False,
        merchant="Seoudi",
        note="",
        date=date(2026, 9, 12),
        source="image",
    )
    fields.update(overrides)
    return Draft(**fields)


def as_telegram_message(draft: Draft) -> dict:
    """Mimic how Telegram returns a sent card: plain text plus entities.

    Telegram parses the HTML we send and hands it back as text with a separate
    entity list, so the hidden link arrives as a `text_link` entity.
    """
    return {
        "message_id": 4242,
        "text": "🧾 45.20\nGroceries\nSeoudi · 12 Sep 2026​",
        "entities": [
            {
                "type": "text_link",
                "offset": 33,
                "length": 1,
                "url": encode_payload(draft),
            }
        ],
    }


def test_card_shows_the_amount_with_currency():
    card = render_card(a_draft(), currency="EGP")

    assert "45.20" in card.text
    assert "EGP" in card.text


def test_card_shows_category_and_merchant():
    card = render_card(a_draft(), currency="EGP")

    assert "Groceries" in card.text
    assert "Seoudi" in card.text


def test_accept_and_discard_buttons_carry_the_draft_id():
    card = render_card(a_draft(draft_id="abc123"), currency="EGP")

    callbacks = [
        button["callback_data"]
        for row in card.reply_markup["inline_keyboard"]
        for button in row
    ]

    assert "acc:abc123" in callbacks
    assert "dsc:abc123" in callbacks


def test_button_callback_data_stays_within_telegram_limit():
    card = render_card(a_draft(merchant="A" * 200, note="B" * 200), currency="EGP")

    for row in card.reply_markup["inline_keyboard"]:
        for button in row:
            assert len(button["callback_data"].encode("utf-8")) <= 64


def test_a_new_category_is_flagged_on_the_card():
    card = render_card(a_draft(is_new_category=True), currency="EGP")

    assert "new category" in card.text.lower()


def test_an_existing_category_is_not_flagged():
    card = render_card(a_draft(is_new_category=False), currency="EGP")

    assert "new category" not in card.text.lower()


def test_draft_is_recovered_from_the_sent_card():
    draft = a_draft()

    assert draft_from_message(as_telegram_message(draft)) == draft


def test_recovery_ignores_the_visible_text_entirely():
    draft = a_draft()
    message = as_telegram_message(draft)
    message["text"] = "completely different wording"

    assert draft_from_message(message) == draft


def test_recovery_fails_when_the_message_carries_no_link():
    with pytest.raises(PayloadError):
        draft_from_message({"message_id": 1, "text": "just a message"})
