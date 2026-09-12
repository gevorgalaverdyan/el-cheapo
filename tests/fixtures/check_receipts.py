"""Run every receipt fixture through the model and report what it extracted.

    uv run python tests/fixtures/check_receipts.py

Prints expected vs actual per fixture. Use this when tuning the prompt -- the
pytest version (tests/test_receipts_live.py) is for pass/fail in CI, this is
for seeing what actually happened.
"""

import asyncio
import json
from decimal import Decimal
from pathlib import Path

from elcheapo.agent.proposer import AgentProposer
from elcheapo.config import Settings
from elcheapo.models import Attachment
from elcheapo.repositories import SingleUserRepositories
from elcheapo.store.memory import InMemoryRepository

RECEIPTS = Path(__file__).parent / "receipts"

# The free tier allows 15 requests per minute. Without pacing, a 12-fixture
# run trips the quota partway through and reports model failures that are
# really rate limits.
SECONDS_BETWEEN_CALLS = 4.5


def tick(ok: bool | None) -> str:
    if ok is None:
        return " - "
    return " ok" if ok else "MISS"


async def main() -> None:
    settings = Settings()
    manifest = json.loads((RECEIPTS / "manifest.json").read_text(encoding="utf-8"))

    proposer = AgentProposer(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        repositories=SingleUserRepositories(InMemoryRepository()),
        currency=settings.currency,
        timezone=settings.timezone,
    )

    print(f"model: {settings.gemini_model}\n")
    header = f"{'fixture':<26} {'amt':>5} {'expected':>9} {'actual':>9}  {'merchant':<22} {'date':<11} category"
    print(header)
    print("-" * len(header))

    scores = {"amount": [0, 0], "merchant": [0, 0], "date": [0, 0]}

    for index, entry in enumerate(manifest):
        if index:
            await asyncio.sleep(SECONDS_BETWEEN_CALLS)
        data = (RECEIPTS / entry["file"]).read_bytes()
        try:
            draft = await proposer.propose(
                text="",
                chat_id=1,
                attachment=Attachment(data=data, mime_type=entry["mime_type"]),
            )
        except Exception as error:  # noqa: BLE001
            print(f"{entry['file']:<26} ERROR {type(error).__name__}: {str(error)[:90]}")
            continue

        expect = entry["expect"]

        want_amount = expect["amount"]
        got_amount = str(draft.amount) if draft else "none"
        amount_ok = (
            (draft is None) if want_amount is None
            else (draft is not None and draft.amount == Decimal(want_amount))
        )
        scores["amount"][1] += 1
        scores["amount"][0] += amount_ok

        merchant_ok = None
        if expect["merchant"] and draft:
            want = expect["merchant"].casefold()
            got = draft.merchant.casefold()
            merchant_ok = want in got or (got and got in want)
            scores["merchant"][1] += 1
            scores["merchant"][0] += bool(merchant_ok)

        date_ok = None
        if expect["date"] and draft:
            date_ok = draft.date.isoformat() == expect["date"]
            scores["date"][1] += 1
            scores["date"][0] += bool(date_ok)

        print(
            f"{entry['file']:<26} {tick(amount_ok):>5} "
            f"{(want_amount or 'none'):>9} {got_amount:>9}  "
            f"{((draft.merchant if draft else '') or '-')[:20]:<22} "
            f"{(draft.date.isoformat() if draft else '-'):<11} "
            f"{(draft.category if draft else '-')}"
        )

    print()
    for name, (hit, total) in scores.items():
        if total:
            print(f"{name:<9} {hit}/{total}")


if __name__ == "__main__":
    asyncio.run(main())
