"""Create the Postgres schema and the shared platform categories.

    uv run python -m elcheapo.seed

Idempotent -- every statement is CREATE IF NOT EXISTS or ON CONFLICT DO
NOTHING, so running it again changes nothing.
"""

from elcheapo.config import Settings
from elcheapo.store.postgres import create_engine
from elcheapo.store.schema import create_schema, seed_platform_categories


def run() -> None:
    settings = Settings()

    engine = create_engine(settings.database_url)

    create_schema(engine)
    print("schema applied")

    created = seed_platform_categories(engine)
    if created:
        print(f"created {created} platform categories")
    else:
        print("platform categories already present")


if __name__ == "__main__":
    run()
