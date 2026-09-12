"""Canadian postal codes.

The bot is Canada-only. Flipp will happily answer a US ZIP with US flyers and
US prices, which is worse than refusing: the user gets plausible deals at shops
they cannot walk into. So a ZIP is rejected here rather than passed through.
"""

import re

# A1A 1A1, with the separator optional. Deliberately not the full rule --
# Canada Post excludes D, F, I, O, Q and U from some positions -- because the
# only cost of letting one impossible code through is an empty result.
PATTERN = re.compile(r"^([A-Z]\d[A-Z])[ -]?(\d[A-Z]\d)$")


def normalise(code: str) -> str | None:
    """A postal code in its printed form, or None if it is not one.

    Accepts what people actually type -- "m5v2t6", "M5V-2T6", a stray space --
    and returns "M5V 2T6".
    """
    match = PATTERN.match((code or "").strip().upper())
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"
