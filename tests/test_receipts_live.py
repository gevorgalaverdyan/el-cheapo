"""Accuracy checks against the receipt fixtures. Calls the real model.

Deselected by default -- it costs tokens and depends on a live service.

    uv run pytest -m live -v

One model call per fixture, paced to stay inside the free tier's 15 requests
per minute. For a readable expected-vs-actual table instead of pass/fail, use
tests/fixtures/check_receipts.py.

Regenerate the fixtures with: uv run python tests/fixtures/make_receipts.py
"""

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest

from elcheapo.agent.proposer import AgentProposer
from elcheapo.config import Settings
from elcheapo.models import Attachment
from elcheapo.repositories import SingleUserRepositories
from elcheapo.store.memory import InMemoryRepository

RECEIPTS = Path(__file__).parent / "fixtures" / "receipts"
MANIFEST = json.loads((RECEIPTS / "manifest.json").read_text(encoding="utf-8"))

# Free tier allows 15 requests per minute; 4.5s keeps a margin.
SECONDS_BETWEEN_CALLS = 4.5

pytestmark = pytest.mark.live


@pytest.fixture
def proposer() -> AgentProposer:
    settings = Settings()
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY is not set")
    # Function-scoped: the SDK's transport binds to the event loop that created
    # it, and pytest-asyncio gives each test a fresh loop.
    return AgentProposer(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        repositories=SingleUserRepositories(InMemoryRepository()),
        currency=settings.currency,
        timezone=settings.timezone,
    )


@pytest.mark.parametrize("entry", MANIFEST, ids=lambda e: e["file"])
async def test_a_receipt_is_read_correctly(proposer, entry):
    """One call per fixture, asserting everything the manifest claims."""
    await asyncio.sleep(SECONDS_BETWEEN_CALLS)

    data = (RECEIPTS / entry["file"]).read_bytes()
    draft = await proposer.propose(
        text="",
        chat_id=1,
        attachment=Attachment(data=data, mime_type=entry["mime_type"]),
    )

    expect = entry["expect"]
    context = f"{entry['file']}: {entry['tests']}"

    if expect["amount"] is None:
        assert draft is None, f"{context} -- expected nothing, got {draft}"
        return

    assert draft is not None, f"{context} -- expected {expect['amount']}, got nothing"
    assert draft.amount == Decimal(expect["amount"]), context
    assert draft.category.strip(), f"{context} -- every expense needs a category"

    if expect["merchant"]:
        # Suffixes vary ("Loblaws" vs "LOBLAWS #1204"), so this asks whether
        # the name is in there, not whether it matches exactly.
        want = expect["merchant"].casefold()
        got = draft.merchant.casefold()
        assert want in got or (got and got in want), f"{context} -- got {draft.merchant!r}"

    if expect["date"]:
        assert draft.date.isoformat() == expect["date"], context
