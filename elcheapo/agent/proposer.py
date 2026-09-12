"""Running the ADK agent for one chat turn.

Each Telegram chat gets an ADK session, so the agent sees the last few turns
and a correction like "make it 45" lands as a revision rather than a fresh
guess. Sessions are conversational convenience only -- every durable fact
lives in the card payload or the database.
"""

import logging
import os
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from elcheapo.agent.agent import build_agent
from elcheapo.agent.tools import PROPOSE_EXPENSE
from elcheapo.models import AgentReply, Attachment, Draft, source_for
from elcheapo.repositories import Repositories
from elcheapo.retry import with_retries

log = logging.getLogger(__name__)

APP_NAME = "elcheapo"
NO_WORDS = "Extract the expense from this receipt or recording."


class AgentProposer:
    """Turns a chat message into a proposed expense, via the ADK agent."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        repositories: Repositories,
        currency: str,
        timezone: str,
    ):
        # ADK reads credentials from the environment rather than taking them as
        # arguments, so an API key has to be published there before the agent runs.
        if api_key:
            os.environ.setdefault("GOOGLE_API_KEY", api_key)
            os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

        self._model = model
        self._repositories = repositories
        self._currency = currency
        self._zone = ZoneInfo(timezone)
        self._sessions = InMemorySessionService()

    async def propose(
        self, *, text: str, chat_id: int, attachment: Attachment | None = None
    ) -> AgentReply:
        if not text.strip() and attachment is None:
            return AgentReply()

        repository = self._repositories.for_chat(chat_id)
        categories = [category.name for category in repository.categories()]
        today = datetime.now(self._zone).date()

        runner = Runner(
            agent=build_agent(
                model=self._model,
                today=today.isoformat(),
                currency=self._currency,
                categories=categories,
                repository=repository,
            ),
            app_name=APP_NAME,
            session_service=self._sessions,
        )

        user_id = str(chat_id)
        session_id = f"chat-{chat_id}"
        await self._ensure_session(user_id, session_id)

        parts = []
        if attachment is not None:
            # Read by the model directly -- no OCR service and no transcription
            # service in between.
            parts.append(
                types.Part.from_bytes(
                    data=attachment.data, mime_type=attachment.mime_type
                )
            )
        parts.append(types.Part.from_text(text=text.strip() or NO_WORDS))

        async def run() -> tuple[dict | None, str]:
            proposal = None
            answer = ""
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(role="user", parts=parts),
            ):
                proposal = _proposal_in(event) or proposal
                answer = _text_in(event) or answer
            return proposal, answer

        proposal, answer = await with_retries(run)

        return AgentReply(
            draft=self._to_draft(proposal, categories, today, attachment),
            text=answer,
        )

    async def _ensure_session(self, user_id: str, session_id: str) -> None:
        existing = await self._sessions.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing is None:
            await self._sessions.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )

    def _to_draft(
        self,
        proposal: dict | None,
        categories: list[str],
        today,
        attachment: Attachment | None,
    ) -> Draft | None:
        if not proposal:
            return None

        try:
            amount = Decimal(str(proposal.get("amount", "")).strip())
        except (InvalidOperation, TypeError):
            log.warning("unparseable amount from agent: %r", proposal.get("amount"))
            return None
        if amount <= 0:
            return None

        category = (proposal.get("category") or "Other").strip()
        known = {name.casefold() for name in categories}

        return Draft(
            draft_id=secrets.token_urlsafe(4),
            amount=amount,
            category=category,
            # Decided here, not trusted from the model, so the card's "new
            # category" flag always reflects what is actually stored.
            is_new_category=category.casefold() not in known,
            merchant=(proposal.get("merchant") or "").strip(),
            note=(proposal.get("note") or "").strip(),
            date=_parse_date(proposal.get("date"), today),
            source=source_for(attachment.mime_type if attachment else None),
        )


def _proposal_in(event) -> dict | None:
    """The arguments of a propose_expense call, if this event carries one."""
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        call = getattr(part, "function_call", None)
        if call is not None and call.name == PROPOSE_EXPENSE:
            return dict(call.args or {})
    return None


def _text_in(event) -> str:
    """Any prose the agent produced in this event."""
    content = getattr(event, "content", None)
    pieces = [
        part.text.strip()
        for part in (getattr(content, "parts", None) or [])
        if getattr(part, "text", None) and part.text.strip()
    ]
    return " ".join(pieces)


def _parse_date(value, fallback):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return fallback
