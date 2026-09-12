"""Tools the agent may call.

Two shapes live here. `propose_expense` announces an intention and writes
nothing -- the handler turns it into a card a human accepts. The read tools
close over one user's repository, so a tool call can only ever reach the data
of the chat it was built for.

Docstrings and type hints are not decoration: ADK derives the function
declarations the model sees from them, so they are part of the prompt.
"""

from datetime import date as Date
from decimal import Decimal, InvalidOperation
from typing import Callable

from elcheapo.flipp import Flipp, FlippError
from elcheapo.models import Document, Expense, ExpenseQuery
from elcheapo.postal import normalise
from elcheapo.reports import GROUPINGS, build_csv, build_xlsx
from elcheapo.store.repository import ExpenseRepository

PROPOSE_EXPENSE = "propose_expense"
LIST_CATEGORIES = "list_categories"
QUERY_EXPENSES = "query_expenses"
EXPORT_EXPENSES = "export_expenses"
SEARCH_DEALS = "search_deals"
LIST_WEEKLY_ADS = "list_weekly_ads"
LIST_FLYER_ITEMS = "list_flyer_items"
REMEMBER_POSTAL_CODE = "remember_postal_code"

# Longer than this and a price qualifier is marketing copy, not a unit.
MAX_PRICE_NOTE = 12

FORMATS = {
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "csv": "text/csv",
}


def propose_expense(
    amount: str,
    category: str,
    merchant: str,
    note: str,
    date: str,
) -> dict:
    """Propose an expense for the user to confirm. Does not save anything.

    Call this whenever the user describes money they spent, including when they
    are correcting an expense you proposed a moment ago -- call it again with
    the corrected values rather than apologising.

    Args:
        amount: Decimal string, no currency symbol. For example "45.20".
        category: Best fit from the known categories, or a short new name if
            none fit.
        merchant: Shop or place. Empty string if not mentioned.
        note: Any extra detail worth keeping. Usually an empty string.
        date: The date the money was spent, as YYYY-MM-DD.

    Returns:
        Confirmation that the proposal was shown to the user for review.
    """
    # Arguments are read off the model's function call by AgentProposer; this
    # body exists so the agent gets a reply and can finish its turn.
    return {
        "status": "proposed",
        "shown_to_user": True,
        "amount": amount,
        "category": category,
    }


def make_tools(
    repository: ExpenseRepository,
    *,
    currency: str = "CAD",
    documents: list[Document] | None = None,
    flipp: Flipp | None = None,
) -> list[Callable]:
    """Build the agent's tool set, bound to one user's data.

    `documents` collects files the agent generates. A tool can only return
    JSON, so the bytes are put here and the caller sends them.

    The deal tools are only included when `flipp` is supplied. Without a
    key they could only ever fail, and a tool that always fails is worse
    than one the model never sees.
    """
    produced = documents if documents is not None else []

    def list_categories() -> dict:
        """List every category available to this user.

        Includes the platform's shared categories and any the user has added.
        Call this before proposing an expense if you are unsure whether a
        category already exists.

        Returns:
            categories: each with a name and a scope of "platform" or "user".
        """
        return {
            "categories": [
                {"name": category.name, "scope": category.scope}
                for category in repository.categories()
            ]
        }

    def query_expenses(
        category: str = "",
        merchant: str = "",
        text: str = "",
        date_from: str = "",
        date_to: str = "",
        min_amount: str = "",
        max_amount: str = "",
        limit: int = 20,
    ) -> dict:
        """Look up the user's recorded expenses. Read-only.

        Every filter is optional and they combine. Leave one as an empty string
        to ignore it. Results come back newest first.

        Args:
            category: Exact category name, case-insensitive. For example "Dining".
            merchant: Part of a merchant name, case-insensitive. "tim" matches
                "Tim Hortons #2841".
            text: Free text matched against the merchant and the note.
            date_from: Earliest date to include, YYYY-MM-DD, inclusive.
            date_to: Latest date to include, YYYY-MM-DD, inclusive.
            min_amount: Smallest amount to include, as a decimal string.
            max_amount: Largest amount to include, as a decimal string.
            limit: Maximum number of expenses to return. Defaults to 20.

        Returns:
            count, total, and the matching expenses. On bad input, an `error`
            explaining which argument was wrong.
        """
        try:
            query = ExpenseQuery(
                category=category or None,
                merchant=merchant or None,
                text=text or None,
                date_from=_as_date(date_from, "date_from"),
                date_to=_as_date(date_to, "date_to"),
                min_amount=_as_decimal(min_amount, "min_amount"),
                max_amount=_as_decimal(max_amount, "max_amount"),
                limit=limit,
            )
        except ValueError as error:
            # Returned rather than raised: the agent can correct itself and
            # try again, where an exception would just end the turn.
            return {"error": str(error)}

        matching = repository.query(query)
        total = sum((expense.amount for expense in matching), Decimal("0"))

        return {
            "count": len(matching),
            "total": f"{total:.2f}",
            "expenses": [_as_dict(expense) for expense in matching],
        }

    def export_expenses(
        format: str = "xlsx",
        group_by: str = "",
        filename: str = "",
        include_chart: bool = True,
        category: str = "",
        merchant: str = "",
        text: str = "",
        date_from: str = "",
        date_to: str = "",
        min_amount: str = "",
        max_amount: str = "",
        limit: int = 500,
    ) -> dict:
        """Build a spreadsheet or CSV of the user's expenses and send it to them.

        Use this when the user asks for a file, a report, a spreadsheet, an
        export, or something they can open in Excel. The same filters as
        query_expenses apply, so you can export any subset.

        Choose the format from what they asked for: "xlsx" for a report they
        will read (it carries formatting, totals and a chart), "csv" when they
        want raw data to import somewhere else. Default to "xlsx".

        Args:
            format: "xlsx" or "csv".
            group_by: "category", "month" or "merchant" to add totals per
                group, or empty for a plain list of expenses. Grouping also
                adds a chart to a spreadsheet.
            filename: Always set this. A short descriptive name, no extension,
                saying what the export holds and for when -- "september dining",
                "groceries 2026", "expenses over 50". The user will scroll past
                this filename in their chat history later, so "expenses" is a
                poor choice when something specific fits.
            include_chart: Whether a grouped spreadsheet gets a chart.
            category: Exact category name, case-insensitive.
            merchant: Part of a merchant name, case-insensitive.
            text: Free text matched against merchant and note.
            date_from: Earliest date, YYYY-MM-DD, inclusive.
            date_to: Latest date, YYYY-MM-DD, inclusive.
            min_amount: Smallest amount, as a decimal string.
            max_amount: Largest amount, as a decimal string.
            limit: Maximum expenses to include.

        Returns:
            What the file contains, or an `error` to explain to the user.
        """
        if format not in FORMATS:
            return {"error": f"format must be xlsx or csv, got {format!r}"}
        if group_by and group_by not in GROUPINGS:
            return {
                "error": f"group_by must be category, month or merchant, got {group_by!r}"
            }

        try:
            query = ExpenseQuery(
                category=category or None,
                merchant=merchant or None,
                text=text or None,
                date_from=_as_date(date_from, "date_from"),
                date_to=_as_date(date_to, "date_to"),
                min_amount=_as_decimal(min_amount, "min_amount"),
                max_amount=_as_decimal(max_amount, "max_amount"),
                limit=limit,
            )
        except ValueError as error:
            return {"error": str(error)}

        matching = repository.query(query)
        if not matching:
            # An empty spreadsheet is worse than an explanation.
            return {"error": "No expenses matched, so there is nothing to export."}

        if format == "csv":
            data = build_csv(matching, group_by=group_by)
        else:
            data = build_xlsx(
                matching,
                currency=currency,
                group_by=group_by,
                include_chart=include_chart,
            )

        total = sum((expense.amount for expense in matching), Decimal(0))
        name = f"{_safe_name(filename) or 'expenses'}.{format}"
        produced.append(Document(filename=name, data=data, caption=""))

        return {
            "status": "sent",
            "filename": name,
            "rows": len(matching),
            "total": f"{total:.2f}",
        }

    def where_to_search(given: str) -> str:
        """The postal code to search with.

        What the model passed if it passed anything -- the user may be
        asking about somewhere they are visiting -- otherwise the one the
        user gave once and we kept. Raises when there is neither, so the
        agent knows to ask rather than spending a credit on a guess.
        """
        if given.strip():
            code = normalise(given)
            if code is None:
                raise ValueError(
                    f"{given!r} is not a Canadian postal code. Ask the user "
                    "for one, like M5V 2T6."
                )
            return code

        stored = repository.postal_code()
        if not stored:
            raise ValueError(
                "No postal code on file. Ask the user for their Canadian "
                "postal code, then call remember_postal_code."
            )
        return stored

    async def remember_postal_code(postal_code: str) -> dict:
        """Remember the user's postal code so they are never asked again.

        Call this the first time the user tells you their postal code, and
        again if they say they have moved. Once it is stored, the deal tools
        use it on their own and you should stop asking.

        Args:
            postal_code: A Canadian postal code, like "M5V 2T6". This bot
                is Canada-only; a US ZIP is not accepted.

        Returns:
            The postal code as stored, or an `error` if it was not one.
        """
        code = normalise(postal_code)
        if code is None:
            return {
                "error": (
                    f"{postal_code!r} is not a Canadian postal code. This bot "
                    "only covers Canada -- ask for one like M5V 2T6."
                )
            }

        repository.set_postal_code(code)
        return {"status": "remembered", "postal_code": code}

    async def search_deals(
        query: str, postal_code: str = "", limit: int = 10
    ) -> dict:
        """Search this week's store flyers for something on sale near the user.

        Use this when the user asks what is on sale, what is cheap this week,
        where something is cheapest, or whether a price is any good. Read-only,
        and unrelated to the expenses they have recorded.

        Args:
            query: What to look for, one or two words. For example "chicken",
                "olive oil", "diapers".
            postal_code: Leave this out. The user's own postal code is used
                automatically once they have given it. Pass one only when
                they ask about somewhere else, as a Canadian postal code
                like "M5V 2T6". Never invent one.
            limit: Most deals to return. Defaults to 10.

        Returns:
            total_matching and the deals -- each with its price, the merchant,
            the day the offer ends, and a flyer_id for list_flyer_items. On
            failure, an `error` to pass on to the user.
        """
        try:
            # Resolved before the call: a bad or missing code would only
            # spend a credit to be rejected.
            where = where_to_search(postal_code)
        except ValueError as error:
            return {"error": str(error)}

        try:
            body = await flipp.search_deals(query, where)
        except FlippError as error:
            # Returned rather than raised, like the other tools, so the agent
            # can tell the user what went wrong instead of ending its turn.
            return {"error": str(error)}

        items = body.get("items") or []
        return {
            "total_matching": body.get("total", len(items)),
            "postal_code": body.get("postal_code", where),
            "deals": [_as_deal(item) for item in items[:limit]],
        }

    async def list_weekly_ads(
        postal_code: str = "", merchant_name: str = "", limit: int = 20
    ) -> dict:
        """List the store flyers running near the user this week.

        Use this when the user asks which shops have a flyer out, or wants to
        browse one store rather than search for a product. Each flyer comes
        back with a flyer_id you can pass to list_flyer_items.

        Args:
            postal_code: Leave this out. The user's own postal code is used
                automatically once they have given it. Pass a Canadian
                postal code only when they ask about somewhere else.
            merchant_name: Part of a retailer name to narrow the list, such as
                "loblaws". Empty string for every flyer, which is well over a
                hundred in a city -- filter unless the user really wants all
                of them.
            limit: Most flyers to return. Defaults to 20.

        Returns:
            total_nearby and the flyers, each with its name, categories and a
            flyer_id for list_flyer_items. On failure, an `error` to pass on
            to the user.
        """
        try:
            where = where_to_search(postal_code)
        except ValueError as error:
            return {"error": str(error)}

        try:
            body = await flipp.weekly_ads(where, merchant_name)
        except FlippError as error:
            return {"error": str(error)}

        flyers = body.get("flyers") or []
        return {
            "total_nearby": body.get("total", len(flyers)),
            "flyers": [_as_flyer(flyer) for flyer in flyers[:limit]],
        }

    async def list_flyer_items(flyer_id: int, limit: int = 25) -> dict:
        """Read the sale items in one store flyer.

        Use this after list_weekly_ads or search_deals has given you a
        flyer_id, when the user wants to see what else is on sale at that shop.

        Args:
            flyer_id: The flyer to read, from list_weekly_ads or search_deals.
                The items carry no merchant of their own -- the flyer is the
                shop, so say which flyer you read.
            limit: Most items to return. Defaults to 25. A flyer can run to
                hundreds of items, so narrow down what the user wants rather
                than raising this.

        Returns:
            total_in_flyer and the items, or an `error` to pass on to the user.
        """
        try:
            body = await flipp.flyer_items(flyer_id)
        except FlippError as error:
            return {"error": str(error)}

        items = body.get("items") or []
        return {
            "flyer_id": flyer_id,
            "total_in_flyer": body.get("total", len(items)),
            "items": [_as_flyer_item(item) for item in items[:limit]],
        }

    tools = [propose_expense, list_categories, query_expenses, export_expenses]
    if flipp is not None:
        tools += [
            search_deals,
            list_weekly_ads,
            list_flyer_items,
            remember_postal_code,
        ]
    return tools


def _as_dict(expense: Expense) -> dict:
    """JSON-safe view of an expense. Decimal and date do not serialise."""
    return {
        "date": expense.date.isoformat(),
        "amount": str(expense.amount),
        "category": expense.category,
        "merchant": expense.merchant,
        "note": expense.note,
    }


def _as_date(value: str, field: str) -> Date | None:
    if not value:
        return None
    try:
        return Date.fromisoformat(value)
    except ValueError:
        raise ValueError(
            f"{field} must be a date like 2026-09-12, got {value!r}"
        ) from None


def _as_decimal(value: str, field: str) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(
            f"{field} must be a number like 45.20, got {value!r}"
        ) from None


def _safe_name(name: str) -> str:
    """A filename built from the model's suggestion, with nothing surprising in it."""
    kept = [
        character if character.isalnum() else "-"
        for character in name.strip().casefold()
    ]
    collapsed = "-".join(part for part in "".join(kept).split("-") if part)
    return collapsed[:60]


def _as_deal(item: dict) -> dict:
    """A flyer deal, cut down to what is worth spending context on.

    The image url is the one worth naming: a search returns dozens of items and
    every url is tokens the model can do nothing with.
    """
    return {
        "name": item.get("name", ""),
        "merchant": item.get("merchant_name", ""),
        "price": _price_text(item),
        "was": _was(item),
        "deal": item.get("sale_story") or "",
        "category": item.get("category_l2") or item.get("category_l1") or "",
        "valid_to": _day(item.get("valid_to", "")),
        "flyer_id": item.get("flyer_id"),
    }


def _as_flyer(flyer: dict) -> dict:
    """One weekly ad. Note `merchant`, not `merchant_name` as a deal has."""
    return {
        "flyer_id": flyer.get("flyer_id"),
        "merchant": flyer.get("merchant", ""),
        # Flyer titles run to "Weekly Savings" or plain "Flyer", and the
        # categories are what separates a grocery flyer from a furniture one.
        "name": flyer.get("name", ""),
        "categories": flyer.get("categories") or [],
        "valid_from": _day(flyer.get("valid_from", "")),
        "valid_to": _day(flyer.get("valid_to", "")),
    }


def _as_flyer_item(item: dict) -> dict:
    """One item inside a flyer.

    A different shape from a search result, despite the shared name: a
    single `price` already formatted as a string, no pre-sale price, and no
    merchant -- the flyer is the shop.
    """
    return {
        "name": item.get("name", ""),
        "brand": item.get("brand") or "",
        "price": str(item.get("price") or ""),
        "valid_to": _day(item.get("valid_to", "")),
    }


def _price_text(item: dict) -> str:
    """The price with the words the flyer prints around it.

    "5.99" on its own is a lie when the flyer says "2 for 5.99 /lb", and the
    model cannot recover the qualifiers once they have been dropped.
    """
    parts = [
        _note(item.get("pre_price_text")),
        _amount(item.get("current_price")),
        _note(item.get("post_price_text")),
    ]
    return " ".join(part for part in parts if part)


def _note(text) -> str:
    """A price qualifier, if that is what it is.

    Retailers also use these fields for marketing copy -- one Costco item
    ships "Available for Same-Day delivery at a higher price." as its
    post-price text. Glued onto a number that reads as a unit, so anything
    longer than a unit is dropped.
    """
    text = (text or "").strip()
    return text if len(text) <= MAX_PRICE_NOTE else ""


def _was(item: dict) -> str:
    """The pre-sale price, or nothing when the item is not marked down."""
    current, original = item.get("current_price"), item.get("original_price")
    if current is None or original is None or original <= current:
        return ""
    return _amount(original)


def _amount(value) -> str:
    """Two decimal places, from whatever JSON gave us."""
    if value is None:
        return ""
    return f"{Decimal(str(value)):.2f}"


def _day(timestamp: str) -> str:
    """The date out of an ISO timestamp. The agent never needs the time."""
    return timestamp.split("T")[0] if timestamp else ""
