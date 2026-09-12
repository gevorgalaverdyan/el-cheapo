"""Resolving which workbook a given chat writes to.

Today every chat resolves to the one workbook configured in the environment.
When accounts arrive, `for_chat` looks up that user's stored credentials and
spreadsheet id instead -- and nothing above this seam has to change, because
no caller has ever seen a spreadsheet id.
"""

from typing import Protocol

from elcheapo.store.repository import ExpenseRepository


class Repositories(Protocol):
    def for_chat(self, chat_id: int) -> ExpenseRepository:
        """The workbook belonging to this chat."""
        ...


class SingleUserRepositories:
    """One workbook, owned by the operator. The hackathon configuration."""

    def __init__(self, repository: ExpenseRepository):
        self._repository = repository

    def for_chat(self, chat_id: int) -> ExpenseRepository:
        return self._repository
