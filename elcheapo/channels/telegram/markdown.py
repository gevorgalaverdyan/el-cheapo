"""Rendering the agent's prose as Telegram HTML.

Every message goes out with parse_mode HTML, which suits the cards -- they are
built as HTML from the start. The agent's free text is not: models write
Markdown, so `**Metro**` arrived as literal asterisks.

Escaping is the load-bearing half. Telegram rejects a message whose markup it
cannot parse, so one unescaped `<` loses the whole reply, not just its
formatting -- and the flyer data is full of merchants like "M&M Food Market".

Only the subset models actually reach for is converted. Single-asterisk and
underscore emphasis are deliberately left alone: `* eggs` is a bullet far more
often than emphasis, and `remember_postal_code` is not italic.
"""

import re
from html import escape

FENCED = re.compile(r"```(?:\w+\n)?(.*?)```", re.DOTALL)
INLINE_CODE = re.compile(r"`([^`\n]+)`")
BOLD = re.compile(r"\*\*(\S.*?)\*\*")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def to_html(text: str) -> str:
    """Telegram-safe HTML for a message the model wrote.

    Escapes first, then converts, so nothing the user or a merchant name
    contains can introduce markup of its own.
    """
    if not text:
        return ""

    rendered = escape(text, quote=False)
    # Before the inline form, so a fence is not read as two empty code spans.
    rendered = FENCED.sub(lambda m: f"<pre>{m.group(1).strip()}</pre>", rendered)
    rendered = INLINE_CODE.sub(r"<code>\1</code>", rendered)
    rendered = HEADING.sub(r"<b>\1</b>", rendered)
    rendered = BOLD.sub(r"<b>\1</b>", rendered)
    return rendered
