"""An in-memory workbook, so the bot runs before any Google setup exists.

Rows are printed as they land and lost on restart. It satisfies the same
interface the real Sheets repository will, which is the point: the handler
cannot tell the difference.
"""

from elcheapo.models import Category, Expense

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


class InMemorySheetsRepository:
    def __init__(self, categories: list[str] | None = None):
        self._categories = [
            Category(name=name, created_by="seed")
            for name in (categories if categories is not None else SEED_CATEGORIES)
        ]
        self._expenses: list[Expense] = []

    def categories(self) -> list[Category]:
        return list(self._categories)

    def add_category(self, name: str) -> None:
        self._categories.append(Category(name=name, created_by="agent"))
        print(f"[sheet] new category: {name}")

    def append_expense(self, expense: Expense) -> None:
        self._expenses.append(expense)
        print(
            f"[sheet] {expense.date} {expense.amount:>9} "
            f"{expense.category:<15} {expense.merchant}"
        )

    def recent_draft_ids(self, limit: int = 200) -> set[str]:
        return {expense.draft_id for expense in self._expenses[-limit:]}

    @property
    def expenses(self) -> list[Expense]:
        return list(self._expenses)
