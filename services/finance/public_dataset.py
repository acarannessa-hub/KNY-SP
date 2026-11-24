"""
Public, analysis-ready dataset for the transparency dashboard (Looker Studio).

All four ledgers are combined into ONE table with the same columns, so any
chart (totals, income vs. expenses, monthly trends, breakdowns) can be built
from a single data source.

PRIVACY: this table is meant to be shown to the public. It deliberately
contains NO member names or IDs, reference numbers, notes, sponsor names,
payment methods or expense descriptions; those can identify people or
accounts (Data Privacy Act of 2012). Only the date, the kind of money
movement, its category and the amount are published.

Pure Python: no database, no Google.
"""

from .ledgers import LEDGERS

PUBLIC_TAB = "transactions"

PUBLIC_HEADERS = [
    "date",            # YYYY-MM-DD
    "year",            # 2026
    "quarter",         # 2026-Q1 (calendar quarter of the transaction date)
    "month",           # 2026-03
    "type",            # Income / Expense
    "source",          # Fundraising / Sponsorships / Membership Fees / Expenses
    "category",        # expense category; for income, the same as source
    "amount",          # always positive
    "signed_amount",   # income positive, expenses negative (for net cash flow)
]


def transaction_row(ledger_key, values):
    """One public row (list in PUBLIC_HEADERS order) from a ledger record's
    field values. Only the fields listed above are ever read."""
    ledger = LEDGERS[ledger_key]
    day = values[ledger.date_field]
    amount = float(values["amount"])
    is_expense = ledger.kind == "expense"

    if is_expense:
        category = values.get("category") or "Uncategorized"
    else:
        category = ledger.label

    return [
        day.isoformat(),
        day.year,
        f"{day.year}-Q{(day.month - 1) // 3 + 1}",
        f"{day.year}-{day.month:02d}",
        "Expense" if is_expense else "Income",
        ledger.label,
        category,
        amount,
        -amount if is_expense else amount,
    ]


def build_table(rows_by_ledger):
    """
    rows_by_ledger: {ledger_key: [values_dict, ...]}
    Returns [PUBLIC_HEADERS, row, row, ...] sorted by date, then source.
    """
    rows = [
        transaction_row(key, values)
        for key, records in rows_by_ledger.items()
        for values in records
    ]
    rows.sort(key=lambda row: (row[0], row[5]))
    return [list(PUBLIC_HEADERS)] + rows
