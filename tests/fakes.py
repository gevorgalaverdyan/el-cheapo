"""Test doubles. Nothing here ships."""

from elcheapo.models import AgentReply, Category, Expense, ExpenseQuery


class FakeExpenseRepository:
    """In-memory stand-in for the workbook, recording the order of writes."""

    def __init__(self, categories: list[str] | None = None):
        self._categories = [
            Category(name=name, scope="platform") for name in (categories or [])
        ]
        self.expenses: list[Expense] = []
        self.calls: list[str] = []
        self.append_failures = 0

    def categories(self) -> list[Category]:
        return list(self._categories)

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

    async def download(self, file_id: str) -> bytes:
        self.downloaded.append(file_id)
        if self.download_error is not None:
            raise self.download_error
        return self.files.get(file_id, b"fake-bytes")


class StubProposer:
    """Returns a fixed draft, so handler tests never touch a model."""

    def __init__(self, draft=None, error: Exception | None = None, reply: str = ""):
        self._draft = draft
        self._error = error
        self._reply = reply
        self.seen: list[str] = []
        self.attachments: list = []

    async def propose(self, *, text: str, chat_id: int, attachment=None):
        self.seen.append(text)
        self.attachments.append(attachment)
        if self._error is not None:
            raise self._error
        return AgentReply(draft=self._draft, text=self._reply)
