from datetime import date, datetime, timezone
from decimal import Decimal

from elcheapo.commit import commit_expense
from elcheapo.models import Draft
from tests.fakes import FakeExpenseRepository

NOW = datetime(2026, 9, 12, 18, 4, 11, tzinfo=timezone.utc)


def a_draft(**overrides) -> Draft:
    fields = dict(
        draft_id="7k2m9x",
        amount=Decimal("45.20"),
        category="Groceries",
        is_new_category=False,
        merchant="Seoudi",
        note="",
        date=date(2026, 9, 12),
        source="image",
    )
    fields.update(overrides)
    return Draft(**fields)


def test_a_draft_becomes_an_expense_row():
    repo = FakeExpenseRepository(categories=["Groceries"])

    commit_expense(a_draft(), repo, now=NOW)

    assert [(e.amount, e.category, e.merchant) for e in repo.expenses] == [
        (Decimal("45.20"), "Groceries", "Seoudi")
    ]


def test_the_row_records_when_it_was_logged():
    repo = FakeExpenseRepository(categories=["Groceries"])

    commit_expense(a_draft(), repo, now=NOW)

    assert repo.expenses[0].logged_at == NOW


def test_a_new_category_is_created_before_the_expense_that_uses_it():
    repo = FakeExpenseRepository(categories=["Dining"])

    commit_expense(a_draft(category="Groceries", is_new_category=True), repo, now=NOW)

    assert repo.calls == ["add_category:Groceries", "append_expense:7k2m9x"]


def test_an_existing_category_is_not_recreated():
    repo = FakeExpenseRepository(categories=["Groceries"])

    commit_expense(a_draft(category="Groceries", is_new_category=True), repo, now=NOW)

    assert repo.calls == ["append_expense:7k2m9x"]


def test_category_matching_ignores_case_and_surrounding_space():
    repo = FakeExpenseRepository(categories=["Groceries"])

    commit_expense(a_draft(category=" groceries ", is_new_category=True), repo, now=NOW)

    assert repo.calls == ["append_expense:7k2m9x"]


def test_committing_the_same_draft_twice_writes_one_row():
    repo = FakeExpenseRepository(categories=["Groceries"])
    draft = a_draft()

    first = commit_expense(draft, repo, now=NOW)
    second = commit_expense(draft, repo, now=NOW)

    assert len(repo.expenses) == 1
    assert first.committed is True
    assert second.committed is False
    assert second.duplicate is True


def test_a_failed_append_can_be_retried_successfully():
    repo = FakeExpenseRepository(categories=["Groceries"])
    repo.append_failures = 1
    draft = a_draft()

    try:
        commit_expense(draft, repo, now=NOW)
    except RuntimeError:
        pass

    result = commit_expense(draft, repo, now=NOW)

    assert result.committed is True
    assert len(repo.expenses) == 1
