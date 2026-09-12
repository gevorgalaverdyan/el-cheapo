from datetime import date, datetime, timezone
from decimal import Decimal

from elcheapo.channels.telegram.cards import render_card
from elcheapo.handler import ExpenseHandler
from elcheapo.models import Draft
from elcheapo.repositories import SingleUserRepositories
from tests.fakes import FakeSheetsRepository, FakeTelegramBot, StubProposer

CHAT = 111
NOW = datetime(2026, 9, 12, 18, 4, 11, tzinfo=timezone.utc)


def a_draft(**overrides) -> Draft:
    fields = dict(
        draft_id="7k2m9x",
        amount=Decimal("45.20"),
        category="Groceries",
        is_new_category=False,
        merchant="Seoudi",
        note="",
        date=date(2026, 9, 12),
        source="text",
    )
    fields.update(overrides)
    return Draft(**fields)


def make_handler(proposal: Draft | None = None, categories=("Groceries",)):
    repo = FakeSheetsRepository(categories=list(categories))
    bot = FakeTelegramBot()
    handler = ExpenseHandler(
        bot=bot,
        repositories=SingleUserRepositories(repo),
        proposer=StubProposer(proposal),
        currency="EGP",
        clock=lambda: NOW,
    )
    return handler, bot, repo


def a_text_update(text: str = "lunch 45.20 seoudi") -> dict:
    return {
        "update_id": 1,
        "message": {"message_id": 9, "chat": {"id": CHAT}, "text": text},
    }


def a_callback_update(action: str, draft: Draft) -> dict:
    card = render_card(draft, currency="EGP")
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb1",
            "data": f"{action}:{draft.draft_id}",
            "message": {
                "message_id": 42,
                "chat": {"id": CHAT},
                "text": "rendered card",
                "entities": [
                    {
                        "type": "text_link",
                        "offset": 0,
                        "length": 1,
                        "url": _hidden_url(card.text),
                    }
                ],
            },
        },
    }


def _hidden_url(card_text: str) -> str:
    start = card_text.rindex('href="') + len('href="')
    return card_text[start : card_text.index('"', start)]


async def test_a_text_message_produces_a_card():
    handler, bot, repo = make_handler(proposal=a_draft())

    await handler.handle(a_text_update())

    assert len(bot.sent) == 1
    assert "Groceries" in bot.sent[0]["text"]
    assert repo.expenses == []


async def test_the_card_offers_accept_and_discard():
    handler, bot, _ = make_handler(proposal=a_draft())

    await handler.handle(a_text_update())

    callbacks = [
        button["callback_data"]
        for row in bot.sent[0]["reply_markup"]["inline_keyboard"]
        for button in row
    ]
    assert callbacks == ["acc:7k2m9x", "dsc:7k2m9x"]


async def test_an_uninterpretable_message_gets_a_reply_not_a_card():
    handler, bot, repo = make_handler(proposal=None)

    await handler.handle(a_text_update("mmm"))

    assert len(bot.sent) == 1
    assert bot.sent[0]["reply_markup"] is None
    assert repo.expenses == []


async def test_accepting_writes_the_expense():
    draft = a_draft()
    handler, bot, repo = make_handler()

    await handler.handle(a_callback_update("acc", draft))

    assert [(e.amount, e.category) for e in repo.expenses] == [
        (Decimal("45.20"), "Groceries")
    ]


async def test_accepting_edits_the_card_and_removes_the_buttons():
    handler, bot, _ = make_handler()

    await handler.handle(a_callback_update("acc", a_draft()))

    assert len(bot.edited) == 1
    assert bot.edited[0]["message_id"] == 42
    assert bot.edited[0]["reply_markup"] is None


async def test_every_callback_is_acknowledged():
    handler, bot, _ = make_handler()

    await handler.handle(a_callback_update("acc", a_draft()))

    assert bot.answered == ["cb1"]


async def test_discarding_writes_nothing():
    handler, bot, repo = make_handler()

    await handler.handle(a_callback_update("dsc", a_draft()))

    assert repo.expenses == []
    assert len(bot.edited) == 1
    assert bot.edited[0]["reply_markup"] is None


async def test_accepting_the_same_card_twice_writes_one_row():
    draft = a_draft()
    handler, bot, repo = make_handler()

    await handler.handle(a_callback_update("acc", draft))
    await handler.handle(a_callback_update("acc", draft))

    assert len(repo.expenses) == 1
    assert bot.answered == ["cb1", "cb1"]


async def test_a_card_with_an_unreadable_payload_reports_an_error():
    handler, bot, repo = make_handler()
    update = a_callback_update("acc", a_draft())
    update["callback_query"]["message"]["entities"] = []

    await handler.handle(update)

    assert repo.expenses == []
    assert bot.answered == ["cb1"]
    assert len(bot.edited) == 1
