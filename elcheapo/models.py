"""Core domain models shared by every channel."""

from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from typing import Literal

from dataclasses import dataclass

from pydantic import BaseModel, Field

Source = Literal["text", "image", "voice"]


def source_for(mime_type: str | None) -> Source:
    """Which kind of input an attachment counts as, for the sheet's audit column."""
    if not mime_type:
        return "text"
    if mime_type.startswith("audio/"):
        return "voice"
    if mime_type.startswith("image/") or mime_type == "application/pdf":
        return "image"
    return "text"


class Draft(BaseModel):
    """A proposed expense awaiting human confirmation.

    A draft has never touched the spreadsheet. Only `commit_expense`, reachable
    solely from an Accept callback, turns one into a row.
    """

    draft_id: str
    amount: Decimal
    category: str
    is_new_category: bool = False
    merchant: str = ""
    note: str = ""
    date: Date
    source: Source


CategoryScope = Literal["platform", "user"]


class Category(BaseModel):
    """A spending category.

    Platform categories ship with the product and are shared by everyone.
    User categories are added by one person, usually because the agent met a
    kind of spending nothing on the platform list covered.
    """

    name: str
    emoji: str = ""
    monthly_budget: Decimal | None = None
    scope: CategoryScope = "platform"


class Expense(BaseModel):
    """A confirmed expense. Exists only once a human has accepted a draft."""

    date: Date
    amount: Decimal
    category: str
    merchant: str = ""
    note: str = ""
    source: Source
    logged_at: datetime
    draft_id: str


@dataclass(frozen=True)
class Attachment:
    """Bytes from a chat message, handed to the model as-is.

    Gemini reads images and hears audio natively, so there is no OCR or
    transcription step between here and the proposal.
    """

    data: bytes
    mime_type: str


class ExpenseQuery(BaseModel):
    """Filters for reading a user's expenses.

    Every field is optional; an empty query means everything. This is the shape
    the agent fills in when it wants to look something up, so the field names
    are also what the model sees.
    """

    category: str | None = None
    merchant: str | None = None
    text: str | None = None
    date_from: Date | None = None
    date_to: Date | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    limit: int = Field(default=50, ge=1, le=500)

    def matches(self, expense: "Expense") -> bool:
        """Whether one expense satisfies every filter that was set."""
        if self.category and expense.category.casefold() != self.category.casefold():
            return False
        if self.merchant and self.merchant.casefold() not in expense.merchant.casefold():
            return False
        if self.text:
            needle = self.text.casefold()
            haystack = f"{expense.merchant} {expense.note}".casefold()
            if needle not in haystack:
                return False
        if self.date_from and expense.date < self.date_from:
            return False
        if self.date_to and expense.date > self.date_to:
            return False
        if self.min_amount is not None and expense.amount < self.min_amount:
            return False
        if self.max_amount is not None and expense.amount > self.max_amount:
            return False
        return True


@dataclass(frozen=True)
class AgentReply:
    """What one agent turn produced.

    A turn yields a proposed expense, or an answer to a question, or neither.
    Keeping both here means a read tool's result reaches the user instead of
    being discarded because it was not a Draft.
    """

    draft: "Draft | None" = None
    text: str = ""
    document: "Document | None" = None


@dataclass(frozen=True)
class Document:
    """A file the agent produced, on its way to the user."""

    filename: str
    data: bytes
    caption: str = ""


