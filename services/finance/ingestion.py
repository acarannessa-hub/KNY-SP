"""
Ingestion: turn an uploaded CSV or Excel (.xlsx) file into raw rows.

This step only READS the file and matches its columns to a ledger. It does
not judge the values; cleaning.py does that row by row. Pure Python plus
openpyxl, no database.

Column names are matched loosely, so the treasurer's own spreadsheets work
as they are: "Date", "Short_Description", "Reference_Number / Sales Invoice
No.", "ACCOUNT NO./ NAME", "Purpose", ... (see COLUMN_ALIASES). Columns the
pipeline does not use (Expense_ID, empty trailing columns, ...) are ignored.

    rows = read_rows("fundraising", "march.xlsx", file_bytes)
    # -> [(row_number, {"fundraising_date": ..., "amount": ..., ...}), ...]

The membership-fee sheets (one row per member, with Status and Balance) are
handled by membership_import.py, which uses read_table() from here.
"""

import csv
import io
import re
from datetime import date, datetime

from .ledgers import LEDGERS

# Vercel rejects request bodies above ~4.5 MB anyway.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_ROWS = 5000

# normalized header -> field, per ledger (in addition to the field names)
_COMMON = {
    "amount": "amount",
    "payment_method": "payment_method",
    "payment_mode": "payment_method",
    "mode_of_payment": "payment_method",
    "reference_number": "reference_no",
    "reference_no": "reference_no",
    "reference": "reference_no",
    "ref_no": "reference_no",
    "reference_number_sales_invoice_no": "reference_no",
    "sales_invoice_no": "reference_no",
    "or_no": "reference_no",
    "notes": "notes",
    "remarks": "notes",
    "activity": "activity",
    "event": "activity",
}

COLUMN_ALIASES = {
    "fundraising": {
        **_COMMON,
        "date": "fundraising_date",
        "income_type": "income_type",
        "type": "income_type",
        "account_no_name": "payer",
        "account_name": "payer",
        "account_no": "payer",
        "payer": "payer",
        "donor": "payer",
        "name": "payer",
    },
    "sponsorships": {
        **_COMMON,
        "date": "sponsorship_date",
        "sponsor": "sponsor_name",
        "sponsor_name": "sponsor_name",
        "sponsor_type": "sponsor_type",
        "type": "sponsor_type",
        "purpose": "activity",
    },
    "membership_fees": {
        **_COMMON,
        "date": "payment_date",
        "date_paid": "payment_date",
        "membership_id": "membership_id",
        "member_id": "membership_id",
        "year": "year",
        "quarter": "quarter",
    },
    "expenses": {
        **_COMMON,
        "date": "expense_date",
        "category": "category",
        "short_description": "description",
        "description": "description",
        "particulars": "description",
        "purpose": "activity",
    },
}


class IngestionError(ValueError):
    """The file as a whole cannot be read. str(error) is safe to show."""


def normalize_header(header):
    """'Payment Date', 'payment-date', ' PAYMENT_DATE ' -> 'payment_date';
    'Reference_Number / Sales Invoice No. ' -> 'reference_number_sales_invoice_no'."""
    text = re.sub(r"[^0-9a-z]+", "_", str(header or "").strip().casefold())
    return text.strip("_")


def column_title(field_name):
    """'membership_id' -> 'Membership_ID' (how headers appear in templates)."""
    return "_".join(
        "ID" if part == "id" else part.capitalize()
        for part in field_name.split("_")
    )


def expected_columns(ledger_key):
    """Human-readable column list for upload instructions."""
    ledger = LEDGERS[ledger_key]
    required = [column_title(name) for name in ledger.required_fields]
    optional = [
        column_title(name)
        for name in ledger.field_names
        if name not in ledger.required_fields
    ]
    return required, optional


def field_for_header(ledger_key, header):
    key = normalize_header(header)
    if key in LEDGERS[ledger_key].field_names:
        return key
    return COLUMN_ALIASES[ledger_key].get(key)


# --------------------------------------------------
# Reading files
# --------------------------------------------------
def read_table(filename, data):
    """
    Return (headers, rows): the first non-blank row as normalized header
    names, and [(row_number, [cell, ...])] for every later non-blank row.
    Raises IngestionError when the file cannot be used at all.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise IngestionError("The file is larger than 4 MB. Split it into smaller files.")
    if not data:
        raise IngestionError("The file is empty.")

    name = (filename or "").lower()
    if name.endswith(".csv"):
        table = _read_csv(data)
    elif name.endswith(".xlsx"):
        table = _read_xlsx(data)
    elif name.endswith(".xls"):
        raise IngestionError(
            "Old .xls files are not supported. In Excel, use "
            "File > Save As > Excel Workbook (.xlsx), or save as CSV."
        )
    else:
        raise IngestionError("Upload a .csv or .xlsx file.")

    header_index = next(
        (index for index, row in enumerate(table) if not _is_blank(row)),
        None,
    )
    if header_index is None:
        raise IngestionError("The file has no header row.")

    headers = [normalize_header(h) for h in table[header_index]]
    rows = []
    for index in range(header_index + 1, len(table)):
        values = [_plain(v) for v in table[index]]
        if _is_blank(values):
            continue
        rows.append((index + 1, values))   # spreadsheet row numbers start at 1
        if len(rows) > MAX_ROWS:
            raise IngestionError(
                f"The file has more than {MAX_ROWS} rows. Split it into smaller files."
            )
    return headers, rows


def read_rows(ledger_key, filename, data):
    """Return [(row_number, raw_dict)] for every non-blank data row of a
    ledger file. Raises IngestionError when the file cannot be used."""
    headers, rows = read_table(filename, data)
    return match_columns(ledger_key, headers, rows)


def match_columns(ledger_key, headers, rows):
    ledger = LEDGERS[ledger_key]
    positions = {}
    for position, header in enumerate(headers):
        field = field_for_header(ledger_key, header)
        if field and field not in positions:
            positions[field] = position

    missing = [name for name in ledger.required_fields if name not in positions]
    if missing:
        required, optional = expected_columns(ledger_key)
        raise IngestionError(
            "Missing column(s): " + ", ".join(column_title(m) for m in missing)
            + ". Required: " + ", ".join(required)
            + ". Optional: " + ", ".join(optional) + "."
        )

    matched = []
    for row_number, values in rows:
        raw = {
            field: (values[position] if position < len(values) else None)
            for field, position in positions.items()
        }
        if _is_blank(raw.values()):
            continue
        matched.append((row_number, raw))
    if not matched:
        raise IngestionError("The file has a header row but no records.")
    return matched


def _plain(value):
    """Cell value -> str / int / float / None, so rows can be serialized."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return str(value)


def _read_csv(data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IngestionError(
            "The CSV file must use UTF-8 encoding. In Excel, choose "
            "'CSV UTF-8 (Comma delimited)' when saving."
        )
    try:
        return list(csv.reader(io.StringIO(text), strict=True))
    except csv.Error:
        raise IngestionError("The CSV file contains malformed rows and was not imported.")


def _read_xlsx(data):
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError:
        raise IngestionError("Excel import is not available on this server. Upload a CSV file instead.")
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - zip/xml/openpyxl errors all mean "unreadable"
        raise IngestionError("The file could not be read as an Excel workbook (.xlsx).")
    try:
        sheet = workbook.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _is_blank(values):
    return not any(str(value).strip() for value in values if value is not None)
