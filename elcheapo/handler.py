"""Turns Telegram updates into cards, and accepted cards into expenses."""

from datetime import datetime, timezone
from typing import Callable, Protocol

from elcheapo.channels.telegram.cards import (
    draft_from_message,
    render_card,
    render_confirmed,
    render_discarded,
    render_error,
)
from elcheapo.channels.telegram.payload import PayloadError
from elcheapo.commit import commit_expense
from elcheapo.models import Draft
from elcheapo.repositories import Repositories
from elcheapo.updates import chat_id_of

ACCEPT = "acc"
DISCARD = "dsc"

COULD_NOT_READ = (
    "I couldn't read an expense in that. Try something like "
    "'lunch 120 at Zooba', or send a photo of the receipt."
)
STALE_CARD = "This card is too old to act on. Send the expense again."


class Bot(Protocol):
    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> dict: ...

    async def edit_message_text(
        self, chat_id: int, message_id: int, text: str, reply_markup: dict | None = None
    ) -> None: ...

    async def answer_callback_query(
        self, callback_query_id: str, text: str = ""
    ) -> None: ...


class Proposer(Protocol):
    async def propose(self, *, text: str, chat_id: int) -> Draft | None: ...


class ExpenseHandler:
    def __init__(
        self,
        *,
        bot: Bot,
        repositories: Repositories,
        proposer: Proposer,
        currency: str,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self._bot = bot
        self._repositories = repositories
        self._proposer = proposer
        self._currency = currency
        self._clock = clock

    async def handle(self, update: dict) -> None:
        if "callback_query" in update:
            await self._handle_callback(update["callback_query"])
        elif "message" in update:
            await self._handle_message(update["message"])

    async def _handle_message(self, message: dict) -> None:
        chat_id = message["chat"]["id"]
        text = message.get("text", "")

        draft = await self._proposer.propose(text=text, chat_id=chat_id)
        if draft is None:
            await self._bot.send_message(chat_id, COULD_NOT_READ)
            return

        card = render_card(draft, currency=self._currency)
        await self._bot.send_message(chat_id, card.text, card.reply_markup)

    async def _handle_callback(self, callback: dict) -> None:
        # Acknowledged first so the client spinner clears even if the work below
        # fails and the update is retried.
        await self._bot.answer_callback_query(callback["id"])

        message = callback.get("message") or {}
        chat_id = chat_id_of({"callback_query": callback})
        message_id = message.get("message_id")

        try:
            draft = draft_from_message(message)
        except PayloadError:
            await self._replace_card(chat_id, message_id, render_error(STALE_CARD))
            return

        action, _, _ = (callback.get("data") or "").partition(":")

        if action == DISCARD:
            card = render_discarded(draft, currency=self._currency)
        elif action == ACCEPT:
            repo = self._repositories.for_chat(chat_id)
            commit_expense(draft, repo, now=self._clock())
            card = render_confirmed(draft, currency=self._currency)
        else:
            card = render_error(STALE_CARD)

        await self._replace_card(chat_id, message_id, card)

    async def _replace_card(self, chat_id: int, message_id: int, card) -> None:
        await self._bot.edit_message_text(
            chat_id, message_id, card.text, card.reply_markup
        )
