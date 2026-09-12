from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from elcheapo.agent.tools import make_tools
from elcheapo.models import Expense
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
def tools():
    repository = InMemoryRepository(categories=["Dining", "Groceries", "Transport"])
    for expense in [
        an_expense(1, "12.00", "Dining", "Tim Hortons", "morning coffee"),
        an_expense(3, "85.40", "Groceries", "Loblaws"),
        an_expense(5, "45.00", "Dining", "Kinton Ramen"),
        an_expense(8, "62.30", "Transport", "Petro-Canada"),
    ]:
        repository.append_expense(expense)
    repository.add_category("Vet")
    return {tool.__name__: tool for tool in make_tools(repository)}, repository


def test_the_agent_is_given_the_expected_tools(tools):
    by_name, _ = tools

    assert set(by_name) == {"propose_expense", "list_categories", "query_expenses"}


def test_list_categories_returns_platform_and_user_categories(tools):
    by_name, _ = tools

    names = [c["name"] for c in by_name["list_categories"]()["categories"]]

    assert names == ["Dining", "Groceries", "Transport", "Vet"]


def test_list_categories_says_which_are_the_users_own(tools):
    by_name, _ = tools

    scopes = {c["name"]: c["scope"] for c in by_name["list_categories"]()["categories"]}

    assert scopes["Dining"] == "platform"
    assert scopes["Vet"] == "user"


def test_query_expenses_with_no_filters_returns_everything(tools):
    by_name, _ = tools

    result = by_name["query_expenses"]()

    assert result["count"] == 4


def test_query_expenses_reports_the_total(tools):
    by_name, _ = tools

    result = by_name["query_expenses"]()

    assert result["total"] == "204.70"


def test_query_expenses_totals_only_what_matched(tools):
    by_name, _ = tools

    result = by_name["query_expenses"](category="Dining")

    assert result["count"] == 2
    assert result["total"] == "57.00"


def test_query_expenses_filters_by_merchant(tools):
    by_name, _ = tools

    assert by_name["query_expenses"](merchant="tim")["count"] == 1


def test_query_expenses_filters_by_date_range(tools):
    by_name, _ = tools

    result = by_name["query_expenses"](date_from="2026-09-03", date_to="2026-09-05")

    assert result["count"] == 2


def test_query_expenses_returns_json_safe_amounts(tools):
    by_name, _ = tools

    first = by_name["query_expenses"]()["expenses"][0]

    # Decimal is not JSON-serialisable, and the agent's reply must serialise.
    assert isinstance(first["amount"], str)
    assert isinstance(first["date"], str)


def test_query_expenses_respects_a_limit(tools):
    by_name, _ = tools

    assert by_name["query_expenses"](limit=2)["count"] == 2


def test_a_malformed_date_is_reported_not_raised(tools):
    by_name, _ = tools

    result = by_name["query_expenses"](date_from="last tuesday")

    # The agent should get a message it can act on, not a stack trace that
    # ends the turn.
    assert "error" in result
    assert "date_from" in result["error"]


def test_a_malformed_amount_is_reported_not_raised(tools):
    by_name, _ = tools

    result = by_name["query_expenses"](min_amount="a lot")

    assert "error" in result


def test_a_query_matching_nothing_is_an_empty_result_not_an_error(tools):
    by_name, _ = tools

    result = by_name["query_expenses"](category="Rent")

    assert result["count"] == 0
    assert result["total"] == "0.00"
    assert result["expenses"] == []
