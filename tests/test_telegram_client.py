import httpx
import pytest

from elcheapo.channels.telegram.client import TelegramBot, redact

# Shaped like a real bot token, but invented. Never put a live token in a
# test -- tests get committed.
TOKEN = "1234567890:TEST-TOKEN-NOT-A-REAL-CREDENTIAL-000000"


def test_a_token_is_removed_from_text():
    message = f"Client error '409 Conflict' for url 'https://api.telegram.org/bot{TOKEN}/getUpdates'"

    assert TOKEN not in redact(message, TOKEN)


def test_the_rest_of_the_message_survives_redaction():
    message = f"Client error '409 Conflict' for url 'https://api.telegram.org/bot{TOKEN}/getUpdates'"

    redacted = redact(message, TOKEN)

    assert "409 Conflict" in redacted
    assert "getUpdates" in redacted


def test_redaction_copes_with_an_empty_token():
    assert redact("nothing secret here", "") == "nothing secret here"


async def test_a_failing_call_never_names_the_token():
    """A leaked token is a compromised bot, and HTTP errors carry the URL."""

    def always_conflict(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"ok": False, "description": "Conflict"})

    bot = TelegramBot(
        TOKEN, client=httpx.AsyncClient(transport=httpx.MockTransport(always_conflict))
    )

    with pytest.raises(Exception) as caught:
        await bot.get_updates()

    assert TOKEN not in str(caught.value)
    await bot.aclose()


async def test_an_api_level_failure_also_hides_the_token():
    def not_ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": False, "description": f"bad token {TOKEN}"}
        )

    bot = TelegramBot(
        TOKEN, client=httpx.AsyncClient(transport=httpx.MockTransport(not_ok))
    )

    with pytest.raises(RuntimeError) as caught:
        await bot.get_me()

    assert TOKEN not in str(caught.value)
    await bot.aclose()
