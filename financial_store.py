"""
financial_store.py -- the four financial record types (fundraising,
sponsorships, membership fees, expenses), stored in the private Google Sheet.

This sits between the Flask routes and google_sheets.py:

  routes  ->  financial_store (validate, de-duplicate, shape records)
          ->  google_sheets   (talk to Google)

What it gives the routes
  * clean_values()      validate a form or a CSV row; returns clean values or
                        raises ValidationError (message is safe to show)
  * load()              records shaped like the old database objects, so the
                        existing templates work unchanged (record.id,
                        record.amount as Decimal, record.payment_date as a
                        date, record.member.full_name, ...)
  * add / update / delete (soft) with duplicate detection
  * split_duplicates()  for CSV imports

Rows that cannot be shown safely (no record_id, invalid date or amount) are
SKIPPED and reported in `problems`, never silently invented.
"""

import csv
import io
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

import google_sheets as gs
import sheets_schema as schema

TAB_LABELS = {
    "fundraising": "Fundraising",
    "sponsorships": "Sponsorships",
    "membership_fees": "Membership fees",
    "expenses": "Expenses",
}

# Singular name used in "<name> record added successfully."
RECORD_NAMES = {
    "fundraising": "Fundraising",
    "sponsorships": "Sponsorship",
    "membership_fees": "Membership fee",
    "expenses": "Expense",
}

DATE_FIELDS = {tab: spec["date_field"] for tab, spec in schema.TABS.items()}

MAX_IMPORT_ROWS = gs.MAX_BATCH_ROWS
MAX_AMOUNT = Decimal("9999999999.99")
EARLIEST_DATE = date(2000, 1, 1)

MAX_LENGTHS = {
    "payment_method": 50,
    "reference_no": 100,
    "notes": 1000,
    "sponsor_name": 150,
    "category": 100,
    "description": 500,
}
MULTILINE_FIELDS = {"notes", "description"}
LABELS = {
    "payment_method": "Payment method",
    "reference_no": "Reference number",
    "notes": "Notes",
    "sponsor_name": "Sponsor name",
    "category": "Category",
    "description": "Description",
}
REQUIRED_TEXT = {
    "sponsorships": ("sponsor_name",),
    "expenses": ("category",),
}

DUPLICATE_MESSAGE = (
    "A record with the same date, amount and details already exists. If this "
    "is a genuinely separate payment, add a reference number or a "
    "distinguishing note."
)


class ValidationError(Exception):
    """str(error) is safe to show to the user."""


class DuplicateRecord(ValidationError):
    pass


class RecordNotFound(Exception):
    pass


# --------------------------------------------------
# Validation
# --------------------------------------------------
def _clean_text(name, raw):
    value = "".join(
        ch for ch in str(raw or "") if ch in "\n\t" or ord(ch) >= 32
    )
    if name not in MULTILINE_FIELDS:
        value = " ".join(value.split())
    else:
        value = value.strip()
    limit = MAX_LENGTHS[name]
    if len(value) > limit:
        raise ValidationError(
            f"{LABELS[name]} is too long (maximum {limit} characters)."
        )
    return value


def _found(raw):
    """' (got 'xyz')' for messages, so people can see what was rejected."""
    text = " ".join(str(raw or "").split())
    return f" (got '{text[:30]}')" if text else ""


def _clean_date(raw):
    try:
        value = datetime.strptime(str(raw or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(
            "Enter a valid date in YYYY-MM-DD format, for example "
            f"2026-10-18{_found(raw)}."
        )
    if value < EARLIEST_DATE or value > date.today() + timedelta(days=366):
        raise ValidationError(
            "That date looks wrong. Enter a date between 2000 and next year."
        )
    return value


def _clean_amount(raw):
    message = (
        "Enter a valid amount greater than zero (at most 2 decimals)"
        f"{_found(raw)}."
    )
    try:
        amount = Decimal(str(raw or "").strip().replace(",", ""))
    except InvalidOperation:
        raise ValidationError(message)
    if not amount.is_finite() or amount <= 0:
        raise ValidationError(message)
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError(message)
    if amount > MAX_AMOUNT:
        raise ValidationError("That amount is too large.")
    return amount


def clean_values(tab, source, members_by_id=None, is_new=True):
    """
    Validate one record from a form (request.form) or a CSV row (a dict).
    Returns a dict of canonical values ready to save, or raises
    ValidationError. For membership fees, members_by_id maps
    membership_id -> Member.
    """
    if tab not in schema.TABS:
        raise ValueError(f"Unknown financial tab: {tab!r}")
    spec = schema.TABS[tab]

    clean = {
        spec["date_field"]: _clean_date(source.get(spec["date_field"])).isoformat(),
        "amount": str(_clean_amount(source.get("amount")).quantize(Decimal("0.01"))),
    }

    for name in spec["fields"]:
        if name in clean or name in ("membership_id", "quarter"):
            continue
        clean[name] = _clean_text(name, source.get(name))

    for name in REQUIRED_TEXT.get(tab, ()):
        if not clean[name]:
            raise ValidationError(f"{LABELS[name]} is required.")

    if tab == "membership_fees":
        membership_id = str(source.get("membership_id") or "").strip()
        member = (members_by_id or {}).get(membership_id)
        if member is None or (is_new and member.status != "active"):
            raise ValidationError(
                f"Membership ID '{membership_id}' does not exist"
                + (" or is not active." if is_new else ".")
            )
        quarter = str(source.get("quarter") or "").strip().upper()
        if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
            raise ValidationError("Choose a valid quarter (Q1 to Q4).")
        clean["membership_id"] = member.membership_id
        clean["quarter"] = quarter

    return clean


# --------------------------------------------------
# Reading: records shaped like the old database objects
# --------------------------------------------------
def _unknown_member(membership_id):
    return SimpleNamespace(
        membership_id=membership_id,
        full_name="(unknown member)",
        org_role="",
        status="unknown",
    )


def _build_record(tab, row, record_id, members_by_id):
    spec = schema.TABS[tab]
    data = {"id": record_id}
    for name in spec["fields"]:
        value = row.get(name, "")
        if name.endswith("_date"):
            data[name] = date.fromisoformat(schema.normalize_date(value))
        elif name == "amount":
            data[name] = Decimal(schema.normalize_amount(value))
        elif name == "quarter":
            data[name] = str(value).strip().upper()
        else:
            data[name] = str(value).strip()
    data["created_at"] = row.get("created_at", "")
    data["created_by"] = row.get("created_by", "")
    data["updated_at"] = row.get("updated_at", "")
    if tab == "membership_fees":
        membership_id = data["membership_id"]
        data["member"] = (members_by_id or {}).get(membership_id) or \
            _unknown_member(membership_id)
    return SimpleNamespace(**data)


def load(tab, members_by_id=None):
    """
    Returns (records, problems).
      records  newest first; each has .id plus the tab's fields
      problems human-readable notes about sheet rows that were skipped
    """
    spec = schema.TABS[tab]
    rows = gs.read_rows(tab, with_row_numbers=True)

    records, problems, seen = [], [], set()
    for row in rows:
        number = row["_row"]
        record_id = row["record_id"].strip().lower()
        try:
            uuid.UUID(record_id)
        except ValueError:
            problems.append(f"row {number} has no valid record_id")
            continue
        if record_id in seen:
            problems.append(f"row {number} repeats a record_id")
            continue
        if not schema.normalize_date(row[spec["date_field"]]):
            problems.append(f"row {number} has an invalid date")
            continue
        if not schema.normalize_amount(row["amount"]):
            problems.append(f"row {number} has an invalid amount")
            continue
        seen.add(record_id)
        records.append(_build_record(tab, row, record_id, members_by_id))

    date_field = spec["date_field"]
    records.sort(key=lambda r: (getattr(r, date_field), r.created_at), reverse=True)
    return records, problems


# --------------------------------------------------
# Duplicates
# --------------------------------------------------
def find_duplicate(tab, clean, exclude_id=None):
    """The existing active row with the same import_key, or None."""
    key = schema.make_import_key(tab, clean)
    skip = str(exclude_id or "").strip().lower()
    for row in gs.read_rows(tab):
        if skip and row["record_id"].strip().lower() == skip:
            continue
        if schema.make_import_key(tab, row) == key:
            return row
    return None


def split_duplicates(tab, candidates):
    """
    candidates: list of (row_number, clean_values).
    Returns (fresh_values, duplicate_row_numbers): a row is a duplicate if it
    is already in the sheet OR repeated earlier in the same file.
    """
    seen = {schema.make_import_key(tab, row) for row in gs.read_rows(tab)}
    fresh, duplicates = [], []
    for number, clean in candidates:
        key = schema.make_import_key(tab, clean)
        if key in seen:
            duplicates.append(number)
        else:
            seen.add(key)
            fresh.append(clean)
    return fresh, duplicates


# --------------------------------------------------
# Writing
# --------------------------------------------------
def add_record(tab, clean, user_id=""):
    if find_duplicate(tab, clean):
        raise DuplicateRecord(DUPLICATE_MESSAGE)
    return gs.append_record(tab, clean, user_id=user_id)


def add_records(tab, fresh_values, user_id=""):
    """Save already-validated, already-de-duplicated rows in one call."""
    return gs.append_records(tab, fresh_values, user_id=user_id)


def update_record(tab, record_id, clean, user_id=""):
    if find_duplicate(tab, clean, exclude_id=record_id):
        raise DuplicateRecord(DUPLICATE_MESSAGE)
    row = gs.update_row(tab, record_id, clean, user_id=user_id)
    if row is None:
        raise RecordNotFound(record_id)
    return row


def delete_record(tab, record_id, user_id=""):
    row = gs.mark_deleted(tab, record_id, user_id=user_id)
    if row is None:
        raise RecordNotFound(record_id)
    return row


# --------------------------------------------------
# Member ID protection
# --------------------------------------------------
def membership_fee_count(membership_id):
    """How many active fee rows use this Membership ID (so the ID is not
    changed underneath them)."""
    wanted = str(membership_id or "").strip().upper()
    return sum(
        1 for row in gs.read_rows("membership_fees")
        if row["membership_id"].strip().upper() == wanted
    )


# --------------------------------------------------
# CSV import (all four record types)
# --------------------------------------------------
IMPORT_LABELS = {
    "fundraising": "fundraising",
    "sponsorships": "sponsorship",
    "membership_fees": "membership-fee",
    "expenses": "expense",
}

MAX_IMPORT_BYTES = 2 * 1024 * 1024   # a 500-row file is far smaller than this


class ImportFileError(ValidationError):
    """The file as a whole cannot be imported (message is safe to show)."""


def _display_name(field):
    """'membership_id' -> 'Membership_ID', 'reference_no' -> 'Reference_No'."""
    return "_".join("ID" if part == "id" else part.capitalize()
                    for part in field.split("_"))


def required_fields(tab):
    """Columns every CSV must have, in sheet order."""
    spec = schema.TABS[tab]
    needed = {spec["date_field"], "amount", *REQUIRED_TEXT.get(tab, ())}
    if tab == "membership_fees":
        needed |= {"membership_id", "quarter"}
    return [field for field in spec["fields"] if field in needed]


def template_columns(tab):
    """Header row of the downloadable CSV template."""
    return [_display_name(field) for field in schema.TABS[tab]["fields"]]


def _normalize_header(header):
    return re.sub(r"[\s\-]+", "_", str(header or "").strip().casefold())


def _header_aliases(tab):
    """Accepted spellings of each column -> the real field name."""
    spec = schema.TABS[tab]
    aliases = {field: field for field in spec["fields"]}
    aliases["date"] = spec["date_field"]
    aliases["reference_number"] = "reference_no"
    aliases["reference"] = "reference_no"
    aliases["ref_no"] = "reference_no"
    if tab == "sponsorships":
        aliases["sponsor"] = "sponsor_name"
    if tab == "membership_fees":
        aliases["member_id"] = "membership_id"
    return aliases


def parse_csv(tab, content, members_by_id=None):
    """
    Read and validate a whole CSV (already decoded to text).

    Returns (candidates, errors):
      candidates  [(row_number, clean_values), ...] ready to de-duplicate/save
      errors      ["Row 5: <reason>", ...] for rows that must be skipped
    Raises ImportFileError for problems with the file itself (no header row,
    missing required columns, too many rows, ...). Nothing is saved here.

    Row numbers match the spreadsheet: row 1 is the header, row 2 the first
    record. Blank rows are ignored; unknown extra columns are ignored.
    """
    if tab not in IMPORT_LABELS:
        raise ValueError(f"Unknown financial tab: {tab!r}")
    aliases = _header_aliases(tab)

    reader = csv.DictReader(io.StringIO(content), strict=True)
    try:
        fieldnames = reader.fieldnames
    except csv.Error:
        raise ImportFileError("The file is not a valid CSV file.")
    if not fieldnames:
        raise ImportFileError("The CSV file is empty or has no header row.")

    column_for = {}
    for header in fieldnames:
        field = aliases.get(_normalize_header(header))
        if field is None:
            continue
        if field in column_for:
            raise ImportFileError(
                f"Two columns in the file both mean '{_display_name(field)}'. "
                "Keep only one of them."
            )
        column_for[field] = header

    required = required_fields(tab)
    missing = [f for f in required if f not in column_for]
    if missing:
        optional = [f for f in schema.TABS[tab]["fields"] if f not in required]
        raise ImportFileError(
            "CSV headers must include "
            + ", ".join(_display_name(f) for f in required)
            + ". Missing: " + ", ".join(_display_name(f) for f in missing)
            + ". Optional columns: "
            + ", ".join(_display_name(f) for f in optional) + "."
        )

    try:
        rows = list(reader)
    except csv.Error:
        raise ImportFileError(
            "The CSV file contains malformed rows and was not imported."
        )
    if len(rows) > MAX_IMPORT_ROWS:
        raise ImportFileError(
            f"The CSV has more than {MAX_IMPORT_ROWS} rows. Split it into "
            f"files of {MAX_IMPORT_ROWS} rows or fewer."
        )

    candidates, errors = [], []
    for number, row in enumerate(rows, start=2):
        values = {
            field: str(row.get(header) or "").strip()
            for field, header in column_for.items()
        }
        if not any(values.values()):
            continue
        try:
            clean = clean_values(tab, values, members_by_id, is_new=True)
        except ValidationError as error:
            errors.append(f"Row {number}: {error}")
            continue
        candidates.append((number, clean))
    return candidates, errors
