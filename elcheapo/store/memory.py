"""An in-memory store, so the bot runs with no database at all.

Postgres is the real storage -- see `store/postgres.py`, which is what the
bot uses when it runs for real. This exists so the test suite and the
receipt harness can exercise everything above the storage seam without a
container, and so a first run needs nothing set up. It implements the same
protocol, which is the point: the handler cannot tell the difference.

Everything written here is printed as it lands and lost on restart.
"""

from datetime import datetime, timezone
from uuid import uuid4

from elcheapo.models import Category, Expense, ExpenseQuery, Task

SEED_CATEGORIES = [
    "Groceries",
    "Dining",
    "Transport",
    "Utilities",
    "Rent",
    "Health",
    "Shopping",
    "Entertainment",
    "Travel",
    "Subscriptions",
    "Other",
]


class InMemoryRepository:
    def __init__(self, categories: list[str] | None = None):
        self._categories = [
            Category(name=name, scope="platform")
            for name in (categories if categories is not None else SEED_CATEGORIES)
        ]
        self._expenses: list[Expense] = []
        self._postal_code: str | None = None
        self._tasks: list[Task] = []

    def categories(self) -> list[Category]:
        return list(self._categories)

    def add_category(self, name: str) -> None:
        self._categories.append(Category(name=name, scope="user"))
        print(f"[memory] new category: {name}")

    def append_expense(self, expense: Expense) -> None:
        self._expenses.append(expense)
        print(
            f"[memory] {expense.date} {expense.amount:>9} "
            f"{expense.category:<15} {expense.merchant}"
        )

    def recent_draft_ids(self, limit: int = 200) -> set[str]:
        return {expense.draft_id for expense in self._expenses[-limit:]}

    def query(self, query: ExpenseQuery) -> list[Expense]:
        matching = [e for e in self._expenses if query.matches(e)]
        # Newest first, with logged_at breaking ties between same-day rows.
        matching.sort(key=lambda e: (e.date, e.logged_at), reverse=True)
        return matching[: query.limit]

    def postal_code(self) -> str | None:
        return self._postal_code

    def set_postal_code(self, code: str) -> None:
        self._postal_code = code
        print(f"[memory] postal code: {code}")

    def tasks(self, include_complete: bool = False) -> list[Task]:
        return [
            task
            for task in self._tasks
            if include_complete or not task.is_complete
        ]

    def add_task(self, task: str) -> Task:
        now = datetime.now(timezone.utc)
        created = Task(
            task_id=str(uuid4()),
            task=task,
            created_at=now,
            updated_at=now,
        )
        self._tasks.append(created)
        print(f"[memory] new task: {task}")
        return created

    def update_task(
        self,
        task_id: str,
        *,
        task: str | None = None,
        is_complete: bool | None = None,
    ) -> Task | None:
        for index, existing in enumerate(self._tasks):
            if existing.task_id != task_id:
                continue
            updated = existing.model_copy(
                update={
                    "task": existing.task if task is None else task,
                    "is_complete": (
                        existing.is_complete
                        if is_complete is None
                        else is_complete
                    ),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._tasks[index] = updated
            return updated
        return None

    @property
    def expenses(self) -> list[Expense]:
        return list(self._expenses)
