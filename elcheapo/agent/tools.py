"""Tools the agent may call.

Two shapes live here. `propose_expense` announces an intention and writes
nothing -- the handler turns it into a card a human accepts. The read tools
close over one user's repository, so a tool call can only ever reach the data
of the chat it was built for.

Docstrings and type hints are not decoration: ADK derives the function
declarations the model sees from them, so they are part of the prompt.
"""

from datetime import date as Date
from decimal import Decimal, InvalidOperation
from typing import Callable

from elcheapo.models import Expense, ExpenseQuery
from elcheapo.store.repository import ExpenseRepository

PROPOSE_EXPENSE = "propose_expense"
LIST_CATEGORIES = "list_categories"
QUERY_EXPENSES = "query_expenses"


def propose_expense(
    amount: str,
    category: str,
    merchant: str,
    note: str,
    date: str,
) -> dict:
    """Propose an expense for the user to confirm. Does not save anything.

    Call this whenever the user describes money they spent, including when they
    are correcting an expense you proposed a moment ago -- call it again with
    the corrected values rather than apologising.

    Args:
        amount: Decimal string, no currency symbol. For example "45.20".
        category: Best fit from the known categories, or a short new name if
            none fit.
        merchant: Shop or place. Empty string if not mentioned.
        note: Any extra detail worth keeping. Usually an empty string.
        date: The date the money was spent, as YYYY-MM-DD.

    Returns:
        Confirmation that the proposal was shown to the user for review.
    """
    # Arguments are read off the model's function call by AgentProposer; this
    # body exists so the agent gets a reply and can finish its turn.
    return {
        "status": "proposed",
        "shown_to_user": True,
        "amount": amount,
        "category": category,
    }


def make_tools(repository: ExpenseRepository) -> list[Callable]:
    """Build the agent's tool set, bound to one user's data."""

    def list_categories() -> dict:
        """List every category available to this user.

        Includes the platform's shared categories and any the user has added.
        Call this before proposing an expense if you are unsure whether a
        category already exists.

        Returns:
            categories: each with a name and a scope of "platform" or "user".
        """
        return {
            "categories": [
                {"name": category.name, "scope": category.scope}
                for category in repository.categories()
            ]
        }

    def query_expenses(
        category: str = "",
        merchant: str = "",
        text: str = "",
        date_from: str = "",
        date_to: str = "",
        min_amount: str = "",
        max_amount: str = "",
        limit: int = 20,
    ) -> dict:
        """Look up the user's recorded expenses. Read-only.

        Every filter is optional and they combine. Leave one as an empty string
        to ignore it. Results come back newest first.

        Args:
            category: Exact category name, case-insensitive. For example "Dining".
            merchant: Part of a merchant name, case-insensitive. "tim" matches
                "Tim Hortons #2841".
            text: Free text matched against the merchant and the note.
            date_from: Earliest date to include, YYYY-MM-DD, inclusive.
            date_to: Latest date to include, YYYY-MM-DD, inclusive.
            min_amount: Smallest amount to include, as a decimal string.
            max_amount: Largest amount to include, as a decimal string.
            limit: Maximum number of expenses to return. Defaults to 20.

        Returns:
            count, total, and the matching expenses. On bad input, an `error`
            explaining which argument was wrong.
        """
        try:
            query = ExpenseQuery(
                category=category or None,
                merchant=merchant or None,
                text=text or None,
                date_from=_as_date(date_from, "date_from"),
                date_to=_as_date(date_to, "date_to"),
                min_amount=_as_decimal(min_amount, "min_amount"),
                max_amount=_as_decimal(max_amount, "max_amount"),
                limit=limit,
            )
        except ValueError as error:
            # Returned rather than raised: the agent can correct itself and
            # try again, where an exception would just end the turn.
            return {"error": str(error)}

        matching = repository.query(query)
        total = sum((expense.amount for expense in matching), Decimal("0"))

        return {
            "count": len(matching),
            "total": f"{total:.2f}",
            "expenses": [_as_dict(expense) for expense in matching],
        }

    return [propose_expense, list_categories, query_expenses]


def _as_dict(expense: Expense) -> dict:
    """JSON-safe view of an expense. Decimal and date do not serialise."""
    return {
        "date": expense.date.isoformat(),
        "amount": str(expense.amount),
        "category": expense.category,
        "merchant": expense.merchant,
        "note": expense.note,
    }


def _as_date(value: str, field: str) -> Date | None:
    if not value:
        return None
    try:
        return Date.fromisoformat(value)
    except ValueError:
        raise ValueError(
            f"{field} must be a date like 2026-09-12, got {value!r}"
        ) from None


def _as_decimal(value: str, field: str) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(
            f"{field} must be a number like 45.20, got {value!r}"
        ) from None
