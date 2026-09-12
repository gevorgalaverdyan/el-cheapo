"""The only path that writes an expense to the workbook.

The agent cannot reach this module. It runs solely from an Accept callback,
which means every row in the spreadsheet was confirmed by a human.
"""

from dataclasses import dataclass
from datetime import datetime

from elcheapo.models import Draft, Expense
from elcheapo.sheets.repository import SheetsRepository


@dataclass(frozen=True)
class CommitResult:
    committed: bool
    duplicate: bool = False


def commit_expense(draft: Draft, repo: SheetsRepository, *, now: datetime) -> CommitResult:
    """Append `draft` as an expense, creating its category first if needed.

    Safe to retry: a draft already present in the sheet is a no-op, so a
    double-tapped Accept or a replayed Telegram webhook cannot duplicate a row.
    """
    if draft.draft_id in repo.recent_draft_ids():
        return CommitResult(committed=False, duplicate=True)

    category = _resolve_category(draft.category, repo)

    repo.append_expense(
        Expense(
            date=draft.date,
            amount=draft.amount,
            category=category,
            merchant=draft.merchant,
            note=draft.note,
            source=draft.source,
            logged_at=now,
            draft_id=draft.draft_id,
        )
    )
    return CommitResult(committed=True)


def _resolve_category(name: str, repo: SheetsRepository) -> str:
    """Return the canonical category name, creating it if it does not exist.

    Creation happens before the expense is appended so the sheet's validation
    range always already contains the value being written.
    """
    wanted = name.strip()
    for existing in repo.categories():
        if existing.name.strip().casefold() == wanted.casefold():
            return existing.name

    repo.add_category(wanted)
    return wanted
