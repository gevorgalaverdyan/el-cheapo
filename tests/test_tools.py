from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from elcheapo.agent.tools import make_tools
from elcheapo.models import Expense
from elcheapo.store.memory import InMemoryRepository
from tests.fakes import FakeFlipp

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

    assert set(by_name) == {
        "propose_expense",
        "list_categories",
        "query_expenses",
        "export_expenses",
        "add_task",
        "list_tasks",
        "complete_task",
        "edit_task",
        "set_budget",
        "budget_status",
    }


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


# --- export ------------------------------------------------------------

@pytest.fixture
def exporting():
    repository = InMemoryRepository(categories=["Dining", "Groceries"])
    for expense in [
        an_expense(1, "12.00", "Dining", "Tim Hortons"),
        an_expense(3, "85.40", "Groceries", "Loblaws"),
        an_expense(5, "45.00", "Dining", "Kinton Ramen"),
    ]:
        repository.append_expense(expense)
    documents = []
    tools = {t.__name__: t for t in make_tools(repository, currency="CAD", documents=documents)}
    return tools["export_expenses"], documents


def test_export_is_offered_as_a_tool(tools):
    by_name, _ = tools

    assert "export_expenses" in by_name


def test_exporting_produces_a_spreadsheet_by_default(exporting):
    export, documents = exporting

    export()

    assert documents[0].filename.endswith(".xlsx")


def test_exporting_as_csv_when_asked(exporting):
    export, documents = exporting

    export(format="csv")

    assert documents[0].filename.endswith(".csv")
    assert documents[0].data.startswith(b"\xef\xbb\xbf")  # BOM for Excel


def test_the_export_reports_what_it_contains(exporting):
    export, _ = exporting

    result = export()

    assert result["rows"] == 3
    assert result["total"] == "142.40"


def test_filters_narrow_the_export(exporting):
    export, _ = exporting

    result = export(category="Dining")

    assert result["rows"] == 2
    assert result["total"] == "57.00"


def test_the_agent_can_name_the_file(exporting):
    export, documents = exporting

    export(filename="september dining")

    assert documents[0].filename == "september-dining.xlsx"


def test_a_dangerous_filename_is_made_safe(exporting):
    export, documents = exporting

    export(filename="../../etc/passwd")

    assert "/" not in documents[0].filename
    assert ".." not in documents[0].filename


def test_an_unknown_format_is_reported_not_raised(exporting):
    export, documents = exporting

    result = export(format="pdf")

    assert "error" in result
    assert documents == []


def test_an_unknown_grouping_is_reported(exporting):
    export, _ = exporting

    assert "error" in export(group_by="colour")


def test_exporting_nothing_explains_itself_instead_of_sending_an_empty_file(exporting):
    export, documents = exporting

    result = export(category="Rent")

    assert "error" in result
    assert documents == []


def test_grouping_is_passed_through_to_the_report(exporting):
    import io
    from openpyxl import load_workbook

    export, documents = exporting
    export(group_by="category")

    book = load_workbook(io.BytesIO(documents[0].data))
    assert "By category" in book.sheetnames


# --- Flipp deal tools --------------------------------------------------

A_DEAL = {
    "id": 9001,
    "name": "Whole Chicken",
    "flyer_id": 7788,
    "valid_to": "2026-09-18T00:00:00Z",
    "valid_from": "2026-09-12T00:00:00Z",
    "image_url": "https://images.example/chicken.png",
    "sale_story": "Save $3",
    "category_l1": "Food",
    "category_l2": "Meat",
    "merchant_id": 42,
    "merchant_name": "Loblaws",
    "current_price": 5.99,
    "original_price": 8.99,
    "pre_price_text": "2 for",
    "post_price_text": "/lb",
}

# Every field the real API can send as null, sent as null.
A_SPARSE_DEAL = {
    "id": 9002,
    "name": "Store Brand Milk",
    "flyer_id": 7789,
    "valid_to": "2026-09-17T03:59:59+00:00",
    "current_price": 4,
    "original_price": None,
    "pre_price_text": None,
    "post_price_text": None,
    "sale_story": None,
    "merchant_name": "FreshCo",
    "category_l1": "Food, Beverages & Tobacco",
    "category_l2": "Food Items",
}


def deal_tools(flipp, repository=None):
    repository = repository or InMemoryRepository(categories=["Groceries"])
    return {tool.__name__: tool for tool in make_tools(repository, flipp=flipp)}


def remembering(postal_code: str = "") -> InMemoryRepository:
    repository = InMemoryRepository(categories=["Groceries"])
    if postal_code:
        repository.set_postal_code(postal_code)
    return repository


def test_the_deal_tools_are_absent_without_a_flipp_client():
    by_name = deal_tools(None)

    assert "search_deals" not in by_name


def test_the_deal_tools_appear_when_flipp_is_configured():
    by_name = deal_tools(FakeFlipp())

    assert {"search_deals", "list_weekly_ads", "list_flyer_items"} <= set(by_name)


async def test_searching_deals_passes_the_query_and_postal_code_through():
    flipp = FakeFlipp()
    by_name = deal_tools(flipp)

    await by_name["search_deals"]("chicken", "M5V 2T6")

    assert flipp.calls == [("search_deals", "chicken", "M5V 2T6")]


async def test_a_deal_is_trimmed_to_what_the_agent_needs():
    by_name = deal_tools(FakeFlipp(deals={"items": [A_DEAL], "total": 1}))

    deal = (await by_name["search_deals"]("chicken", "M5V 2T6"))["deals"][0]

    assert deal["name"] == "Whole Chicken"
    assert deal["merchant"] == "Loblaws"
    assert deal["was"] == "8.99"
    assert deal["category"] == "Meat"
    assert deal["flyer_id"] == 7788


async def test_a_deal_drops_the_image_url_that_would_only_cost_context():
    by_name = deal_tools(FakeFlipp(deals={"items": [A_DEAL], "total": 1}))

    deal = (await by_name["search_deals"]("chicken", "M5V 2T6"))["deals"][0]

    assert "image_url" not in deal


async def test_a_price_carries_its_qualifiers_so_it_cannot_be_misread():
    """A bare "5.99" reads as each when the flyer means two for that, per pound."""
    by_name = deal_tools(FakeFlipp(deals={"items": [A_DEAL], "total": 1}))

    deal = (await by_name["search_deals"]("chicken", "M5V 2T6"))["deals"][0]

    assert deal["price"] == "2 for 5.99 /lb"


async def test_a_long_post_price_note_is_kept_out_of_the_price():
    """Flyers put marketing copy in that field -- "Available for Same-Day
    delivery at a higher price." is not a unit, and reads as one."""
    wordy = A_DEAL | {
        "pre_price_text": None,
        "post_price_text": "Available for Same-Day delivery at a higher price.",
    }
    by_name = deal_tools(FakeFlipp(deals={"items": [wordy], "total": 1}))

    deal = (await by_name["search_deals"]("chicken", "M5V 2T6"))["deals"][0]

    assert deal["price"] == "5.99"


async def test_a_short_unit_note_stays_in_the_price():
    per_pound = A_DEAL | {"pre_price_text": None, "post_price_text": "lb"}
    by_name = deal_tools(FakeFlipp(deals={"items": [per_pound], "total": 1}))

    deal = (await by_name["search_deals"]("chicken", "M5V 2T6"))["deals"][0]

    assert deal["price"] == "5.99 lb"


async def test_a_deal_that_is_not_marked_down_reports_no_previous_price():
    plain = A_DEAL | {"original_price": 5.99}
    by_name = deal_tools(FakeFlipp(deals={"items": [plain], "total": 1}))

    deal = (await by_name["search_deals"]("chicken", "M5V 2T6"))["deals"][0]

    assert deal["was"] == ""


async def test_the_end_date_is_shortened_to_a_day():
    by_name = deal_tools(FakeFlipp(deals={"items": [A_DEAL], "total": 1}))

    deal = (await by_name["search_deals"]("chicken", "M5V 2T6"))["deals"][0]

    assert deal["valid_to"] == "2026-09-18"


async def test_searching_deals_stops_at_the_limit():
    many = {"items": [A_DEAL] * 40, "total": 40}
    by_name = deal_tools(FakeFlipp(deals=many))

    result = await by_name["search_deals"]("chicken", "M5V 2T6", limit=3)

    assert len(result["deals"]) == 3


async def test_searching_deals_says_how_many_matched_in_total():
    """Otherwise a capped list looks like the whole story."""
    many = {"items": [A_DEAL] * 40, "total": 40}
    by_name = deal_tools(FakeFlipp(deals=many))

    result = await by_name["search_deals"]("chicken", "M5V 2T6", limit=3)

    assert result["total_matching"] == 40


async def test_a_flipp_failure_reaches_the_agent_as_an_error_it_can_relay():
    from elcheapo.flipp import FlippError

    flipp = FakeFlipp(error=FlippError("Flipp rate limit reached; wait a minute."))
    by_name = deal_tools(flipp)

    result = await by_name["search_deals"]("chicken", "M5V 2T6")

    assert "rate limit" in result["error"]


async def test_a_search_without_a_postal_code_is_refused_before_a_credit_is_spent():
    flipp = FakeFlipp()
    by_name = deal_tools(flipp)

    result = await by_name["search_deals"]("chicken", "")

    assert "error" in result
    assert flipp.calls == []


A_FLYER = {
    "flyer_id": 7788,
    "name": "Weekly Savings",
    "merchant": "Loblaws",
    "merchant_id": 42,
    "valid_from": "2026-09-12T00:00:00-04:00",
    "valid_to": "2026-09-18T23:59:59-04:00",
    "categories": ["All Flyers", "Groceries"],
    "thumbnail_url": "https://images.example/flyer.jpg",
}


async def test_weekly_ads_come_back_with_the_ids_needed_to_read_them():
    by_name = deal_tools(FakeFlipp(flyers={"flyers": [A_FLYER], "total": 1}))

    flyer = (await by_name["list_weekly_ads"]("M5V 2T6"))["flyers"][0]

    assert flyer["flyer_id"] == 7788
    assert flyer["merchant"] == "Loblaws"
    assert flyer["valid_to"] == "2026-09-18"


async def test_a_flyer_keeps_its_name_and_categories_to_choose_between_them():
    """A postal code returns well over a hundred flyers, most of them
    furniture and sporting goods. "Loblaws" alone does not say which."""
    by_name = deal_tools(FakeFlipp(flyers={"flyers": [A_FLYER], "total": 1}))

    flyer = (await by_name["list_weekly_ads"]("M5V 2T6"))["flyers"][0]

    assert flyer["name"] == "Weekly Savings"
    assert "Groceries" in flyer["categories"]


async def test_weekly_ads_stop_at_the_limit():
    """A real postal code returns about 150 flyers."""
    by_name = deal_tools(FakeFlipp(flyers={"flyers": [A_FLYER] * 150, "total": 150}))

    result = await by_name["list_weekly_ads"]("M5V 2T6", limit=5)

    assert len(result["flyers"]) == 5
    assert result["total_nearby"] == 150


async def test_weekly_ads_pass_a_merchant_filter_through():
    flipp = FakeFlipp()
    by_name = deal_tools(flipp)

    await by_name["list_weekly_ads"]("M5V 2T6", merchant_name="loblaws")

    assert flipp.calls == [("weekly_ads", "M5V 2T6", "loblaws")]


# A flyer item is a different shape from a search result: one price, as a
# string, no merchant (the flyer says who), and no pre-sale price.
A_FLYER_ITEM = {
    "id": 1,
    "name": "Whole Chicken",
    "brand": "PC",
    "price": "5.99",
    "valid_from": "2026-09-12T00:00:00-04:00",
    "valid_to": "2026-09-18T23:59:59-04:00",
    "image_url": "https://images.example/chicken.png",
    "flyer_id": 7788,
}


async def test_flyer_items_are_listed_for_one_flyer():
    flipp = FakeFlipp(items={"items": [A_FLYER_ITEM], "total": 1})
    by_name = deal_tools(flipp)

    result = await by_name["list_flyer_items"](7788)

    assert flipp.calls == [("flyer_items", 7788)]
    item = result["items"][0]
    assert item["name"] == "Whole Chicken"
    assert item["brand"] == "PC"
    assert item["price"] == "5.99"
    assert item["valid_to"] == "2026-09-18"


async def test_a_flyer_item_without_a_brand_says_nothing_rather_than_null():
    unbranded = A_FLYER_ITEM | {"brand": None}
    by_name = deal_tools(FakeFlipp(items={"items": [unbranded], "total": 1}))

    item = (await by_name["list_flyer_items"](7788))["items"][0]

    assert item["brand"] == ""


async def test_flyer_items_stop_at_the_limit():
    by_name = deal_tools(
        FakeFlipp(items={"items": [A_FLYER_ITEM] * 60, "total": 60})
    )

    result = await by_name["list_flyer_items"](7788, limit=5)

    assert len(result["items"]) == 5
    assert result["total_in_flyer"] == 60


async def test_a_deal_with_every_optional_field_null_still_reads_cleanly():
    """The API sends null for sale_story, both price notes and original_price."""
    by_name = deal_tools(FakeFlipp(deals={"items": [A_SPARSE_DEAL], "total": 1}))

    deal = (await by_name["search_deals"]("milk", "M5V 2T6"))["deals"][0]

    assert deal["price"] == "4.00"
    assert deal["was"] == ""
    assert deal["deal"] == ""
    assert deal["name"] == "Store Brand Milk"


# --- remembering where the user shops ----------------------------------


async def test_a_postal_code_the_user_gives_is_remembered():
    repository = remembering()
    by_name = deal_tools(FakeFlipp(), repository)

    await by_name["remember_postal_code"]("m5v2t6")

    assert repository.postal_code() == "M5V 2T6"


async def test_remembering_a_postal_code_confirms_what_was_stored():
    by_name = deal_tools(FakeFlipp(), remembering())

    result = await by_name["remember_postal_code"]("m5v2t6")

    assert result["postal_code"] == "M5V 2T6"


async def test_a_zip_is_refused_because_the_bot_is_canada_only():
    """Flipp answers a ZIP with US flyers -- plausible deals at unreachable shops."""
    repository = remembering()
    by_name = deal_tools(FakeFlipp(), repository)

    result = await by_name["remember_postal_code"]("95054")

    assert "error" in result
    assert repository.postal_code() is None


async def test_searching_deals_uses_the_remembered_postal_code():
    """The whole point: the user says where they live once."""
    flipp = FakeFlipp()
    by_name = deal_tools(flipp, remembering("M5V 2T6"))

    await by_name["search_deals"]("chicken")

    assert flipp.calls == [("search_deals", "chicken", "M5V 2T6")]


async def test_a_postal_code_given_in_the_moment_beats_the_remembered_one():
    """Asking about deals while away should not move where they live."""
    flipp = FakeFlipp()
    repository = remembering("M5V 2T6")
    by_name = deal_tools(flipp, repository)

    await by_name["search_deals"]("chicken", "H2Y 1C6")

    assert flipp.calls == [("search_deals", "chicken", "H2Y 1C6")]
    assert repository.postal_code() == "M5V 2T6"


async def test_a_malformed_postal_code_is_refused_before_a_credit_is_spent():
    flipp = FakeFlipp()
    by_name = deal_tools(flipp, remembering())

    result = await by_name["search_deals"]("chicken", "95054")

    assert "error" in result
    assert flipp.calls == []


async def test_weekly_ads_also_use_the_remembered_postal_code():
    flipp = FakeFlipp()
    by_name = deal_tools(flipp, remembering("M5V 2T6"))

    await by_name["list_weekly_ads"]()

    assert flipp.calls == [("weekly_ads", "M5V 2T6", "")]


# --- the todo list -----------------------------------------------------


def todo_tools(repository=None):
    repository = repository or InMemoryRepository(categories=["Groceries"])
    return {
        tool.__name__: tool for tool in make_tools(repository)
    }, repository


def test_the_todo_tools_do_not_need_a_flipp_key():
    by_name, _ = todo_tools()

    assert {"add_task", "list_tasks", "complete_task", "edit_task"} <= set(by_name)


async def test_adding_a_task_stores_it():
    by_name, repository = todo_tools()

    await by_name["add_task"]("buy milk")

    assert [task.task for task in repository.tasks()] == ["buy milk"]


async def test_adding_a_task_returns_the_id_needed_to_change_it_later():
    by_name, repository = todo_tools()

    result = await by_name["add_task"]("buy milk")

    assert result["task_id"] == repository.tasks()[0].task_id


async def test_an_empty_task_is_refused_rather_than_stored():
    by_name, repository = todo_tools()

    result = await by_name["add_task"]("   ")

    assert "error" in result
    assert repository.tasks() == []


async def test_listing_tasks_returns_what_was_added():
    by_name, _ = todo_tools()
    await by_name["add_task"]("buy milk")
    await by_name["add_task"]("call the vet")

    result = await by_name["list_tasks"]()

    assert [task["task"] for task in result["tasks"]] == ["buy milk", "call the vet"]


async def test_listing_tasks_hides_finished_ones_by_default():
    by_name, _ = todo_tools()
    added = await by_name["add_task"]("buy milk")
    await by_name["complete_task"](added["task_id"])

    assert (await by_name["list_tasks"]())["tasks"] == []


async def test_finished_tasks_can_be_asked_for():
    by_name, _ = todo_tools()
    added = await by_name["add_task"]("buy milk")
    await by_name["complete_task"](added["task_id"])

    result = await by_name["list_tasks"](include_complete=True)

    assert result["tasks"][0]["is_complete"] is True


async def test_completing_a_task_marks_it_done():
    by_name, repository = todo_tools()
    added = await by_name["add_task"]("buy milk")

    await by_name["complete_task"](added["task_id"])

    assert repository.tasks(include_complete=True)[0].is_complete is True


async def test_a_task_can_be_reopened_when_it_was_not_really_done():
    by_name, repository = todo_tools()
    added = await by_name["add_task"]("buy milk")
    await by_name["complete_task"](added["task_id"])

    await by_name["complete_task"](added["task_id"], done=False)

    assert repository.tasks()[0].is_complete is False


async def test_completing_a_task_that_does_not_exist_says_so():
    by_name, _ = todo_tools()

    result = await by_name["complete_task"]("no-such-id")

    assert "error" in result


async def test_editing_a_task_changes_its_words():
    by_name, repository = todo_tools()
    added = await by_name["add_task"]("buy milk")

    await by_name["edit_task"](added["task_id"], "buy oat milk")

    assert repository.tasks()[0].task == "buy oat milk"


async def test_editing_a_task_that_does_not_exist_says_so():
    by_name, _ = todo_tools()

    result = await by_name["edit_task"]("no-such-id", "buy oat milk")

    assert "error" in result


async def test_editing_a_task_to_nothing_is_refused():
    by_name, repository = todo_tools()
    added = await by_name["add_task"]("buy milk")

    result = await by_name["edit_task"](added["task_id"], "  ")

    assert "error" in result
    assert repository.tasks()[0].task == "buy milk"


class RecordingTasks(InMemoryRepository):
    """Notices when a tool reaches storage with an id it should have refused."""

    def __init__(self):
        super().__init__(categories=["Groceries"])
        self.update_calls: list[str] = []

    def update_task(self, task_id, *, task=None, is_complete=None):
        self.update_calls.append(task_id)
        return super().update_task(task_id, task=task, is_complete=is_complete)


async def test_an_id_that_is_not_an_id_never_reaches_storage():
    """Postgres answers a malformed uuid with an error, not an empty result --
    which would end the turn instead of letting the agent correct itself."""
    repository = RecordingTasks()
    by_name, _ = todo_tools(repository)

    result = await by_name["complete_task"]("the milk one")

    assert "error" in result
    assert repository.update_calls == []


async def test_editing_with_a_malformed_id_is_refused_the_same_way():
    repository = RecordingTasks()
    by_name, _ = todo_tools(repository)

    result = await by_name["edit_task"]("3", "buy oat milk")

    assert "error" in result
    assert repository.update_calls == []


# --- budgets -----------------------------------------------------------


def budget_tools(repository=None):
    repository = repository or InMemoryRepository(categories=["Dining", "Groceries"])
    return {
        tool.__name__: tool
        for tool in make_tools(repository, today=date(2026, 9, 12))
    }, repository


async def test_setting_a_budget_stores_it():
    by_name, repository = budget_tools()

    await by_name["set_budget"]("Dining", "300")

    assert [c.monthly_budget for c in repository.categories() if c.name == "Dining"] == [
        Decimal("300")
    ]


async def test_a_budget_can_be_cleared_with_an_empty_amount():
    by_name, repository = budget_tools()
    await by_name["set_budget"]("Dining", "300")

    await by_name["set_budget"]("Dining", "")

    assert [c.monthly_budget for c in repository.categories() if c.name == "Dining"] == [
        None
    ]


async def test_a_budget_for_an_unknown_category_is_refused():
    """Otherwise a typo becomes a budget nothing will ever be spent against."""
    by_name, repository = budget_tools()

    result = await by_name["set_budget"]("Dning", "300")

    assert "error" in result
    assert all(c.monthly_budget is None for c in repository.categories())


async def test_a_budget_that_is_not_a_number_is_refused():
    by_name, _ = budget_tools()

    assert "error" in await by_name["set_budget"]("Dining", "lots")


async def test_a_negative_budget_is_refused():
    by_name, _ = budget_tools()

    assert "error" in await by_name["set_budget"]("Dining", "-50")


async def test_budget_status_reports_nothing_when_no_budget_is_set():
    by_name, _ = budget_tools()

    assert (await by_name["budget_status"]())["budgets"] == []


async def test_budget_status_reports_spending_against_the_budget():
    by_name, repository = budget_tools()
    await by_name["set_budget"]("Dining", "300")
    repository.append_expense(
        an_expense(3, "45.00", "Dining", "Kinton Ramen")
    )

    standing = (await by_name["budget_status"]())["budgets"][0]

    assert standing["spent"] == "45.00"
    assert standing["budget"] == "300.00"
    assert standing["remaining"] == "255.00"
    assert standing["percent"] == 15


async def test_budget_status_says_when_a_budget_is_blown():
    by_name, repository = budget_tools()
    await by_name["set_budget"]("Dining", "40")
    repository.append_expense(an_expense(3, "45.00", "Dining"))

    standing = (await by_name["budget_status"]())["budgets"][0]

    assert standing["is_over"] is True
    assert standing["remaining"] == "-5.00"
