"""The agent's wiring. A tool built but never handed over is invisible."""

import pytest

from elcheapo.agent.agent import build_agent
from elcheapo.store.memory import InMemoryRepository
from tests.fakes import FakeFlipp


class OneRepository:
    """The Repositories protocol, for a bot with a single chat."""

    def __init__(self, postal_code: str = ""):
        self._repository = InMemoryRepository(categories=["Groceries"])
        if postal_code:
            self._repository.set_postal_code(postal_code)

    def for_chat(self, chat_id: int):
        return self._repository


def an_agent(flipp=None, postal_code=None):
    return build_agent(
        model="gemini-3.5-flash-lite",
        today="2026-09-12",
        currency="CAD",
        categories=["Groceries"],
        repository=InMemoryRepository(categories=["Groceries"]),
        flipp=flipp,
        postal_code=postal_code,
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


def test_a_known_postal_code_is_put_in_the_instruction_rather_than_asked_for():
    """The whole point of storing it: the agent starts every turn knowing it."""
    instruction = an_agent(flipp=FakeFlipp(), postal_code="M5V 2T6").instruction

    assert "M5V 2T6" in instruction


def test_an_agent_that_does_not_know_the_postal_code_is_told_how_to_keep_it():
    instruction = an_agent(flipp=FakeFlipp()).instruction

    assert "remember_postal_code" in instruction


def test_an_agent_that_knows_the_postal_code_is_not_told_to_ask_for_one():
    """Asking again for something already on file is the bug being fixed."""
    known = an_agent(flipp=FakeFlipp(), postal_code="M5V 2T6").instruction
    unknown = an_agent(flipp=FakeFlipp()).instruction

    assert "ask for it once" in unknown.casefold()
    assert "ask for it once" not in known.casefold()


async def test_the_proposer_gives_the_agent_the_stored_postal_code(monkeypatch):
    from datetime import timedelta

    from elcheapo.agent import proposer as proposer_module
    from elcheapo.agent.proposer import AgentProposer

    seen = {}

    def record(**kwargs):
        seen.update(kwargs)
        raise Recorded

    monkeypatch.setattr(proposer_module, "build_agent", record)

    subject = AgentProposer(
        api_key="",
        model="gemini-3.5-flash-lite",
        repositories=OneRepository(postal_code="M5V 2T6"),
        currency="CAD",
        timezone="America/Toronto",
        idle_timeout=timedelta(minutes=15),
        flipp=FakeFlipp(),
    )

    with pytest.raises(Recorded):
        await subject.propose(text="what is on sale", chat_id=1)

    assert seen["postal_code"] == "M5V 2T6"


def test_the_instruction_covers_the_todo_list_even_without_a_flipp_key():
    """The todo tools are always built, so the prompt must always describe them."""
    instruction = an_agent().instruction

    assert "add_task" in instruction
    assert "list_tasks" in instruction


def test_the_instruction_keeps_tasks_and_expenses_apart():
    """"Remember to pay rent" is a task; it is not money that has been spent."""
    instruction = an_agent().instruction.casefold()

    assert "not an expense" in instruction or "not expenses" in instruction


def test_the_instruction_covers_budgets():
    instruction = an_agent().instruction

    assert "set_budget" in instruction
    assert "budget_status" in instruction
