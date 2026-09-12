"""The seam between the application and its storage.

Everything above this interface is testable without a database: the tests
run against InMemoryRepository, which implements the same protocol.
"""

from typing import Protocol

from elcheapo.models import Category, Expense, ExpenseQuery, Task


class ExpenseRepository(Protocol):
    """Everything one user's data supports: expenses, categories,
    their postal code, and their todo list."""

    def categories(self) -> list[Category]:
        """All categories, in sheet order."""
        ...

    def add_category(self, name: str) -> None:
        """Append a new category. Called before any expense that uses it."""
        ...

    def append_expense(self, expense: Expense) -> None:
        """Store a confirmed expense."""
        ...

    def recent_draft_ids(self, limit: int = 200) -> set[str]:
        """Draft ids from the most recent expenses, for idempotency checks."""
        ...

    def query(self, query: ExpenseQuery) -> list[Expense]:
        """Matching expenses, newest first."""
        ...

    def postal_code(self) -> str | None:
        """The user's postal code, or None if they have not given one."""
        ...

    def set_postal_code(self, code: str) -> None:
        """Remember this postal code, replacing any earlier one."""
        ...

    def tasks(self, include_complete: bool = False) -> list[Task]:
        """The user's todo list, oldest first."""
        ...

    def add_task(self, task: str) -> Task:
        """Add a task and return it, id and all."""
        ...

    def update_task(
        self,
        task_id: str,
        *,
        task: str | None = None,
        is_complete: bool | None = None,
    ) -> Task | None:
        """Change a task's words, its state, or both.

        Returns the task as it now stands, or None if this user has no
        task with that id.
        """
        ...
