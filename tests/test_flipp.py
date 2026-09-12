import httpx
import pytest

from elcheapo.flipp import Flipp, FlippError

# Invented. Never put a live key in a test -- tests get committed.
KEY = "pb-TEST-KEY-NOT-A-REAL-CREDENTIAL-0000"


def flipp_answering(handler) -> Flipp:
    return Flipp(KEY, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def recording(data: dict):
    """A transport that answers with `data`, enveloped as the API does,
    and keeps the request it was given."""
    seen: dict = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json={"status": "success", "data": data})

    return handle, seen


async def test_searching_deals_sends_the_query_and_postal_code():
    handle, seen = recording({"items": [], "total": 0})
    flipp = flipp_answering(handle)

    await flipp.search_deals("chicken", "M5V 2T6")

    request = seen["request"]
    assert request.url.path.endswith("/search_deals")
    assert request.url.params["query"] == "chicken"
    assert request.url.params["postal_code"] == "M5V 2T6"


async def test_every_call_carries_the_api_key_header():
    handle, seen = recording({"items": [], "total": 0})
    flipp = flipp_answering(handle)

    await flipp.search_deals("milk", "95054")

    assert seen["request"].headers["X-API-Key"] == KEY


async def test_the_success_envelope_is_unwrapped():
    """The real API wraps every answer in {"status", "data"}; callers
    should see the payload, not the packaging."""
    handle, _ = recording({"items": [{"name": "Whole Chicken"}], "total": 1})
    flipp = flipp_answering(handle)

    body = await flipp.search_deals("chicken", "95054")

    assert body["items"] == [{"name": "Whole Chicken"}]
    assert body["total"] == 1


async def test_a_failure_reported_inside_a_200_is_still_a_failure():
    """The scraper answers 200 with status "error" rather than a 4xx."""

    def failed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"status": "error", "message": "unknown flyer"}
        )

    flipp = flipp_answering(failed)

    with pytest.raises(FlippError) as caught:
        await flipp.flyer_items(1)

    assert "unknown flyer" in str(caught.value)


async def test_weekly_ads_leaves_out_a_merchant_filter_that_was_not_given():
    handle, seen = recording({"flyers": [], "total": 0})
    flipp = flipp_answering(handle)

    await flipp.weekly_ads("95054")

    assert seen["request"].url.path.endswith("/get_weekly_ads")
    assert "merchant_name" not in seen["request"].url.params


async def test_weekly_ads_passes_a_merchant_filter_when_given():
    handle, seen = recording({"flyers": [], "total": 0})
    flipp = flipp_answering(handle)

    await flipp.weekly_ads("95054", merchant_name="loblaws")

    assert seen["request"].url.params["merchant_name"] == "loblaws"


async def test_flyer_items_sends_the_flyer_id():
    handle, seen = recording({"items": [], "total": 0})
    flipp = flipp_answering(handle)

    await flipp.flyer_items(7788)

    assert seen["request"].url.path.endswith("/get_flyer_items")
    assert seen["request"].url.params["flyer_id"] == "7788"


async def test_a_failing_call_never_names_the_api_key():
    """A leaked key is someone else spending our credits."""

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": f"bad key {KEY}"})

    flipp = flipp_answering(unauthorized)

    with pytest.raises(FlippError) as caught:
        await flipp.search_deals("chicken", "95054")

    assert KEY not in str(caught.value)


async def test_being_rate_limited_says_so_in_plain_words():
    """The free tier is 5 requests a minute, so this is the expected failure."""

    def too_many(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "slow down"})

    flipp = flipp_answering(too_many)

    with pytest.raises(FlippError) as caught:
        await flipp.search_deals("chicken", "95054")

    assert "rate limit" in str(caught.value).casefold()


async def test_a_missing_key_fails_before_any_request_is_made():
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should have been sent")

    flipp = Flipp("", client=httpx.AsyncClient(transport=httpx.MockTransport(explode)))

    with pytest.raises(FlippError):
        await flipp.search_deals("chicken", "95054")
