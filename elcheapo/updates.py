"""Reading the parts of a Telegram update that the transport layer needs."""


def chat_id_of(update: dict) -> int | None:
    """The chat an update belongs to, whatever kind of update it is."""
    for key in ("message", "edited_message", "channel_post"):
        chat = (update.get(key) or {}).get("chat") or {}
        if "id" in chat:
            return chat["id"]

    callback_message = (update.get("callback_query") or {}).get("message") or {}
    chat = callback_message.get("chat") or {}
    return chat.get("id")
