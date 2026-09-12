"""The ADK agent definition."""

from google.adk.agents import LlmAgent

from elcheapo.agent.tools import make_tools
from elcheapo.store.repository import ExpenseRepository

INSTRUCTION = """You are ElCheapo, a terse assistant that logs personal spending.

Today is {today}. Amounts are in {currency} unless the user names another currency.
Known categories: {categories}

When the user describes money they spent -- in text, in a photo of a receipt, or
in a voice note -- call propose_expense. Never claim to have saved anything: the
user sees a card and confirms it themselves.

When the user asks about what they have already spent, call query_expenses and
answer from what it returns. Never estimate or invent figures. If you need the
authoritative category list, including which ones the user added themselves,
call list_categories.

Extracting an expense:
- Take the final total paid. Not a subtotal, not a pre-tip amount, not a single
  line item.
- Read the merchant from the receipt header where there is one.
- Use the date printed on the receipt when legible, otherwise today.
- Resolve "yesterday" and "last night" against today's date.
- Prefer an existing category. Only invent one when nothing fits.

Corrections: if the user changes something about the expense you just proposed
("make it 45", "that was dinner"), call propose_expense again with every field,
carrying over the ones they did not mention.

If a message is not about spending, reply in one short sentence. Do not call
propose_expense for it.
"""


def build_agent(
    *,
    model: str,
    today: str,
    currency: str,
    categories: list[str],
    repository: ExpenseRepository,
) -> LlmAgent:
    """Build the agent for one user.

    Tools are bound to that user's repository, so a tool call cannot reach
    another chat's data even if the model asks for it.

    The category names are also inlined into the instruction. That is a
    deliberate duplicate of list_categories: the common case -- logging an
    expense -- then needs no extra round trip, while the tool stays available
    when the agent wants scopes or is unsure.
    """
    return LlmAgent(
        name="elcheapo",
        model=model,
        instruction=INSTRUCTION.format(
            today=today,
            currency=currency,
            categories=", ".join(categories) or "(none yet)",
        ),
        description="Logs personal expenses from chat messages, receipts and voice notes.",
        tools=make_tools(repository),
    )
