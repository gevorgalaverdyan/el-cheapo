"""Postgres storage.

Postgres does everything the query language needs natively: ILIKE for merchant
substrings, several range filters at once, exact NUMERIC money, and ordering.
Unlike a document store, nothing has to be re-filtered in Python.

The connection is a plain URL, so the same code runs against the local Docker
container and against any managed Postgres later.
"""

import logging
from datetime import date as Date
from decimal import Decimal

import sqlalchemy
from sqlalchemy import text

from elcheapo.models import Category, Expense, ExpenseQuery, Task

log = logging.getLogger(__name__)


ASYNC_DRIVER = "postgresql+asyncpg://"


def async_url(database_url: str) -> str:
    """The same database, addressed with an async driver.

    The app talks to Postgres synchronously through pg8000, but ADK's session
    store wants an async engine, and pg8000 cannot provide one. Both point at
    the same database -- only the driver differs.
    """
    for prefix in ("postgresql+pg8000://", "postgresql+psycopg2://", "postgresql://"):
        if database_url.startswith(prefix):
            return ASYNC_DRIVER + database_url[len(prefix) :]

    if database_url.startswith(ASYNC_DRIVER):
        return database_url

    raise ValueError(f"not a Postgres URL: {database_url!r}")


def create_engine(database_url: str) -> sqlalchemy.engine.Engine:
    """Build a pooled engine for `database_url`."""
    return sqlalchemy.create_engine(
        database_url,
        pool_size=2,
        max_overflow=2,
        # Recycles a connection the container closed while the bot sat idle,
        # instead of surfacing it as a failed message.
        pool_pre_ping=True,
        pool_recycle=1800,
    )


class PostgresRepository:
    """One user's categories and expenses."""

    def __init__(self, engine: sqlalchemy.engine.Engine, uid: str):
        self._engine = engine
        self._uid = uid

    # --- reads ----------------------------------------------------------

    def categories(self) -> list[Category]:
        rows = self._fetch(
            """
            SELECT name, emoji, scope, monthly_budget
            FROM categories
            WHERE uid IS NULL OR uid = :uid
            ORDER BY scope DESC, lower(name)
            """,
            {"uid": self._uid},
        )
        # scope DESC puts 'platform' before 'user' alphabetically, which is the
        # order list_categories promises. Deterministic matters: this list goes
        # into the model's prompt.
        return [
            Category(
                name=row.name,
                emoji=row.emoji or "",
                scope=row.scope,
                monthly_budget=row.monthly_budget,
            )
            for row in rows
        ]

    def recent_draft_ids(self, limit: int = 200) -> set[str]:
        rows = self._fetch(
            """
            SELECT draft_id FROM expenses
            WHERE uid = :uid
            ORDER BY logged_at DESC
            LIMIT :limit
            """,
            {"uid": self._uid, "limit": limit},
        )
        return {row.draft_id for row in rows}

    def query(self, query: ExpenseQuery) -> list[Expense]:
        clauses = ["uid = :uid"]
        params: dict = {"uid": self._uid, "limit": query.limit}

        if query.category:
            clauses.append("lower(category) = lower(:category)")
            params["category"] = query.category
        if query.merchant:
            clauses.append("merchant ILIKE :merchant")
            params["merchant"] = f"%{query.merchant}%"
        if query.text:
            clauses.append("(merchant || ' ' || note) ILIKE :text")
            params["text"] = f"%{query.text}%"
        if query.date_from:
            clauses.append("date >= :date_from")
            params["date_from"] = query.date_from
        if query.date_to:
            clauses.append("date <= :date_to")
            params["date_to"] = query.date_to
        if query.min_amount is not None:
            clauses.append("amount >= :min_amount")
            params["min_amount"] = query.min_amount
        if query.max_amount is not None:
            clauses.append("amount <= :max_amount")
            params["max_amount"] = query.max_amount

        rows = self._fetch(
            f"""
            SELECT date, amount, category, merchant, note, source,
                   logged_at, draft_id
            FROM expenses
            WHERE {" AND ".join(clauses)}
            ORDER BY date DESC, logged_at DESC
            LIMIT :limit
            """,
            params,
        )
        return [_to_expense(row) for row in rows]

    def postal_code(self) -> str | None:
        rows = self._fetch(
            "SELECT postal_code FROM user_settings WHERE uid = :uid",
            {"uid": self._uid},
        )
        return rows[0].postal_code if rows else None

    def tasks(self, include_complete: bool = False) -> list[Task]:
        rows = self._fetch(
            f"""
            SELECT task_id, task, is_complete, created_at, updated_at
            FROM todos
            WHERE uid = :uid{"" if include_complete else " AND NOT is_complete"}
            ORDER BY created_at, task_id
            """,
            {"uid": self._uid},
        )
        return [_to_task(row) for row in rows]

    # --- writes ---------------------------------------------------------

    def add_category(self, name: str) -> None:
        self._execute(
            """
            INSERT INTO categories (uid, name, scope)
            VALUES (:uid, :name, 'user')
            ON CONFLICT DO NOTHING
            """,
            {"uid": self._uid, "name": name},
        )

    def set_postal_code(self, code: str) -> None:
        # One row per user, so a second answer overwrites the first rather
        # than leaving two codes with no way to tell which is current.
        self._execute(
            """
            INSERT INTO user_settings (uid, postal_code)
            VALUES (:uid, :postal_code)
            ON CONFLICT (uid) DO UPDATE
                SET postal_code = EXCLUDED.postal_code,
                    updated_at = now()
            """,
            {"uid": self._uid, "postal_code": code},
        )

    def add_task(self, task: str) -> Task:
        # RETURNING so the generated id and timestamps come back in the
        # same round trip, rather than being read again afterwards.
        rows = self._returning(
            """
            INSERT INTO todos (uid, task)
            VALUES (:uid, :task)
            RETURNING task_id, task, is_complete, created_at, updated_at
            """,
            {"uid": self._uid, "task": task},
        )
        return _to_task(rows[0])

    def update_task(
        self,
        task_id: str,
        *,
        task: str | None = None,
        is_complete: bool | None = None,
    ) -> Task | None:
        # COALESCE leaves a column alone when its parameter is NULL, so one
        # statement covers renaming, completing, and both at once.
        # The uid in the WHERE clause is what stops one chat editing
        # another's task by guessing an id.
        rows = self._returning(
            """
            UPDATE todos
               SET task = COALESCE(:task, task),
                   is_complete = COALESCE(:is_complete, is_complete),
                   updated_at = now()
             WHERE uid = :uid AND task_id = :task_id
            RETURNING task_id, task, is_complete, created_at, updated_at
            """,
            {
                "uid": self._uid,
                "task_id": task_id,
                "task": task,
                "is_complete": is_complete,
            },
        )
        return _to_task(rows[0]) if rows else None

    def append_expense(self, expense: Expense) -> None:
        # ON CONFLICT DO NOTHING makes a replayed Accept a no-op rather than a
        # duplicate row or an error.
        self._execute(
            """
            INSERT INTO expenses
                (draft_id, uid, date, amount, category, merchant, note,
                 source, logged_at)
            VALUES
                (:draft_id, :uid, :date, :amount, :category, :merchant, :note,
                 :source, :logged_at)
            ON CONFLICT (draft_id) DO NOTHING
            """,
            {
                "draft_id": expense.draft_id,
                "uid": self._uid,
                "date": expense.date,
                "amount": expense.amount,
                "category": expense.category,
                "merchant": expense.merchant,
                "note": expense.note,
                "source": expense.source,
                "logged_at": expense.logged_at,
            },
        )

    # --- internals ------------------------------------------------------

    def _fetch(self, sql: str, params: dict):
        with self._engine.connect() as connection:
            return connection.execute(text(sql), params).fetchall()

    def _execute(self, sql: str, params: dict) -> None:
        with self._engine.begin() as connection:
            connection.execute(text(sql), params)

    def _returning(self, sql: str, params: dict):
        """A write that hands rows back. Committed, unlike _fetch."""
        with self._engine.begin() as connection:
            return connection.execute(text(sql), params).fetchall()


class PostgresRepositories:
    """Resolves a chat to its own repository."""

    def __init__(self, engine: sqlalchemy.engine.Engine):
        self._engine = engine

    def for_chat(self, chat_id: int) -> PostgresRepository:
        # The Telegram chat id is the account id until real accounts exist.
        # Nothing above this seam ever sees it.
        return PostgresRepository(self._engine, str(chat_id))


def _to_task(row) -> Task:
    return Task(
        task_id=str(row.task_id),
        task=row.task,
        is_complete=row.is_complete,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_expense(row) -> Expense:
    return Expense(
        date=row.date if isinstance(row.date, Date) else Date.fromisoformat(str(row.date)),
        amount=Decimal(str(row.amount)),
        category=row.category,
        merchant=row.merchant or "",
        note=row.note or "",
        source=row.source,
        logged_at=row.logged_at,
        draft_id=row.draft_id,
    )
