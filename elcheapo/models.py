"""Core domain models shared by every channel."""

from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["text", "image", "voice"]


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


class Category(BaseModel):
    """A spending category. Seeded by us, extendable by the agent."""

    name: str
    emoji: str = ""
    monthly_budget: Decimal | None = None
    created_by: Literal["seed", "agent"] = "seed"


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
