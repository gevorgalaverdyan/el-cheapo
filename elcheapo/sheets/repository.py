"""The seam between the application and the workbook.

Everything above this interface is testable without credentials or network.
"""

from typing import Protocol

from elcheapo.models import Category, Expense


class SheetsRepository(Protocol):
    """Reads and writes for the expense workbook."""

    def categories(self) -> list[Category]:
        """All categories, in sheet order."""
        ...

    def add_category(self, name: str) -> None:
        """Append a new category. Called before any expense that uses it."""
        ...

    def append_expense(self, expense: Expense) -> None:
        """Append a confirmed expense row."""
        ...

    def recent_draft_ids(self, limit: int = 200) -> set[str]:
        """Draft ids from the most recent rows, for idempotency checks."""
        ...
