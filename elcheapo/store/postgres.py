"""Cloud SQL (Postgres) storage.

Connections go through the Cloud SQL Python Connector, which authenticates
with the service account and tunnels over TLS -- so no database IP has to be
exposed and no network has to be allow-listed.

Postgres does everything the query language needs natively: ILIKE for merchant
substrings, several range filters at once, and ordering. Unlike a document
store, nothing has to be re-filtered in Python.
"""

import logging
from datetime import date as Date
from decimal import Decimal

import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes
from google.oauth2 import service_account
from sqlalchemy import text

from elcheapo.models import Category, Expense, ExpenseQuery

log = logging.getLogger(__name__)


def create_engine(
    *, instance: str, database: str, user: str, password: str, credentials_path: str
) -> sqlalchemy.engine.Engine:
    """Build a pooled engine that dials Cloud SQL through the connector."""
    connector = Connector(
        credentials=service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        ),
        ip_type=IPTypes.PUBLIC,
    )

    def connect():
        return connector.connect(
            instance, "pg8000", user=user, password=password, db=database
        )

    return sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=connect,
        pool_size=2,
        max_overflow=2,
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


class PostgresRepositories:
    """Resolves a chat to its own repository."""

    def __init__(self, engine: sqlalchemy.engine.Engine):
        self._engine = engine

    def for_chat(self, chat_id: int) -> PostgresRepository:
        # The Telegram chat id is the account id until real accounts exist.
        # Nothing above this seam ever sees it.
        return PostgresRepository(self._engine, str(chat_id))


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
