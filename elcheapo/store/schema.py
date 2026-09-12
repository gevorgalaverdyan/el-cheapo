"""The Postgres schema, and the platform categories that seed it.

Applied by `uv run python -m elcheapo.seed`. Every statement is idempotent, so
running it against an existing database changes nothing.
"""

from sqlalchemy import text

PLATFORM_CATEGORIES = [
    "Groceries",
    "Dining",
    "Transport",
    "Utilities",
    "Rent",
    "Health",
    "Shopping",
    "Entertainment",
    "Travel",
    "Subscriptions",
    "Other",
]

STATEMENTS = [
    # Platform categories have uid IS NULL and are shared by everyone.
    """
    CREATE TABLE IF NOT EXISTS categories (
        id             BIGSERIAL PRIMARY KEY,
        uid            TEXT,
        name           TEXT NOT NULL,
        emoji          TEXT NOT NULL DEFAULT '',
        scope          TEXT NOT NULL CHECK (scope IN ('platform', 'user')),
        monthly_budget NUMERIC(12, 2),
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # A user cannot hold two categories differing only by case, and the
    # platform list is likewise unique. COALESCE gives NULL uids one bucket,
    # since NULLs never collide in a plain unique index.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS categories_owner_name_key
        ON categories (COALESCE(uid, ''), lower(name))
    """,
    # draft_id is the primary key: accepting the same card twice conflicts
    # instead of writing a second row.
    """
    CREATE TABLE IF NOT EXISTS expenses (
        draft_id   TEXT PRIMARY KEY,
        uid        TEXT NOT NULL,
        date       DATE NOT NULL,
        amount     NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
        category   TEXT NOT NULL,
        merchant   TEXT NOT NULL DEFAULT '',
        note       TEXT NOT NULL DEFAULT '',
        source     TEXT NOT NULL CHECK (source IN ('text', 'image', 'voice')),
        logged_at  TIMESTAMPTZ NOT NULL
    )
    """,
    # Every query is scoped to one user and ordered newest first.
    """
    CREATE INDEX IF NOT EXISTS expenses_uid_date_idx
        ON expenses (uid, date DESC, logged_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS expenses_uid_category_idx
        ON expenses (uid, lower(category))
    """,
]

SEED_CATEGORY = text(
    """
    INSERT INTO categories (uid, name, scope)
    VALUES (NULL, :name, 'platform')
    ON CONFLICT DO NOTHING
    """
)


def create_schema(engine) -> None:
    """Create tables and indexes if they are not already there."""
    with engine.begin() as connection:
        for statement in STATEMENTS:
            connection.execute(text(statement))


def seed_platform_categories(engine) -> int:
    """Insert the shared categories. Returns how many were new."""
    with engine.begin() as connection:
        before = connection.execute(
            text("SELECT count(*) FROM categories WHERE uid IS NULL")
        ).scalar_one()

        for name in PLATFORM_CATEGORIES:
            connection.execute(SEED_CATEGORY, {"name": name})

        after = connection.execute(
            text("SELECT count(*) FROM categories WHERE uid IS NULL")
        ).scalar_one()

    return after - before
