"""Print the chat ids of everyone who has messaged the bot recently.

    uv run python -m elcheapo.whoami

Stop the dev bot first -- Telegram allows only one poller per token, and the
dev loop consumes updates as it reads them.
"""

import asyncio

from elcheapo.channels.telegram.client import TelegramBot
from elcheapo.config import Settings
from elcheapo.updates import chat_id_of


async def run() -> None:
    bot = TelegramBot(Settings().telegram_bot_token)
    try:
        updates = await bot.get_updates(timeout=0)
    except Exception as error:  # noqa: BLE001
        print(f"could not read updates: {error}")
        print("is the dev bot still running? only one poller per token is allowed.")
        return
    finally:
        await bot.aclose()

    seen: dict[int, str] = {}
    for update in updates:
        chat_id = chat_id_of(update)
        if chat_id is None:
            continue
        sender = (update.get("message") or {}).get("from") or (
            update.get("callback_query") or {}
        ).get("from") or {}
        name = " ".join(
            part for part in (sender.get("first_name"), sender.get("last_name")) if part
        )
        seen[chat_id] = name or sender.get("username") or "unknown"

    if not seen:
        print("No messages waiting.")
        print("Send your bot a message in Telegram, then run this again.")
        print("(Updates already read by the dev bot are gone -- send a fresh one.)")
        return

    print("Chat ids that have messaged the bot:\n")
    for chat_id, name in seen.items():
        print(f"  {chat_id}   {name}")
    print("\nPut this in .env:\n")
    print(f"ALLOWED_CHAT_IDS={','.join(str(chat_id) for chat_id in seen)}")


if __name__ == "__main__":
    asyncio.run(run())
