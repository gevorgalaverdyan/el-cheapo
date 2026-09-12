"""Test doubles. Nothing here ships."""

from elcheapo.models import AgentReply, Category, Expense, ExpenseQuery


class FakeExpenseRepository:
    """Stand-in for the store, recording the order of writes."""

    def __init__(self, categories: list[str] | None = None):
        self._categories = [
            Category(name=name, scope="platform") for name in (categories or [])
        ]
        self.expenses: list[Expense] = []
        self.calls: list[str] = []
        self.append_failures = 0
        self._budgets: dict = {}
        self._postal_code: str | None = None

    def categories(self) -> list[Category]:
        return [
            category.model_copy(
                update={"monthly_budget": self._budgets.get(category.name.casefold())}
            )
            for category in self._categories
        ]

    def set_budget(self, category, monthly_budget) -> None:
        self.calls.append(f"set_budget:{category}={monthly_budget}")
        if monthly_budget is None:
            self._budgets.pop(category.casefold(), None)
        else:
            self._budgets[category.casefold()] = monthly_budget

    def add_category(self, name: str) -> None:
        self.calls.append(f"add_category:{name}")
        self._categories.append(Category(name=name, scope="user"))

    def append_expense(self, expense: Expense) -> None:
        self.calls.append(f"append_expense:{expense.draft_id}")
        if self.append_failures:
            self.append_failures -= 1
            raise RuntimeError("sheets unavailable")
        self.expenses.append(expense)

    def recent_draft_ids(self, limit: int = 200) -> set[str]:
        return {expense.draft_id for expense in self.expenses[-limit:]}

    def tasks(self, include_complete: bool = False):
        return []

    def add_task(self, task: str):
        raise NotImplementedError("no handler test needs the todo list")

    def update_task(self, task_id, *, task=None, is_complete=None):
        return None

    def postal_code(self) -> str | None:
        return self._postal_code

    def set_postal_code(self, code: str) -> None:
        self.calls.append(f"set_postal_code:{code}")
        self._postal_code = code

    def query(self, query: ExpenseQuery) -> list[Expense]:
        matching = [e for e in self.expenses if query.matches(e)]
        matching.sort(key=lambda e: (e.date, e.logged_at), reverse=True)
        return matching[: query.limit]


class FakeTelegramBot:
    """Records outbound Telegram calls instead of making them."""

    def __init__(self):
        self.sent: list[dict] = []
        self.edited: list[dict] = []
        self.answered: list[str] = []
        self.documents: list[dict] = []
        self.downloaded: list[str] = []
        self.files: dict[str, bytes] = {}
        self.download_error: Exception | None = None

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> dict:
        self.sent.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )
        return {"message_id": 100 + len(self.sent)}

    async def edit_message_text(
        self, chat_id: int, message_id: int, text: str, reply_markup: dict | None = None
    ) -> None:
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )

    async def answer_callback_query(
        self, callback_query_id: str, text: str = ""
    ) -> None:
        self.answered.append(callback_query_id)

    async def send_document(
        self, chat_id: int, filename: str, data: bytes, caption: str = ""
    ) -> None:
        self.documents.append(
            {"chat_id": chat_id, "filename": filename, "data": data, "caption": caption}
        )

    async def download(self, file_id: str) -> bytes:
        self.downloaded.append(file_id)
        if self.download_error is not None:
            raise self.download_error
        return self.files.get(file_id, b"fake-bytes")


class StubProposer:
    """Returns a fixed draft, so handler tests never touch a model."""

    def __init__(self, draft=None, error: Exception | None = None, reply: str = "", document=None):
        self._draft = draft
        self._error = error
        self._reply = reply
        self._document = document
        self.seen: list[str] = []
        self.attachments: list = []
        self.resets: list[int] = []

    async def propose(self, *, text: str, chat_id: int, attachment=None):
        self.seen.append(text)
        self.attachments.append(attachment)
        if self._error is not None:
            raise self._error
        return AgentReply(
            draft=self._draft, text=self._reply, document=self._document
        )

    def reset(self, chat_id: int) -> None:
        self.resets.append(chat_id)


class FakeFlipp:
    """Canned Flipp responses, recording the calls made instead of making them."""

    def __init__(
        self,
        *,
        deals: dict | None = None,
        flyers: dict | None = None,
        items: dict | None = None,
        error: Exception | None = None,
    ):
        self._deals = deals or {"items": [], "total": 0}
        self._flyers = flyers or {"flyers": [], "total": 0}
        self._items = items or {"items": [], "total": 0}
        self.error = error
        self.calls: list[tuple] = []

    async def search_deals(self, query: str, postal_code: str) -> dict:
        self.calls.append(("search_deals", query, postal_code))
        return self._answer(self._deals)

    async def weekly_ads(self, postal_code: str, merchant_name: str = "") -> dict:
        self.calls.append(("weekly_ads", postal_code, merchant_name))
        return self._answer(self._flyers)

    async def flyer_items(self, flyer_id: int) -> dict:
        self.calls.append(("flyer_items", flyer_id))
        return self._answer(self._items)

    def _answer(self, body: dict) -> dict:
        if self.error:
            raise self.error
        return body
