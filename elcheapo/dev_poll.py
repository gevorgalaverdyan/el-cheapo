"""Run the bot locally with long polling -- no public URL, no tunnel, no deploy.

Production uses the webhook in `elcheapo.main`. Both feed the same handler, so
what you exercise here is the real code path.

    uv run python -m elcheapo.dev_poll
"""

import asyncio

from elcheapo.agent.proposer import GeminiProposer
from elcheapo.channels.telegram.client import TelegramBot
from elcheapo.config import Settings
from elcheapo.handler import ExpenseHandler
from elcheapo.repositories import SingleUserRepositories
from elcheapo.sheets.memory import InMemorySheetsRepository
from elcheapo.updates import chat_id_of


async def run() -> None:
    settings = Settings()
    bot = TelegramBot(settings.telegram_bot_token)

    me = await bot.get_me()
    print(f"connected as @{me['username']}")

    repository = InMemorySheetsRepository()
    repositories = SingleUserRepositories(repository)

    handler = ExpenseHandler(
        bot=bot,
        repositories=repositories,
        proposer=GeminiProposer(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            categories_for=lambda chat_id: [
                category.name for category in repositories.for_chat(chat_id).categories()
            ],
            currency=settings.currency,
            timezone=settings.timezone,
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
