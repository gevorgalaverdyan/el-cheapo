from datetime import date
from decimal import Decimal

import pytest

from elcheapo.channels.telegram.payload import PayloadError, decode_payload, encode_payload
from elcheapo.models import Draft


def a_draft(**overrides) -> Draft:
    fields = dict(
        draft_id="7k2m9x",
        amount=Decimal("45.20"),
        category="Groceries",
        is_new_category=False,
        merchant="Seoudi",
        note="weekly shop",
        date=date(2026, 9, 12),
        source="image",
    )
    fields.update(overrides)
    return Draft(**fields)


def test_round_trip_preserves_every_field():
    draft = a_draft()

    restored = decode_payload(encode_payload(draft))

    assert restored == draft


def test_amount_survives_as_exact_decimal():
    draft = a_draft(amount=Decimal("0.10"))

    restored = decode_payload(encode_payload(draft))

    assert restored.amount == Decimal("0.10")


def test_decode_rejects_an_unknown_schema_version():
    encoded = encode_payload(a_draft()).replace("#d1.", "#d99.")

    with pytest.raises(PayloadError):
        decode_payload(encoded)
