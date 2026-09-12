"""Turns Telegram updates into cards, and accepted cards into expenses."""

import logging
from datetime import datetime, timezone
from typing import Callable, Protocol

from elcheapo.channels.telegram.cards import (
    draft_from_message,
    render_card,
    render_confirmed,
    render_discarded,
    render_error,
)
from elcheapo.channels.telegram.media import attachment_in
from elcheapo.channels.telegram.payload import PayloadError
from elcheapo.commit import commit_expense
from elcheapo.models import AgentReply, Attachment
from elcheapo.repositories import Repositories
from elcheapo.updates import chat_id_of

log = logging.getLogger(__name__)

ACCEPT = "acc"
DISCARD = "dsc"

COULD_NOT_READ = (
    "I couldn't read an expense in that. Try something like "
    "'lunch 18.50 at Tim Hortons', or send a photo of the receipt."
)
STALE_CARD = "This card is too old to act on. Send the expense again."
MODEL_UNAVAILABLE = (
    "I couldn't reach the model just now. Send that again in a moment."
)
COMMIT_FAILED = "I couldn't save that to the sheet. Tap Accept again to retry."
DOWNLOAD_FAILED = "I couldn't download that file. Try sending it again."
RESET_DONE = (
    "Fresh start. I've forgotten what we were talking about -- "
    "your logged expenses are untouched."
)

RESET = "/reset"

# Telegram truncates anything longer, so the tail would be lost silently.
MAX_CAPTION = 1024


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

    async def send_document(
        self, chat_id: int, filename: str, data: bytes, caption: str = ""
    ) -> None: ...

    async def download(self, file_id: str) -> bytes: ...


class Proposer(Protocol):
    async def propose(
        self, *, text: str, chat_id: int, attachment: Attachment | None = None
    ) -> AgentReply: ...

    def reset(self, chat_id: int) -> None: ...


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
        # A photo or voice note carries its words in `caption`, not `text`.
        text = message.get("text") or message.get("caption") or ""
        reference = attachment_in(message)

        if _is_reset(text):
            # Handled here, never sent to the model: it costs nothing and the
            # user gets the same answer every time.
            self._proposer.reset(chat_id)
            await self._bot.send_message(chat_id, RESET_DONE)
            return

        if reference is None and not text.strip():
            # A sticker, a location, a poll. Nothing to read, so nothing is
            # spent asking the model about it.
            await self._bot.send_message(chat_id, COULD_NOT_READ)
            return

        attachment = None
        if reference is not None:
            file_id, mime_type = reference
            try:
                data = await self._bot.download(file_id)
            except Exception:  # noqa: BLE001
                log.exception("download of %s failed", file_id)
                await self._bot.send_message(chat_id, DOWNLOAD_FAILED)
                return
            attachment = Attachment(data=data, mime_type=mime_type)

        try:
            reply = await self._proposer.propose(
                text=text, chat_id=chat_id, attachment=attachment
            )
        except Exception:  # noqa: BLE001 - the user gets an answer either way
            log.exception("proposal failed for chat %s", chat_id)
            await self._bot.send_message(chat_id, MODEL_UNAVAILABLE)
            return

        if reply.document is not None:
            # The agent's words ride along as the caption rather than arriving
            # as a separate message above the file.
            await self._bot.send_document(
                chat_id,
                reply.document.filename,
                reply.document.data,
                reply.text[:MAX_CAPTION],
            )

        if reply.draft is not None:
            card = render_card(reply.draft, currency=self._currency)
            await self._bot.send_message(chat_id, card.text, card.reply_markup)
            return

        if reply.document is not None:
            return

        # No expense, but the agent may have answered a question -- a query
        # tool's result arrives here as prose.
        await self._bot.send_message(chat_id, reply.text or COULD_NOT_READ)

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
            try:
                commit_expense(draft, repo, now=self._clock())
            except Exception:  # noqa: BLE001
                # The card keeps its buttons, so Accept can simply be tapped
                # again -- the draft_id guard makes that retry safe.
                log.exception("commit failed for draft %s", draft.draft_id)
                await self._bot.send_message(chat_id, COMMIT_FAILED)
                return
            card = render_confirmed(draft, currency=self._currency)
        else:
            card = render_error(STALE_CARD)

        await self._replace_card(chat_id, message_id, card)

    async def _replace_card(self, chat_id: int, message_id: int, card) -> None:
        await self._bot.edit_message_text(
            chat_id, message_id, card.text, card.reply_markup
        )


def _is_reset(text: str) -> bool:
    """Whether this message is the /reset command.

    Telegram rewrites commands as /reset@botname in groups, so the bot
    suffix is stripped before comparing.
    """
    command, _, _ = text.strip().partition(" ")
    command, _, _ = command.partition("@")
    return command.casefold() == RESET
