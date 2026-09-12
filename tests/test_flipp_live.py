"""Checks the Flipp wrapper against the real API. Calls a live service.

Deselected by default -- every call spends a credit, and the free tier only
has 200 of them.

    uv run pytest -m live tests/test_flipp_live.py -v

These exist because the client was written from published documentation. A
field renamed upstream would leave every mocked test green while the bot
quietly answered with blanks, so something has to look at the real shape.
"""

import asyncio

import pytest

from elcheapo.agent.tools import _as_deal, _as_flyer, _as_flyer_item
from elcheapo.config import Settings
from elcheapo.flipp import Flipp

# Downtown Toronto; the app's default locale is Canadian.
POSTAL_CODE = "M5V 2T6"

# Free tier allows 5 requests a minute; 13s keeps a margin.
SECONDS_BETWEEN_CALLS = 13.0

pytestmark = pytest.mark.live


@pytest.fixture
def flipp() -> Flipp:
    settings = Settings()
    if not settings.flipp_api:
        pytest.skip("FLIPP_API is not set")
    # Function-scoped: httpx binds its transport to the loop that created it,
    # and pytest-asyncio gives each test a fresh loop.
    return Flipp(settings.flipp_api)


async def test_a_real_search_comes_back_with_deals(flipp):
    body = await flipp.search_deals("chicken", POSTAL_CODE)

    assert body["items"], "no deals returned -- has the response shape changed?"
    await flipp.aclose()


async def test_a_real_deal_still_has_the_fields_the_agent_is_shown(flipp):
    body = await flipp.search_deals("milk", POSTAL_CODE)
    await asyncio.sleep(SECONDS_BETWEEN_CALLS)

    deal = _as_deal(body["items"][0])

    assert deal["name"]
    assert deal["merchant"]
    assert deal["price"]
    assert deal["flyer_id"]
    await flipp.aclose()


async def test_a_real_flyer_can_be_read_from_a_weekly_ad(flipp):
    ads = await flipp.weekly_ads(POSTAL_CODE)
    assert ads["flyers"], "no flyers returned -- has the response shape changed?"
    flyer = _as_flyer(ads["flyers"][0])
    assert flyer["merchant"], "a flyer with no merchant -- was the field renamed?"
    await asyncio.sleep(SECONDS_BETWEEN_CALLS)

    body = await flipp.flyer_items(flyer["flyer_id"])

    assert body["items"], "flyer had no items -- has the response shape changed?"
    item = _as_flyer_item(body["items"][0])
    assert item["name"]
    assert item["price"], "a flyer item with no price -- was the field renamed?"
    await flipp.aclose()
