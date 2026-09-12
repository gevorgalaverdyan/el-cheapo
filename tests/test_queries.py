from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from elcheapo.models import Expense, ExpenseQuery
from elcheapo.store.memory import InMemoryRepository

LOGGED = datetime(2026, 9, 12, tzinfo=timezone.utc)


def an_expense(day: int, amount: str, category: str, merchant: str = "", note: str = ""):
    return Expense(
        date=date(2026, 9, day),
        amount=Decimal(amount),
        category=category,
        merchant=merchant,
        note=note,
        source="text",
        logged_at=LOGGED,
        draft_id=f"d{day}{amount}",
    )


@pytest.fixture
def repo() -> InMemoryRepository:
    repository = InMemoryRepository()
    for expense in [
        an_expense(1, "12.00", "Dining", "Tim Hortons", "morning coffee"),
        an_expense(3, "85.40", "Groceries", "Loblaws"),
        an_expense(5, "45.00", "Dining", "Kinton Ramen"),
        an_expense(8, "62.30", "Transport", "Petro-Canada", "fill up"),
        an_expense(11, "9.99", "Dining", "Tim Hortons"),
    ]:
        repository.append_expense(expense)
    return repository


def amounts(results) -> list[str]:
    return [str(expense.amount) for expense in results]


def test_an_empty_query_returns_everything(repo):
    assert len(repo.query(ExpenseQuery())) == 5


def test_results_come_back_newest_first(repo):
    assert amounts(repo.query(ExpenseQuery()))[0] == "9.99"


def test_filtering_by_category(repo):
    results = repo.query(ExpenseQuery(category="Dining"))

    assert len(results) == 3
    assert all(e.category == "Dining" for e in results)


def test_category_matching_ignores_case(repo):
    assert len(repo.query(ExpenseQuery(category="dining"))) == 3


def test_filtering_by_merchant_matches_part_of_the_name(repo):
    # The agent will pass "tim hortons" when the row says "Tim Hortons #2841".
    results = repo.query(ExpenseQuery(merchant="tim"))

    assert len(results) == 2


def test_filtering_from_a_date_is_inclusive(repo):
    results = repo.query(ExpenseQuery(date_from=date(2026, 9, 5)))

    assert amounts(results) == ["9.99", "62.30", "45.00"]


def test_filtering_to_a_date_is_inclusive(repo):
    results = repo.query(ExpenseQuery(date_to=date(2026, 9, 3)))

    assert amounts(results) == ["85.40", "12.00"]


def test_filtering_by_a_date_range(repo):
    results = repo.query(
        ExpenseQuery(date_from=date(2026, 9, 3), date_to=date(2026, 9, 8))
    )

    assert amounts(results) == ["62.30", "45.00", "85.40"]


def test_filtering_by_minimum_amount(repo):
    assert amounts(repo.query(ExpenseQuery(min_amount=Decimal("60")))) == [
        "62.30",
        "85.40",
    ]


def test_filtering_by_maximum_amount(repo):
    assert amounts(repo.query(ExpenseQuery(max_amount=Decimal("12")))) == [
        "9.99",
        "12.00",
    ]


def test_free_text_matches_the_note(repo):
    results = repo.query(ExpenseQuery(text="fill up"))

    assert amounts(results) == ["62.30"]


def test_free_text_also_matches_the_merchant(repo):
    assert len(repo.query(ExpenseQuery(text="kinton"))) == 1


def test_filters_combine(repo):
    results = repo.query(
        ExpenseQuery(category="Dining", merchant="tim", max_amount=Decimal("10"))
    )

    assert amounts(results) == ["9.99"]


def test_the_limit_is_respected(repo):
    assert len(repo.query(ExpenseQuery(limit=2))) == 2


def test_a_query_matching_nothing_returns_empty(repo):
    assert repo.query(ExpenseQuery(category="Rent")) == []
