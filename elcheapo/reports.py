"""Turning expenses into files a person can open.

Two formats, because they answer different asks. CSV is for "give me the raw
data" -- it imports anywhere. XLSX is for "show me a report" -- formatting,
totals and a chart, readable on a phone without importing anything.

Grouping is optional and orthogonal: an ungrouped export is the detail rows, a
grouped one adds totals per category, month or merchant.
"""

import csv
import io
from collections import OrderedDict
from decimal import Decimal
from typing import Callable, Iterable

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from elcheapo.models import Expense

DETAIL_HEADERS = ["date", "amount", "category", "merchant", "note", "source"]

GROUPINGS: dict[str, Callable[[Expense], str]] = {
    "category": lambda expense: expense.category,
    "month": lambda expense: expense.date.strftime("%Y-%m"),
    "merchant": lambda expense: expense.merchant or "(none)",
}

HEADER_FILL = PatternFill("solid", fgColor="1F3B4D")
HEADER_FONT = Font(bold=True, color="FFFFFF")
MONEY_FORMAT = '#,##0.00'


def group_totals(
    expenses: Iterable[Expense], group_by: str
) -> "OrderedDict[str, tuple[int, Decimal]]":
    """Count and total per group, largest total first."""
    key = GROUPINGS[group_by]

    totals: dict[str, tuple[int, Decimal]] = {}
    for expense in expenses:
        name = key(expense)
        count, total = totals.get(name, (0, Decimal("0")))
        totals[name] = (count + 1, total + expense.amount)

    return OrderedDict(
        sorted(totals.items(), key=lambda item: item[1][1], reverse=True)
    )


def build_csv(expenses: list[Expense], group_by: str = "") -> bytes:
    """A CSV of the detail rows, or of the group totals when grouping."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)

    if group_by:
        writer.writerow([group_by, "count", "total"])
        for name, (count, total) in group_totals(expenses, group_by).items():
            writer.writerow([name, count, f"{total:.2f}"])
    else:
        writer.writerow(DETAIL_HEADERS)
        for expense in expenses:
            writer.writerow(
                [
                    expense.date.isoformat(),
                    f"{expense.amount:.2f}",
                    expense.category,
                    expense.merchant,
                    expense.note,
                    expense.source,
                ]
            )

    # BOM so Excel opens UTF-8 correctly on Windows instead of mangling accents.
    return buffer.getvalue().encode("utf-8-sig")


def build_workbook(
    expenses: list[Expense],
    *,
    currency: str,
    group_by: str = "",
    include_chart: bool = True,
) -> Workbook:
    """The report as a Workbook, so charts can be inspected before saving."""
    book = Workbook()
    detail = book.active
    detail.title = "Expenses"

    _write_header(detail, DETAIL_HEADERS)
    for expense in expenses:
        detail.append(
            [
                expense.date,
                # A float, not a string: text amounts cannot be summed, which
                # would defeat the point of sending a spreadsheet.
                float(expense.amount),
                expense.category,
                expense.merchant,
                expense.note,
                expense.source,
            ]
        )

    for row in detail.iter_rows(min_row=2, min_col=1, max_col=1):
        row[0].number_format = "yyyy-mm-dd"
    for row in detail.iter_rows(min_row=2, min_col=2, max_col=2):
        row[0].number_format = MONEY_FORMAT

    detail.freeze_panes = "A2"
    _fit_columns(detail)

    if group_by:
        _add_summary(book, expenses, group_by, currency, include_chart)

    return book


def build_xlsx(
    expenses: list[Expense],
    *,
    currency: str,
    group_by: str = "",
    include_chart: bool = True,
) -> bytes:
    book = build_workbook(
        expenses, currency=currency, group_by=group_by, include_chart=include_chart
    )
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _add_summary(
    book: Workbook,
    expenses: list[Expense],
    group_by: str,
    currency: str,
    include_chart: bool,
) -> None:
    sheet = book.create_sheet(f"By {group_by}")
    _write_header(sheet, [group_by, "count", f"total ({currency})"])

    totals = group_totals(expenses, group_by)
    for name, (count, total) in totals.items():
        sheet.append([name, count, float(total)])

    for row in sheet.iter_rows(min_row=2, min_col=3, max_col=3):
        row[0].number_format = MONEY_FORMAT

    sheet.freeze_panes = "A2"
    _fit_columns(sheet)

    if not include_chart or not totals:
        return

    # A pie reads proportions; months are a series over time, so bars.
    chart = BarChart() if group_by == "month" else PieChart()
    chart.title = f"Spend by {group_by}"
    chart.height, chart.width = 9, 16
    chart.add_data(
        Reference(sheet, min_col=3, min_row=1, max_row=sheet.max_row), titles_from_data=True
    )
    chart.set_categories(
        Reference(sheet, min_col=1, min_row=2, max_row=sheet.max_row)
    )
    sheet.add_chart(chart, "E2")


def _write_header(sheet, headers: list[str]) -> None:
    sheet.append(headers)
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="left")


def _fit_columns(sheet) -> None:
    for index, column in enumerate(sheet.iter_cols(), start=1):
        widest = max((len(str(cell.value or "")) for cell in column), default=0)
        sheet.column_dimensions[get_column_letter(index)].width = min(
            max(widest + 2, 10), 40
        )
