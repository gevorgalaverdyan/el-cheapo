"""Thin async wrapper over the Telegram Bot API."""

import httpx

API_ROOT = "https://api.telegram.org"
REDACTED = "<bot-token>"


def redact(message: str, token: str) -> str:
    """Remove a bot token from text.

    Every Bot API call carries the token in its URL, so any HTTP error message
    quotes it verbatim. Left alone it ends up in terminals, log aggregators and
    bug reports -- and a leaked token is a compromised bot.
    """
    if not token:
        return message
    return message.replace(token, REDACTED)


class TelegramError(RuntimeError):
    """A Bot API call failed. Never carries the token."""


class TelegramBot:
    def __init__(self, token: str, client: httpx.AsyncClient | None = None):
        self._token = token
        self._client = client or httpx.AsyncClient(timeout=60.0)

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> dict:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._call("sendMessage", payload)

    async def edit_message_text(
        self, chat_id: int, message_id: int, text: str, reply_markup: dict | None = None
    ) -> None:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            # An absent reply_markup leaves the old keyboard in place, so an
            # empty one is sent explicitly to clear the buttons off a resolved card.
            "reply_markup": reply_markup if reply_markup is not None else {"inline_keyboard": []},
        }
        await self._call("editMessageText", payload)

    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        await self._call(
            "answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text}
        )

    async def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict]:
        payload: dict = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        return await self._call("getUpdates", payload)

    async def get_me(self) -> dict:
        return await self._call("getMe", {})

    async def download(self, file_id: str) -> bytes:
        info = await self._call("getFile", {"file_id": file_id})
        try:
            response = await self._client.get(
                f"{API_ROOT}/file/bot{self._token}/{info['file_path']}"
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise TelegramError(redact(str(error), self._token)) from None
        return response.content

    async def _call(self, method: str, payload: dict):
        try:
            response = await self._client.post(
                f"{API_ROOT}/bot{self._token}/{method}", json=payload
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise TelegramError(redact(str(error), self._token)) from None

        body = response.json()
        if not body.get("ok"):
            raise TelegramError(
                redact(f"telegram {method} failed: {body.get('description')}", self._token)
            )
        return body["result"]

    async def aclose(self) -> None:
        await self._client.aclose()
