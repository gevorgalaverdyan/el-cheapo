"""HTTP entry point. Authenticates and filters updates, then dispatches them."""

from collections import deque
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException, Request, Response

from elcheapo.config import Settings
from elcheapo.updates import chat_id_of

SEEN_UPDATE_CAPACITY = 1000


class UpdateHandler(Protocol):
    async def handle(self, update: dict) -> None: ...


class SeenUpdates:
    """A bounded record of update ids already handled.

    Best-effort deduplication of Telegram's retries. It is a courtesy, not a
    guarantee -- the load-bearing protection against duplicate rows is the
    draft_id check in `commit_expense`.
    """

    def __init__(self, capacity: int = SEEN_UPDATE_CAPACITY):
        self._capacity = capacity
        self._order: deque[int] = deque()
        self._ids: set[int] = set()

    def __contains__(self, update_id: int) -> bool:
        return update_id in self._ids

    def add(self, update_id: int) -> None:
        if update_id in self._ids:
            return
        self._ids.add(update_id)
        self._order.append(update_id)
        if len(self._order) > self._capacity:
            self._ids.discard(self._order.popleft())


def create_app(*, settings: Settings, handler: UpdateHandler) -> FastAPI:
    app = FastAPI(title="elcheapo")
    seen = SeenUpdates()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @app.post("/telegram/webhook")
    async def telegram_webhook(
        request: Request,
        secret_token: str = Header("", alias="X-Telegram-Bot-Api-Secret-Token"),
    ) -> Response:
        if secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="bad secret token")

        update = await request.json()

        chat_id = chat_id_of(update)
        if chat_id not in settings.allowed_chat_ids:
            # Silently ignore: anyone who finds the bot can message it, and a
            # 200 stops Telegram retrying something we will never act on.
            return Response(status_code=200)

        update_id = update.get("update_id")
        if update_id in seen:
            return Response(status_code=200)

        # Handled synchronously: on scale-to-zero Cloud Run the container can be
        # frozen the moment a response is sent, which would kill background work.
        # A failure returns 5xx so Telegram retries, and the draft_id guard makes
        # that retry safe.
        await handler.handle(update)

        if update_id is not None:
            seen.add(update_id)
        return Response(status_code=200)

    return app
