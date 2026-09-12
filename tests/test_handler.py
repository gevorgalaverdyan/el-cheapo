from datetime import date, datetime, timezone
from decimal import Decimal

from elcheapo.channels.telegram.cards import render_card
from elcheapo.handler import ExpenseHandler
from elcheapo.models import Draft
from elcheapo.repositories import SingleUserRepositories
from tests.fakes import FakeExpenseRepository, FakeTelegramBot, StubProposer

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


def make_handler(proposal: Draft | None = None, categories=("Groceries",), error=None, reply=""):
    repo = FakeExpenseRepository(categories=list(categories))
    bot = FakeTelegramBot()
    handler = ExpenseHandler(
        bot=bot,
        repositories=SingleUserRepositories(repo),
        proposer=StubProposer(proposal, error=error, reply=reply),
        currency="CAD",
        clock=lambda: NOW,
    )
    return handler, bot, repo


def make_handler_with_proposer(**kwargs):
    handler, bot, repo = make_handler(**kwargs)
    return handler, bot, repo, handler._proposer


def a_text_update(text: str = "lunch 45.20 seoudi") -> dict:
    return {
        "update_id": 1,
        "message": {"message_id": 9, "chat": {"id": CHAT}, "text": text},
    }


def a_callback_update(action: str, draft: Draft) -> dict:
    card = render_card(draft, currency="CAD")
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


async def test_a_model_outage_gets_an_apology_not_silence():
    handler, bot, repo = make_handler(error=RuntimeError("503 UNAVAILABLE"))

    await handler.handle(a_text_update())

    assert len(bot.sent) == 1
    assert bot.sent[0]["reply_markup"] is None
    assert repo.expenses == []


async def test_a_failed_commit_tells_the_user_to_try_again():
    handler, bot, repo = make_handler()
    repo.append_failures = 1

    await handler.handle(a_callback_update("acc", a_draft()))

    assert repo.expenses == []
    # The card keeps its buttons so Accept can simply be tapped again.
    assert bot.sent and "again" in bot.sent[-1]["text"].lower()


def a_photo_update(caption: str | None = None) -> dict:
    message = {
        "message_id": 9,
        "chat": {"id": CHAT},
        "photo": [
            {"file_id": "thumb", "width": 90},
            {"file_id": "full", "width": 1280},
        ],
    }
    if caption is not None:
        message["caption"] = caption
    return {"update_id": 3, "message": message}


def a_voice_update() -> dict:
    return {
        "update_id": 4,
        "message": {
            "message_id": 9,
            "chat": {"id": CHAT},
            "voice": {"file_id": "voice1", "mime_type": "audio/ogg", "duration": 4},
        },
    }


async def test_a_receipt_photo_is_downloaded_at_full_size():
    handler, bot, repo, proposer = make_handler_with_proposer(proposal=a_draft())

    await handler.handle(a_photo_update())

    assert bot.downloaded == ["full"]
    assert proposer.attachments[0].mime_type == "image/jpeg"
    assert proposer.attachments[0].data == b"fake-bytes"


async def test_a_photo_caption_is_passed_along_as_text():
    handler, bot, repo, proposer = make_handler_with_proposer(proposal=a_draft())

    await handler.handle(a_photo_update(caption="dinner with sam"))

    assert proposer.seen == ["dinner with sam"]


async def test_a_photo_produces_a_card():
    handler, bot, _ = make_handler(proposal=a_draft())

    await handler.handle(a_photo_update())

    assert len(bot.sent) == 1
    assert bot.sent[0]["reply_markup"] is not None


async def test_a_voice_note_is_downloaded_and_sent_as_audio():
    handler, bot, repo, proposer = make_handler_with_proposer(proposal=a_draft())

    await handler.handle(a_voice_update())

    assert bot.downloaded == ["voice1"]
    assert proposer.attachments[0].mime_type == "audio/ogg"


async def test_a_failed_download_is_reported_not_swallowed():
    handler, bot, repo, proposer = make_handler_with_proposer(proposal=a_draft())
    bot.download_error = RuntimeError("file too big")

    await handler.handle(a_photo_update())

    assert len(bot.sent) == 1
    assert bot.sent[0]["reply_markup"] is None
    assert proposer.attachments == []


async def test_a_message_with_nothing_readable_never_reaches_the_model():
    handler, bot, repo, proposer = make_handler_with_proposer(proposal=a_draft())

    await handler.handle({"update_id": 5, "message": {"message_id": 9, "chat": {"id": CHAT}, "sticker": {"file_id": "s1"}}})

    assert proposer.seen == []
    assert len(bot.sent) == 1


async def test_an_answer_from_the_agent_is_sent_to_the_user():
    handler, bot, repo = make_handler(reply="You have spent 88.75 on Dining this month.")

    await handler.handle(a_text_update("how much on dining?"))

    assert len(bot.sent) == 1
    assert bot.sent[0]["text"] == "You have spent 88.75 on Dining this month."
    assert bot.sent[0]["reply_markup"] is None


async def test_a_card_wins_over_any_accompanying_chatter():
    handler, bot, repo = make_handler(proposal=a_draft(), reply="Here you go.")

    await handler.handle(a_text_update())

    assert len(bot.sent) == 1
    assert bot.sent[0]["reply_markup"] is not None


async def test_silence_from_the_agent_still_gets_a_reply():
    handler, bot, repo = make_handler(proposal=None, reply="")

    await handler.handle(a_text_update("mmm"))

    assert len(bot.sent) == 1
    assert "couldn't read" in bot.sent[0]["text"]
