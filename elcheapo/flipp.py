"""Thin async wrapper over the Flipp weekly-ad API, via parse.bot.

Three read-only endpoints: search the flyers near a postal code, list the
flyers themselves, and read one flyer end to end. Every call costs a credit
and the free tier allows five a minute, so a 429 is an ordinary outcome here
rather than a surprise -- it gets its own message so the agent can tell the
user to wait rather than repeating the call.
"""

import httpx

API_ROOT = "https://api.parse.bot/scraper/a496e089-6377-4719-bec7-21aa74d15185"
REDACTED = "<flipp-key>"


def redact(message: str, key: str) -> str:
    """Remove an API key from text.

    Errors quote the request that failed, headers included. A leaked key is
    someone else spending our credits, and error text ends up in logs.
    """
    if not key:
        return message
    return message.replace(key, REDACTED)


class FlippError(RuntimeError):
    """A Flipp API call failed. Never carries the key."""


class Flipp:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def search_deals(self, query: str, postal_code: str) -> dict:
        """Sale items matching `query` in the flyers near `postal_code`."""
        return await self._get(
            "search_deals", {"query": query, "postal_code": postal_code}
        )

    async def weekly_ads(self, postal_code: str, merchant_name: str = "") -> dict:
        """Flyers currently running near `postal_code`."""
        params = {"postal_code": postal_code}
        if merchant_name:
            params["merchant_name"] = merchant_name
        return await self._get("get_weekly_ads", params)

    async def flyer_items(self, flyer_id: int) -> dict:
        """Every sale item in one flyer."""
        return await self._get("get_flyer_items", {"flyer_id": flyer_id})

    async def _get(self, path: str, params: dict) -> dict:
        if not self._key:
            raise FlippError("No Flipp API key is configured.")

        try:
            response = await self._client.get(
                f"{API_ROOT}/{path}",
                params=params,
                headers={"X-API-Key": self._key},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 429:
                raise FlippError(
                    "Flipp rate limit reached; wait a minute before asking again."
                ) from None
            raise FlippError(redact(str(error), self._key)) from None
        except httpx.HTTPError as error:
            raise FlippError(redact(str(error), self._key)) from None

        return _payload(response.json())

    async def aclose(self) -> None:
        await self._client.aclose()


def _payload(body) -> dict:
    """The data out of the API's envelope.

    Every answer arrives as {"status": ..., "data": {...}} -- failures
    included, which come back inside a 200 rather than as a 4xx. The
    published documentation shows the payload without the envelope, so
    this is the one place the two disagree.
    """
    if not isinstance(body, dict):
        raise FlippError("Flipp returned something that was not an object.")

    status = body.get("status")
    if status is not None and status != "success":
        detail = body.get("message") or body.get("error") or status
        raise FlippError(f"Flipp request failed: {detail}")

    data = body.get("data")
    return data if isinstance(data, dict) else body
