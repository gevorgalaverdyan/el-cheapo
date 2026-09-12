"""Run the bot locally with long polling -- no public URL, no tunnel, no deploy.

Production uses the webhook in `elcheapo.main`. Both feed the same handler, so
what you exercise here is the real code path.

    uv run python -m elcheapo.dev_poll
"""

import asyncio
from datetime import timedelta

from elcheapo.agent.proposer import AgentProposer
from elcheapo.channels.telegram.client import TelegramBot
from elcheapo.config import Settings
from elcheapo.handler import ExpenseHandler
from google.adk.sessions import DatabaseSessionService

from elcheapo.store.postgres import PostgresRepositories, async_url, create_engine
from elcheapo.updates import chat_id_of


async def run() -> None:
    settings = Settings()
    bot = TelegramBot(settings.telegram_bot_token)

    me = await bot.get_me()
    print(f"connected as @{me['username']}")

    engine = create_engine(settings.database_url)
    try:
        with engine.connect():
            pass
    except Exception as error:  # noqa: BLE001
        print(f"\ncannot reach the database: {error}\n")
        print("Is the database running?  docker compose up -d")
        return
    print("database ready")

    repositories = PostgresRepositories(engine)
    # Conversations live in the same database as the expenses, so an open
    # card survives a restart instead of losing its context.
    sessions = DatabaseSessionService(db_url=async_url(settings.database_url))

    handler = ExpenseHandler(
        bot=bot,
        repositories=repositories,
        proposer=AgentProposer(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            repositories=repositories,
            currency=settings.currency,
            timezone=settings.timezone,
            idle_timeout=timedelta(minutes=settings.session_idle_minutes),
            session_service=sessions,
        ),
        currency=settings.currency,
    )

    if not settings.allowed_chat_ids:
        print("ALLOWED_CHAT_IDS is empty -- replying to anyone. Fine locally, not in production.")
    print("listening; send it a message\n")

    offset: int | None = None
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=30)
        except Exception as error:  # noqa: BLE001 - a dev loop should outlive a blip
            print(f"poll failed, retrying: {error}")
            await asyncio.sleep(3)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            chat_id = chat_id_of(update)

            if settings.allowed_chat_ids and chat_id not in settings.allowed_chat_ids:
                print(f"ignored chat {chat_id} (add it to ALLOWED_CHAT_IDS to permit)")
                continue
            if not settings.allowed_chat_ids:
                print(f"chat id {chat_id} -- put this in ALLOWED_CHAT_IDS")

            try:
                await handler.handle(update)
            except Exception as error:  # noqa: BLE001
                print(f"handling update {update['update_id']} failed: {error}")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nstopped")
