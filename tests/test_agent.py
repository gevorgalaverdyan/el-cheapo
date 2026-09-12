"""The agent's wiring. A tool built but never handed over is invisible."""

import pytest

from elcheapo.agent.agent import build_agent
from elcheapo.store.memory import InMemoryRepository
from tests.fakes import FakeFlipp


class OneRepository:
    """The Repositories protocol, for a bot with a single chat."""

    def __init__(self):
        self._repository = InMemoryRepository(categories=["Groceries"])

    def for_chat(self, chat_id: int):
        return self._repository


def an_agent(flipp=None):
    return build_agent(
        model="gemini-3.5-flash-lite",
        today="2026-09-12",
        currency="CAD",
        categories=["Groceries"],
        repository=InMemoryRepository(categories=["Groceries"]),
        flipp=flipp,
    )


def tool_names(agent) -> set[str]:
    return {tool.__name__ for tool in agent.tools}


def test_the_deal_tools_reach_the_agent_when_flipp_is_configured():
    assert "search_deals" in tool_names(an_agent(flipp=FakeFlipp()))


def test_the_agent_has_no_deal_tools_without_a_flipp_client():
    assert "search_deals" not in tool_names(an_agent())


def test_the_expense_tools_are_there_either_way():
    assert "propose_expense" in tool_names(an_agent())
    assert "propose_expense" in tool_names(an_agent(flipp=FakeFlipp()))


def test_the_instruction_tells_the_agent_to_ask_for_a_postal_code():
    """It has no other way to get one, and a guessed postal code is wrong data."""
    assert "postal code" in an_agent(flipp=FakeFlipp()).instruction.casefold()


class Recorded(Exception):
    """Stops the turn once the agent has been built. Not a failure."""


async def test_the_proposer_hands_its_flipp_client_to_the_agent(monkeypatch):
    """Accepting the client and then not passing it on would silently drop
    every deal tool, with nothing failing to say so."""
    from datetime import timedelta

    from elcheapo.agent import proposer as proposer_module
    from elcheapo.agent.proposer import AgentProposer

    seen = {}

    def record(**kwargs):
        seen.update(kwargs)
        raise Recorded

    monkeypatch.setattr(proposer_module, "build_agent", record)

    flipp = FakeFlipp()
    subject = AgentProposer(
        api_key="",
        model="gemini-3.5-flash-lite",
        repositories=OneRepository(),
        currency="CAD",
        timezone="America/Toronto",
        idle_timeout=timedelta(minutes=15),
        flipp=flipp,
    )

    with pytest.raises(Recorded):
        await subject.propose(text="what is on sale", chat_id=1)

    assert seen["flipp"] is flipp
