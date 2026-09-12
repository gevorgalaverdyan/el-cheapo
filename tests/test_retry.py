import pytest

from elcheapo.retry import is_transient, with_retries


class Boom(Exception):
    def __init__(self, code=None, message=""):
        super().__init__(message or f"error {code}")
        self.code = code


async def never_sleeps(_seconds: float) -> None:
    return None


async def test_a_successful_call_is_not_retried():
    calls = []

    async def operation():
        calls.append(1)
        return "ok"

    assert await with_retries(operation, sleep=never_sleeps) == "ok"
    assert len(calls) == 1


async def test_a_transient_failure_is_retried_until_it_succeeds():
    calls = []

    async def operation():
        calls.append(1)
        if len(calls) < 3:
            raise Boom(code=503)
        return "ok"

    assert await with_retries(operation, attempts=3, sleep=never_sleeps) == "ok"
    assert len(calls) == 3


async def test_it_gives_up_after_the_attempt_limit():
    calls = []

    async def operation():
        calls.append(1)
        raise Boom(code=503)

    with pytest.raises(Boom):
        await with_retries(operation, attempts=3, sleep=never_sleeps)

    assert len(calls) == 3


async def test_a_permanent_failure_is_not_retried():
    calls = []

    async def operation():
        calls.append(1)
        raise Boom(code=400, message="bad request")

    with pytest.raises(Boom):
        await with_retries(operation, attempts=3, sleep=never_sleeps)

    assert len(calls) == 1


async def test_backoff_grows_between_attempts():
    delays = []

    async def record(seconds: float) -> None:
        delays.append(seconds)

    async def operation():
        raise Boom(code=503)

    with pytest.raises(Boom):
        await with_retries(operation, attempts=3, base_delay=1.0, sleep=record)

    assert delays == [1.0, 2.0]


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_server_and_rate_limit_codes_are_transient(code):
    assert is_transient(Boom(code=code)) is True


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_client_errors_are_permanent(code):
    assert is_transient(Boom(code=code)) is False


def test_an_unavailable_message_is_transient_even_without_a_code():
    assert is_transient(Exception("503 UNAVAILABLE. high demand")) is True
