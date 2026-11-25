"""
Public, analysis-ready datasets for the transparency dashboard (Looker Studio).

1. 'transactions': all four ledgers combined into ONE table with the same
   columns, so any chart (totals, income vs. expenses, monthly trends,
   breakdowns, per-activity results) comes from a single data source.
2. 'dues_summary': membership dues per quarter as TOTALS only (billed,
   collected, outstanding, collection rate).

PRIVACY: these tables are meant to be shown to the public. They contain NO
member names or IDs, payer / account names, reference numbers, notes,
sponsor names, payment methods or expense descriptions; those can identify
people or accounts (Data Privacy Act of 2012). Only dates, the kind of
money movement, its category, the activity (a public event name) and
amounts are published.

Pure Python: no database, no Google.
"""

from decimal import Decimal

from .ledgers import LEDGERS

PUBLIC_TAB = "transactions"

PUBLIC_HEADERS = [
    "date",            # YYYY-MM-DD
    "year",            # 2026
    "quarter",         # 2026-Q1 (calendar quarter of the transaction date)
    "month",           # 2026-03
    "type",            # Income / Expense
    "source",          # Fundraising / Sponsorships / Membership Fees / Expenses
    "category",        # expense category; income type; sponsor type
    "activity",        # event / project name ("" when not recorded)
    "amount",          # always positive
    "signed_amount",   # income positive, expenses negative (for net cash flow)
]

DUES_SUMMARY_HEADERS = [
    "period",                # 2026-Q1 (the dues period, not the payment date)
    "year",
    "quarter",               # Q1..Q4
    "members_billed",
    "members_paid_in_full",
    "members_partial",
    "members_unpaid",        # unpaid + deferred
    "total_due",
    "total_collected",
    "outstanding",
    "collection_rate",       # 0..1 (format as % in Looker Studio)
]


def _category(ledger_key, values):
    if ledger_key == "expenses":
        return values.get("category") or "Uncategorized"
    if ledger_key == "fundraising":
        return values.get("income_type") or "Fundraising"
    if ledger_key == "sponsorships":
        kind = values.get("sponsor_type")
        return f"Sponsorship ({kind})" if kind else "Sponsorship"
    return "Membership Fee"


def transaction_row(ledger_key, values):
    """One public row (list in PUBLIC_HEADERS order) from a ledger record's
    field values. Only the fields listed above are ever read."""
    ledger = LEDGERS[ledger_key]
    day = values[ledger.date_field]
    amount = float(values["amount"])
    is_expense = ledger.kind == "expense"
    return [
        day.isoformat(),
        day.year,
        f"{day.year}-Q{(day.month - 1) // 3 + 1}",
        f"{day.year}-{day.month:02d}",
        "Expense" if is_expense else "Income",
        ledger.label,
        _category(ledger_key, values),
        values.get("activity") or "",
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


def build_dues_summary(dues):
    """
    dues: objects or dicts with year, quarter, amount_due, amount_paid,
          balance, status. Returns [DUES_SUMMARY_HEADERS, row, ...] by period.
    """
    def get(item, name):
        return item[name] if isinstance(item, dict) else getattr(item, name)

    periods = {}
    for item in dues:
        key = (get(item, "year"), get(item, "quarter"))
        bucket = periods.setdefault(key, {
            "billed": 0, "paid": 0, "partial": 0, "unpaid": 0,
            "due": Decimal("0"), "collected": Decimal("0"), "outstanding": Decimal("0"),
        })
        status = get(item, "status")
        bucket["billed"] += 1
        if status == "paid":
            bucket["paid"] += 1
        elif status == "partial":
            bucket["partial"] += 1
        else:
            bucket["unpaid"] += 1
        bucket["due"] += Decimal(get(item, "amount_due"))
        bucket["collected"] += Decimal(get(item, "amount_paid"))
        bucket["outstanding"] += Decimal(get(item, "balance"))

    rows = [list(DUES_SUMMARY_HEADERS)]
    for (year, quarter), b in sorted(periods.items()):
        rate = float(b["collected"] / b["due"]) if b["due"] else 0.0
        rows.append([
            f"{year}-{quarter}", year, quarter,
            b["billed"], b["paid"], b["partial"], b["unpaid"],
            float(b["due"]), float(b["collected"]), float(b["outstanding"]),
            round(rate, 4),
        ])
    return rows
