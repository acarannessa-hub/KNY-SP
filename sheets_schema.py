"""
Shared definition of the Google Sheets layout for KNY-SP financial records.

Used by:
  * google_sheets.py (reading/writing the private Google Sheet)
  * the Flask app (manual entry, CSV import, duplicate detection)
  * migrate_financial_to_csv.py (optional one-time migration; not needed for
    a fresh start)

Keeping this in one module guarantees that migrated rows and newly entered
rows produce the SAME import_key for the same underlying payment, so
duplicate detection works across both.

No Flask, no database, and no Google imports here on purpose.
"""

import hashlib
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# --------------------------------------------------
# Columns added to EVERY tab (after the tab-specific ones)
# --------------------------------------------------
META_COLUMNS = [
    "import_key",   # hash used for duplicate detection (see make_import_key)
    "status",       # "active" or "deleted" (soft delete)
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "legacy_id",    # old MySQL id, kept only for traceability
]

# --------------------------------------------------
# Tab definitions
#
#   db_table      : table name in the old MySQL database
#   date_field    : the column used for ordering and date validation
#   fields        : tab-specific columns, in sheet order
#   key_core      : fields that identify a payment when a reference number
#                   exists
#   key_fallback  : extra fields added to the key when reference_no is empty,
#                   so two genuinely different cash entries on the same day
#                   are less likely to be flagged as duplicates
# --------------------------------------------------
TABS = {
    "fundraising": {
        "db_table": "fundraising",
        "date_field": "fundraising_date",
        "fields": [
            "fundraising_date", "amount", "payment_method",
            "reference_no", "notes",
        ],
        "key_core": ["fundraising_date", "amount", "reference_no"],
        "key_fallback": ["payment_method", "notes"],
    },
    "sponsorships": {
        "db_table": "sponsorships",
        "date_field": "sponsorship_date",
        "fields": [
            "sponsorship_date", "sponsor_name", "amount",
            "payment_method", "reference_no", "notes",
        ],
        "key_core": [
            "sponsorship_date", "sponsor_name", "amount", "reference_no",
        ],
        "key_fallback": ["payment_method", "notes"],
    },
    "membership_fees": {
        "db_table": "membership_fees",
        "date_field": "payment_date",
        "fields": [
            "membership_id", "quarter", "payment_date", "amount",
            "payment_method", "reference_no", "notes",
        ],
        "key_core": [
            "membership_id", "quarter", "payment_date", "amount",
            "reference_no",
        ],
        "key_fallback": ["payment_method", "notes"],
    },
    "expenses": {
        "db_table": "expenses",
        "date_field": "expense_date",
        "fields": [
            "expense_date", "category", "description", "amount",
            "payment_method", "reference_no", "notes",
        ],
        "key_core": ["expense_date", "category", "amount", "reference_no"],
        "key_fallback": ["description", "payment_method", "notes"],
    },
}

# record_id is always the first column so it is easy to find and never edited.
def headers(tab):
    return ["record_id"] + TABS[tab]["fields"] + META_COLUMNS


# --------------------------------------------------
# Normalizers
# --------------------------------------------------
def normalize_text(value):
    """None -> ''. Trim, collapse inner whitespace, case-fold."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def normalize_amount(value):
    """Return amount as a 2-decimal string ('1500.00'), or '' if unusable."""
    if value is None or str(value).strip() == "":
        return ""
    try:
        amount = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        return ""
    if not amount.is_finite():
        return ""
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def normalize_date(value):
    """Return 'YYYY-MM-DD', or '' if unusable."""
    if value is None or str(value).strip() == "":
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def _normalize_field(name, value):
    if name == "amount":
        return normalize_amount(value)
    if name.endswith("_date"):
        return normalize_date(value)
    if name in ("quarter", "membership_id"):
        # membership IDs / quarters are identifiers: compare case-insensitively
        return normalize_text(value).upper()
    return normalize_text(value)


# --------------------------------------------------
# Identity helpers
# --------------------------------------------------
def new_record_id():
    """Stable, random, never-reused ID for a sheet row."""
    return str(uuid.uuid4())


def make_import_key(tab, record):
    """
    Deterministic fingerprint of a payment, for duplicate detection.

    * If the record has a reference number, the key uses only the core
      fields (date, amount, who, reference). Notes or payment-method
      wording changes will NOT hide a duplicate.
    * If there is no reference number, the key also includes the fallback
      fields (payment method, notes/description) to avoid flagging two
      genuinely different same-day, same-amount entries.
    """
    spec = TABS[tab]
    names = list(spec["key_core"])
    if not _normalize_field("reference_no", record.get("reference_no")):
        names += spec["key_fallback"]
    parts = [tab] + [_normalize_field(n, record.get(n)) for n in names]
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]


def format_timestamp(value):
    """DB datetime -> 'YYYY-MM-DD HH:MM:SS' (or '' if missing)."""
    if value is None or str(value).strip() == "":
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return str(value).strip()[:19]


# --------------------------------------------------
# Building a sheet row (used when the app saves a new record)
# --------------------------------------------------
def utc_now_text():
    """Current time in UTC as 'YYYY-MM-DD HH:MM:SS' (what the sheet stores)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def is_deleted(record):
    """A row counts as deleted ONLY when status says so. A row someone typed
    by hand with no status is kept, so money is never silently hidden."""
    return str(record.get("status", "")).strip().lower() == "deleted"


def build_row(tab, record, created_by="", created_at=None, legacy_id=""):
    """
    Turn form/CSV values into one complete sheet row (a dict keyed by header).

    * Amounts become '1500.00', dates become 'YYYY-MM-DD', text is trimmed.
    * record_id, import_key, status and the audit columns are filled in.
    * This does NOT validate (that happens in the route, before saving);
      unusable amounts/dates simply become '' so they are easy to spot.
    """
    spec = TABS[tab]
    stamp = created_at or utc_now_text()
    row = {"record_id": new_record_id()}

    for field in spec["fields"]:
        value = record.get(field)
        if field == "amount":
            row[field] = normalize_amount(value)
        elif field.endswith("_date"):
            row[field] = normalize_date(value)
        elif field == "quarter":
            row[field] = "" if value is None else str(value).strip().upper()
        else:
            row[field] = "" if value is None else str(value).strip()

    row["import_key"] = make_import_key(tab, row)
    row["status"] = "active"
    row["created_at"] = stamp
    row["created_by"] = str(created_by or "")
    row["updated_at"] = stamp
    row["updated_by"] = str(created_by or "")
    row["legacy_id"] = str(legacy_id or "")
    return row
