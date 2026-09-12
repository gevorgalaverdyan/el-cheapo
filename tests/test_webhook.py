from fastapi.testclient import TestClient

from elcheapo.config import Settings
from elcheapo.main import create_app

SECRET = "s3cret"
ALLOWED_CHAT = 111
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": SECRET}


class RecordingHandler:
    def __init__(self):
        self.updates: list[dict] = []

    async def handle(self, update: dict) -> None:
        self.updates.append(update)


def make_client() -> tuple[TestClient, RecordingHandler]:
    settings = Settings(
        _env_file=None,
        telegram_bot_token="token",
        telegram_webhook_secret=SECRET,
        allowed_chat_ids={ALLOWED_CHAT},
    )
    handler = RecordingHandler()
    return TestClient(create_app(settings=settings, handler=handler)), handler


def a_message_update(update_id: int = 1, chat_id: int = ALLOWED_CHAT) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 9,
            "chat": {"id": chat_id},
            "text": "lunch 40",
        },
    }


def a_callback_update(update_id: int = 1, chat_id: int = ALLOWED_CHAT) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cb1",
            "data": "acc:7k2m9x",
            "message": {"message_id": 9, "chat": {"id": chat_id}},
        },
    }


def test_an_update_without_the_secret_header_is_refused():
    client, handler = make_client()

    response = client.post("/telegram/webhook", json=a_message_update())

    assert response.status_code == 403
    assert handler.updates == []


def test_an_update_with_the_wrong_secret_is_refused():
    client, handler = make_client()

    response = client.post(
        "/telegram/webhook",
        json=a_message_update(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )

    assert response.status_code == 403
    assert handler.updates == []


def test_an_allowlisted_message_is_dispatched():
    client, handler = make_client()

    response = client.post("/telegram/webhook", json=a_message_update(), headers=HEADERS)

    assert response.status_code == 200
    assert len(handler.updates) == 1


def test_a_message_from_an_unknown_chat_is_ignored_without_error():
    client, handler = make_client()

    response = client.post(
        "/telegram/webhook", json=a_message_update(chat_id=999), headers=HEADERS
    )

    assert response.status_code == 200
    assert handler.updates == []


def test_a_callback_from_an_unknown_chat_is_ignored():
    client, handler = make_client()

    response = client.post(
        "/telegram/webhook", json=a_callback_update(chat_id=999), headers=HEADERS
    )

    assert response.status_code == 200
    assert handler.updates == []


def test_a_replayed_update_is_dispatched_only_once():
    client, handler = make_client()

    client.post("/telegram/webhook", json=a_message_update(update_id=7), headers=HEADERS)
    client.post("/telegram/webhook", json=a_message_update(update_id=7), headers=HEADERS)

    assert len(handler.updates) == 1


def test_distinct_updates_are_both_dispatched():
    client, handler = make_client()

    client.post("/telegram/webhook", json=a_message_update(update_id=7), headers=HEADERS)
    client.post("/telegram/webhook", json=a_message_update(update_id=8), headers=HEADERS)

    assert len(handler.updates) == 2


def test_a_handler_failure_returns_non_200_so_telegram_retries():
    class FailingHandler:
        async def handle(self, update: dict) -> None:
            raise RuntimeError("sheets unavailable")

    settings = Settings(
        _env_file=None,
        telegram_bot_token="token",
        telegram_webhook_secret=SECRET,
        allowed_chat_ids={ALLOWED_CHAT},
    )
    client = TestClient(
        create_app(settings=settings, handler=FailingHandler()), raise_server_exceptions=False
    )

    response = client.post("/telegram/webhook", json=a_message_update(), headers=HEADERS)

    assert response.status_code >= 500
