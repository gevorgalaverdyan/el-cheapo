from datetime import datetime, timedelta, timezone

import pytest

from elcheapo.agent.conversations import Conversations

START = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, now: datetime = START):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def conversations(clock) -> Conversations:
    return Conversations(idle_timeout=timedelta(minutes=15), clock=clock)


def test_the_first_message_opens_a_session(conversations):
    assert conversations.session_for(111)


def test_a_prompt_reply_stays_in_the_same_session(conversations, clock):
    first = conversations.session_for(111)
    clock.advance(minutes=1)

    assert conversations.session_for(111) == first


def test_a_message_after_the_idle_window_starts_a_new_session(conversations, clock):
    first = conversations.session_for(111)
    clock.advance(minutes=16)

    assert conversations.session_for(111) != first


def test_a_message_exactly_on_the_boundary_still_continues(conversations, clock):
    first = conversations.session_for(111)
    clock.advance(minutes=15)

    assert conversations.session_for(111) == first


def test_each_message_extends_the_window(conversations, clock):
    """The window is idle time, not total conversation length.

    A ten-minute back-and-forth must not be cut off halfway through.
    """
    first = conversations.session_for(111)
    for _ in range(5):
        clock.advance(minutes=10)
        assert conversations.session_for(111) == first


def test_resetting_starts_a_new_session_immediately(conversations):
    first = conversations.session_for(111)

    conversations.reset(111)

    assert conversations.session_for(111) != first


def test_resetting_a_chat_that_never_spoke_is_harmless(conversations):
    conversations.reset(999)

    assert conversations.session_for(999)


def test_resetting_twice_does_not_error(conversations):
    conversations.reset(111)
    conversations.reset(111)

    assert conversations.session_for(111)


def test_chats_do_not_share_sessions(conversations):
    assert conversations.session_for(111) != conversations.session_for(222)


def test_resetting_one_chat_leaves_another_alone(conversations):
    other = conversations.session_for(222)

    conversations.reset(111)

    assert conversations.session_for(222) == other


def test_a_session_id_is_stable_across_repeated_reads(conversations):
    assert conversations.session_for(111) == conversations.session_for(111)
