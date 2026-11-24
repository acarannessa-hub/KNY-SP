"""
Ingestion: turn an uploaded CSV or Excel (.xlsx) file into raw rows.

This step only READS the file and matches its columns to a ledger. It does
not judge the values; cleaning.py does that row by row. Pure Python plus
openpyxl, no database.

    rows = read_rows("fundraising", "march.xlsx", file_bytes)
    # -> [(row_number, {"fundraising_date": ..., "amount": ..., ...}), ...]
"""

import csv
import io
import re

from .ledgers import LEDGERS

# Vercel rejects request bodies above ~4.5 MB anyway.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_ROWS = 5000


class IngestionError(ValueError):
    """The file as a whole cannot be read. str(error) is safe to show."""


def normalize_header(header):
    """'Payment Date', 'payment-date', ' PAYMENT_DATE ' -> 'payment_date'."""
    return re.sub(r"[\s\-]+", "_", str(header or "").strip()).casefold()


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


def read_rows(ledger_key, filename, data):
    """Return [(row_number, raw_dict)] for every non-blank data row.
    Raises IngestionError when the file cannot be used at all."""
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

    return _match_columns(ledger_key, table)


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


def _match_columns(ledger_key, table):
    ledger = LEDGERS[ledger_key]

    # The header is the first non-blank row.
    header_index = next(
        (index for index, row in enumerate(table) if not _is_blank(row)),
        None,
    )
    if header_index is None:
        raise IngestionError("The file has no header row.")

    positions = {}
    for position, header in enumerate(table[header_index]):
        key = normalize_header(header)
        if key in ledger.field_names and key not in positions:
            positions[key] = position

    missing = [name for name in ledger.required_fields if name not in positions]
    if missing:
        required, optional = expected_columns(ledger_key)
        raise IngestionError(
            "Missing column(s): " + ", ".join(column_title(m) for m in missing)
            + ". Required: " + ", ".join(required)
            + ". Optional: " + ", ".join(optional) + "."
        )

    rows = []
    for index in range(header_index + 1, len(table)):
        values = table[index]
        if _is_blank(values):
            continue
        raw = {
            field: (values[position] if position < len(values) else None)
            for field, position in positions.items()
        }
        rows.append((index + 1, raw))   # spreadsheet row numbers start at 1
        if len(rows) > MAX_ROWS:
            raise IngestionError(
                f"The file has more than {MAX_ROWS} rows. Split it into smaller files."
            )
    if not rows:
        raise IngestionError("The file has a header row but no records.")
    return rows
