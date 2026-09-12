"""Monthly budgets: storing them, and working out where a user stands."""

from datetime import date, datetime, timezone
from decimal import Decimal

from elcheapo.budgets import status_for, statuses
from elcheapo.models import Expense
from elcheapo.store.memory import InMemoryRepository

TODAY = date(2026, 9, 12)
LOGGED = datetime(2026, 9, 12, tzinfo=timezone.utc)


def a_repository() -> InMemoryRepository:
    return InMemoryRepository(categories=["Dining", "Groceries"])


def spend(repository, day: int, amount: str, category: str) -> None:
    repository.append_expense(
        Expense(
            date=date(2026, 9, day),
            amount=Decimal(amount),
            category=category,
            merchant="",
            note="",
            source="text",
            logged_at=LOGGED,
            draft_id=f"d{day}{amount}{category}",
        )
    )


def budget_of(repository, name: str):
    return next(c.monthly_budget for c in repository.categories() if c.name == name)


# --- storing a budget --------------------------------------------------


def test_a_category_has_no_budget_until_one_is_set():
    assert budget_of(a_repository(), "Dining") is None


def test_a_budget_shows_up_on_the_category():
    repository = a_repository()

    repository.set_budget("Dining", Decimal("300"))

    assert budget_of(repository, "Dining") == Decimal("300")


def test_a_budget_is_matched_without_regard_to_case():
    """The agent passes back whatever the user typed."""
    repository = a_repository()

    repository.set_budget("dining", Decimal("300"))

    assert budget_of(repository, "Dining") == Decimal("300")


def test_setting_a_budget_again_replaces_the_first():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))

    repository.set_budget("Dining", Decimal("250"))

    assert budget_of(repository, "Dining") == Decimal("250")


def test_a_budget_can_be_cleared():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))

    repository.set_budget("Dining", None)

    assert budget_of(repository, "Dining") is None


def test_one_budget_does_not_leak_onto_another_category():
    repository = a_repository()

    repository.set_budget("Dining", Decimal("300"))

    assert budget_of(repository, "Groceries") is None


# --- where the user stands ---------------------------------------------


def test_nothing_is_reported_when_no_budget_is_set():
    assert statuses(a_repository(), today=TODAY) == []


def test_a_budget_with_no_spending_yet_reports_zero():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))

    standing = statuses(repository, today=TODAY)[0]

    assert standing.spent == Decimal("0")
    assert standing.remaining == Decimal("300")


def test_spending_counts_towards_its_category():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))
    spend(repository, 3, "45.00", "Dining")

    assert statuses(repository, today=TODAY)[0].spent == Decimal("45.00")


def test_spending_in_another_category_does_not_count():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))
    spend(repository, 3, "85.00", "Groceries")

    assert statuses(repository, today=TODAY)[0].spent == Decimal("0")


def test_only_this_month_counts():
    """A monthly budget starts again on the first."""
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))
    repository.append_expense(
        Expense(
            date=date(2026, 8, 30),
            amount=Decimal("200.00"),
            category="Dining",
            merchant="",
            note="",
            source="text",
            logged_at=LOGGED,
            draft_id="last-month",
        )
    )

    assert statuses(repository, today=TODAY)[0].spent == Decimal("0")


def test_a_category_recorded_in_another_case_still_counts():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))
    spend(repository, 3, "45.00", "dining")

    assert statuses(repository, today=TODAY)[0].spent == Decimal("45.00")


def test_the_percentage_used_is_reported():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))
    spend(repository, 3, "150.00", "Dining")

    assert statuses(repository, today=TODAY)[0].percent == 50


def test_going_over_is_flagged():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))
    spend(repository, 3, "320.00", "Dining")

    standing = statuses(repository, today=TODAY)[0]

    assert standing.is_over is True
    assert standing.remaining == Decimal("-20.00")


def test_staying_under_is_not_flagged():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))
    spend(repository, 3, "45.00", "Dining")

    assert statuses(repository, today=TODAY)[0].is_over is False


def test_one_category_can_be_asked_about_on_its_own():
    repository = a_repository()
    repository.set_budget("Dining", Decimal("300"))
    spend(repository, 3, "45.00", "Dining")

    assert status_for(repository, "Dining", today=TODAY).spent == Decimal("45.00")


def test_asking_about_a_category_with_no_budget_gives_nothing():
    """The confirmed card uses this: no budget means no extra line."""
    assert status_for(a_repository(), "Groceries", today=TODAY) is None
