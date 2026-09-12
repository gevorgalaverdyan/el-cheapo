"""Where a user stands against their monthly budgets.

Spend is worked out from the expenses already recorded rather than kept as a
running total, so a corrected or deleted expense cannot leave a counter wrong.
A month's worth of one person's expenses is a small read.
"""

from collections import defaultdict
from datetime import date as Date
from decimal import Decimal

from elcheapo.models import BudgetStatus, ExpenseQuery
from elcheapo.store.repository import ExpenseRepository

# A personal month runs to dozens of expenses, not hundreds, so this is never
# reached in practice. It is also the most ExpenseQuery will accept.
MONTHLY_CAP = 500


def statuses(repository: ExpenseRepository, *, today: Date) -> list[BudgetStatus]:
    """Every budgeted category, with what has been spent against it this month."""
    budgeted = [
        category
        for category in repository.categories()
        if category.monthly_budget is not None
    ]
    if not budgeted:
        # No budgets, so no reason to read a month of expenses.
        return []

    spent = _spent_by_category(repository, today=today)
    return [
        BudgetStatus(
            category=category.name,
            monthly_budget=category.monthly_budget,
            spent=spent[category.name.casefold()],
        )
        for category in budgeted
    ]


def status_for(
    repository: ExpenseRepository, category: str, *, today: Date
) -> BudgetStatus | None:
    """Where one category stands, or None if it has no budget."""
    wanted = category.casefold()
    for standing in statuses(repository, today=today):
        if standing.category.casefold() == wanted:
            return standing
    return None


def month_start(today: Date) -> Date:
    """The first of the month `today` falls in. Budgets reset here."""
    return today.replace(day=1)


def _spent_by_category(
    repository: ExpenseRepository, *, today: Date
) -> dict[str, Decimal]:
    """This month's spending, totalled per category and keyed case-insensitively.

    Categories are matched without regard to case everywhere else, and an
    expense recorded as "dining" has to count against the "Dining" budget.
    """
    this_month = repository.query(
        ExpenseQuery(date_from=month_start(today), limit=MONTHLY_CAP)
    )

    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for expense in this_month:
        totals[expense.category.casefold()] += expense.amount
    return totals
