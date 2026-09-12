"""Resolving which user's data a given chat reads and writes.

The Telegram chat id is the account id, and `for_chat` is the only place
that knows it. Nothing above this seam has ever seen one, so real accounts
can arrive here later without disturbing any caller.
"""

from typing import Protocol

from elcheapo.store.repository import ExpenseRepository


class Repositories(Protocol):
    def for_chat(self, chat_id: int) -> ExpenseRepository:
        """The data belonging to this chat."""
        ...


class SingleUserRepositories:
    """One store, shared by every chat. Used by the tests and the receipt
    harness; the running bot uses PostgresRepositories."""

    def __init__(self, repository: ExpenseRepository):
        self._repository = repository

    def for_chat(self, chat_id: int) -> ExpenseRepository:
        return self._repository
