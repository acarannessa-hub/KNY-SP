"""
Google Sheets mirror for the financial ledgers.

Supabase PostgreSQL is the source of truth. After every successful change,
the affected ledger is copied in full to its tab in the dedicated Google
Sheet, so officers can view, filter and chart the data in Sheets.

* One-way only: edits typed into the sheet are NOT read back, and the next
  sync overwrites them. Share the sheet with officers as VIEWER.
* Optional: when GOOGLE_SHEET_ID is not set the mirror is simply off.
* Never blocks saving: a Google failure leaves the database change in place
  and returns a warning; an admin can run "Resync Google Sheet" later.

This module does not query the database. records.py passes in the rows.
"""

import logging
import os

import google_sheets as gs
import sheets_schema as schema

from .ledgers import LEDGERS

log = logging.getLogger(__name__)

# Extra read-only columns appended AFTER the standard sheet layout, to make
# the sheet easier to analyze. (Extra columns on the right are allowed by
# google_sheets.header_status.)
EXTRA_COLUMNS = {
    "membership_fees": ["member_name", "org_role"],
}


def is_enabled():
    return bool((os.getenv("GOOGLE_SHEET_ID") or "").strip())


def sheet_headers(ledger_key):
    return schema.headers(ledger_key) + EXTRA_COLUMNS.get(ledger_key, [])


def row_values(ledger_key, record_id, values, created_at=None, extras=None):
    """
    Build one sheet row (a list, in header order) from a database record.

    values      {field_name: python value} for the ledger's fields
    extras      {column: value} for EXTRA_COLUMNS

    Amounts are written as numbers so SUM() and charts work in Sheets;
    everything else is written as plain text.
    """
    ledger = LEDGERS[ledger_key]
    row = {"record_id": str(record_id)}
    for field in ledger.fields:
        value = values.get(field.name)
        if value is None:
            row[field.name] = ""
        elif field.kind == "amount":
            row[field.name] = float(value)
        elif field.kind == "date":
            row[field.name] = value.isoformat()
        else:
            row[field.name] = str(value)
    row["import_key"] = schema.make_import_key(ledger_key, values)
    row["status"] = "active"
    row["created_at"] = schema.format_timestamp(created_at)
    row.update({column: "" if value is None else str(value)
                for column, value in (extras or {}).items()})
    return [row.get(header, "") for header in sheet_headers(ledger_key)]


def push_ledger(ledger_key, rows):
    """Replace the ledger's tab with header + rows. Raises gs.SheetsError."""
    gs.replace_tab(ledger_key, [sheet_headers(ledger_key)] + list(rows))


def warning_for(error):
    detail = str(error).rstrip(".")
    return (
        "The change was saved, but the Google Sheet copy could not be "
        f"updated ({detail}). An administrator can use 'Resync Google Sheet' "
        "on the Financial Management page to fix this."
    )
