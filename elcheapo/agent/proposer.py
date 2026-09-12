"""Turning a message into a proposed expense, using Gemini.

This is the only component that talks to a model, and the only thing it can do
is return a Draft. It has no access to the workbook's write path.
"""

import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Callable
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types
from pydantic import BaseModel

from elcheapo.models import Draft
from elcheapo.retry import with_retries

INSTRUCTION = """You read short messages about personal spending and extract one expense.

Today is {today} and amounts are in {currency} unless the user names another currency.

Rules:
- `is_expense` is false if the message is not about money the user spent.
- Choose `category` from this list when one fits: {categories}
- Only invent a new category name when nothing on the list is a reasonable fit.
- `amount` is a plain decimal string, no currency symbol, e.g. "45.20".
- `date` is YYYY-MM-DD. Resolve "yesterday" and "last night" against today's date.
- `merchant` is the shop or place, empty if not mentioned.
- `note` is any extra detail worth keeping, usually empty.
"""


class ProposedExpense(BaseModel):
    """The model's structured reply."""

    is_expense: bool
    amount: str = ""
    category: str = ""
    merchant: str = ""
    note: str = ""
    date: str = ""


class GeminiProposer:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        categories_for: Callable[[int], list[str]],
        currency: str,
        timezone: str,
    ):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._categories_for = categories_for
        self._currency = currency
        self._zone = ZoneInfo(timezone)

    async def propose(self, *, text: str, chat_id: int) -> Draft | None:
        if not text.strip():
            return None

        categories = self._categories_for(chat_id)
        today = datetime.now(self._zone).date()

        async def call():
            return await self._client.aio.models.generate_content(
                model=self._model,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=INSTRUCTION.format(
                        today=today.isoformat(),
                        currency=self._currency,
                        categories=", ".join(categories) or "(none yet)",
                    ),
                    response_mime_type="application/json",
                    response_schema=ProposedExpense,
                    # We ask for a structured reply, never tool calls. Saying so
                    # explicitly silences the SDK's automatic-function-calling notice.
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )

        response = await with_retries(call)

        return self._to_draft(response.parsed, categories, today)

    def _to_draft(self, proposed, categories: list[str], today) -> Draft | None:
        if proposed is None or not proposed.is_expense:
            return None

        try:
            amount = Decimal(proposed.amount)
        except (InvalidOperation, TypeError):
            return None
        if amount <= 0:
            return None

        category = (proposed.category or "Other").strip()
        known = {name.casefold() for name in categories}

        return Draft(
            draft_id=secrets.token_urlsafe(4),
            amount=amount,
            category=category,
            # Decided here rather than trusted from the model, so the card's
            # "new category" flag always reflects the actual sheet.
            is_new_category=category.casefold() not in known,
            merchant=proposed.merchant or "",
            note=proposed.note or "",
            date=_parse_date(proposed.date, today),
            source="text",
        )


def _parse_date(value: str, fallback):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return fallback
