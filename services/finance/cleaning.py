"""
Cleaning and validation of ONE financial record.

Pure Python: no Flask, no database, no Google. The caller passes in whatever
lookup data is needed (existing members, existing expense categories), so the
same function serves the web form, CSV import and Excel import, and can be
unit-tested directly.

    cleaned, errors = clean_record("fundraising", raw_values)

`cleaned` holds Python types ready for the model (date, Decimal, str/None).
`errors` is a list of messages that are safe to show to the user; when it is
non-empty, `cleaned` must not be saved.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import sheets_schema

from .ledgers import LEDGERS

# NUMERIC(12, 2) in the database -> at most 10 digits before the decimal point.
MAX_AMOUNT = Decimal("9999999999.99")

# Dates before this are almost always a typo in the year (e.g. 0226, 1926).
EARLIEST_DATE = date(2000, 1, 1)

# Accepted date spellings. Slash dates are read MONTH first (MM/DD/YYYY),
# the usual convention in the Philippines.
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%d %B %Y",
    "%d %b %Y",
)

# Common spellings -> one canonical name, so reports group them together.
PAYMENT_METHOD_ALIASES = {
    "cash": "Cash",
    "gcash": "GCash",
    "g-cash": "GCash",
    "g cash": "GCash",
    "maya": "Maya",
    "paymaya": "Maya",
    "pay maya": "Maya",
    "bank": "Bank Transfer",
    "bank transfer": "Bank Transfer",
    "online transfer": "Bank Transfer",
    "online banking": "Bank Transfer",
    "bank deposit": "Bank Deposit",
    "deposit": "Bank Deposit",
    "check": "Check",
    "cheque": "Check",
    "maribank": "MariBank",
    "mari bank": "MariBank",
    "bpi": "BPI",
    "landbank": "Landbank",
    "land bank": "Landbank",
    "gotyme": "GoTyme Bank",
    "gotyme bank": "GoTyme Bank",
    "go tyme": "GoTyme Bank",
}

INCOME_TYPE_ALIASES = {
    "donation": "Donation",
    "donations": "Donation",
    "registration fee": "Registration Fee",
    "registration fees": "Registration Fee",
    "registration": "Registration Fee",
    "sponsorship": "Sponsorship",
    "sponsorships": "Sponsorship",
    "event proceeds": "Event Proceeds",
    "proceeds": "Event Proceeds",
    "sales": "Event Proceeds",
}

SPONSOR_TYPE_ALIASES = {
    "individual": "Individual",
    "person": "Individual",
    "business": "Business",
    "company": "Business",
    "organization": "Organization",
    "organisation": "Organization",
    "org": "Organization",
    "government": "Government",
}

# Values spreadsheets use for "nothing here".
PLACEHOLDERS = {"n/a", "na", "n.a.", "n.a", "n.d", "n.d.", "nd", "none", "-", "--", "null"}

_CURRENCY_PREFIX = re.compile(r"^(php|₱|p)\s*(?=[\d.,\s])", re.IGNORECASE)
_TWO_DIGIT_YEAR = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2})$")
_DATETIME_TEXT = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T]\d{1,2}:\d{2}")
_QUARTER = re.compile(r"^Q?([1-4])$")


class FieldError(ValueError):
    """A value that cannot be accepted. str(error) completes the sentence
    that starts with the field label, e.g. 'must be greater than zero.'"""


# --------------------------------------------------
# Single-value normalizers
# --------------------------------------------------
def collapse(value):
    """None -> ''. Strip and collapse inner whitespace. Whole-number floats
    (how Excel hands over IDs such as 1001) lose their '.0'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def is_placeholder(text):
    return text.casefold() in PLACEHOLDERS


def present(value):
    """collapse(), with spreadsheet placeholders (N/A, N.D, -) treated as empty."""
    text = collapse(value)
    return "" if is_placeholder(text) else text


def parse_amount(value, allow_zero=False):
    if isinstance(value, bool):
        raise FieldError("must be a number, like 1500 or 1,500.00.")
    text = present(value)
    if not text:
        raise FieldError("is required.")
    text = _CURRENCY_PREFIX.sub("", text).replace(",", "").replace(" ", "")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise FieldError("must be a number, like 1500 or 1,500.00.")
    if not amount.is_finite():
        raise FieldError("must be a number, like 1500 or 1,500.00.")
    if amount < 0 or (amount == 0 and not allow_zero):
        raise FieldError("must be greater than zero." if not allow_zero else "cannot be negative.")
    if amount != amount.quantize(Decimal("0.01")):
        raise FieldError("can have at most 2 decimal places.")
    if amount > MAX_AMOUNT:
        raise FieldError("is too large.")
    return amount.quantize(Decimal("0.01"))


def parse_date(value, today):
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = present(value)
        if not text:
            raise FieldError("is required.")
        match = _DATETIME_TEXT.match(text)
        if match:
            text = match.group(1)
        short = _TWO_DIGIT_YEAR.match(text)
        if short:
            # 08/23/26 -> 08/23/2026 (Python's %Y would read "26" as year 26)
            text = f"{short.group(1)}/{short.group(2)}/20{short.group(3)}"
        parsed = None
        for fmt in DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            raise FieldError(
                "must be a date such as 2026-03-15 (YYYY-MM-DD) "
                "or 03/15/2026 (MM/DD/YYYY)."
            )
    if parsed > today:
        raise FieldError("cannot be in the future.")
    if parsed < EARLIEST_DATE:
        raise FieldError("is before the year 2000. Check the year.")
    return parsed


def parse_quarter(value):
    match = _QUARTER.match(present(value).upper())
    if not match:
        raise FieldError("must be Q1, Q2, Q3, or Q4.")
    return f"Q{match.group(1)}"


def parse_year(value, today):
    text = present(value)
    if not text:
        return None
    if not re.fullmatch(r"\d{4}", text):
        raise FieldError("must be a 4-digit year such as 2026.")
    year = int(text)
    if year < EARLIEST_DATE.year or year > today.year + 1:
        raise FieldError(f"must be between {EARLIEST_DATE.year} and {today.year + 1}.")
    return year


def normalize_choice(value, aliases):
    """Known spellings -> canonical; unknown -> title case if typed all one case."""
    text = present(value)
    if not text:
        return ""
    known = aliases.get(text.casefold())
    if known:
        return known
    return text.title() if (text.islower() or text.isupper()) else text


def normalize_payment_method(value):
    text = present(value)
    return PAYMENT_METHOD_ALIASES.get(text.casefold(), text)


def normalize_category(value, known_categories=None):
    """Reuse an existing spelling when one matches ignoring case, so
    'food', 'FOOD' and 'Food ' all become the category already on file."""
    text = present(value)
    if not text:
        return text
    if known_categories:
        existing = known_categories.get(text.casefold())
        if existing:
            return existing
    if text.islower() or text.isupper():
        return text.title()
    return text


def normalize_longtext(value):
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


# --------------------------------------------------
# Whole record
# --------------------------------------------------
def clean_record(
    ledger_key,
    raw,
    *,
    today=None,
    members=None,
    known_categories=None,
    require_active_member=True,
):
    """
    Normalize and validate one record.

    raw                    any mapping (request.form, a CSV row dict, ...)
    members                {membership_id.casefold(): (membership_id, status)}
                           required for membership_fees
    known_categories       {category.casefold(): category} for expenses
    require_active_member  True when adding a fee; False when editing or
                           importing historical payments

    Returns (cleaned_dict, errors).
    """
    ledger = LEDGERS[ledger_key]
    today = today or date.today()
    cleaned = {}
    errors = []

    for field in ledger.fields:
        value = raw.get(field.name)
        try:
            cleaned[field.name] = _clean_field(
                field, value, today, members, known_categories,
                require_active_member,
            )
        except FieldError as error:
            errors.append(f"{field.label} {error}")

    # Dues year defaults to the year of the payment date.
    if "year" in cleaned and cleaned["year"] is None:
        paid_on = cleaned.get(ledger.date_field)
        if paid_on:
            cleaned["year"] = paid_on.year

    return cleaned, errors


def _clean_field(field, value, today, members, known_categories, require_active_member):
    kind = field.kind

    if kind == "date":
        return parse_date(value, today)
    if kind == "amount":
        return parse_amount(value)
    if kind == "quarter":
        return parse_quarter(value)
    if kind == "year":
        return parse_year(value, today)

    if kind == "member":
        text = present(value)
        if not text:
            raise FieldError("is required.")
        found = (members or {}).get(text.casefold())
        if found is None:
            raise FieldError(f"'{text}' does not match any member.")
        membership_id, status = found
        if require_active_member and status != "active":
            raise FieldError(f"'{membership_id}' belongs to an inactive member.")
        return membership_id

    if kind == "longtext":
        text = normalize_longtext(value)
        if is_placeholder(text):
            text = ""
    elif kind == "payment_method":
        text = normalize_payment_method(value)
    elif kind == "category":
        text = normalize_category(value, known_categories)
    elif kind == "income_type":
        text = normalize_choice(value, INCOME_TYPE_ALIASES)
    elif kind == "sponsor_type":
        text = normalize_choice(value, SPONSOR_TYPE_ALIASES)
    else:
        text = present(value)

    if not text:
        if field.required:
            raise FieldError("is required.")
        return None
    if field.max_length and len(text) > field.max_length:
        raise FieldError(f"must be at most {field.max_length} characters.")
    return text


# --------------------------------------------------
# Duplicate fingerprint
# --------------------------------------------------
def fingerprint(ledger_key, record):
    """Same fingerprint as the Google Sheet's import_key (sheets_schema),
    so a payment is recognized as a duplicate however it was entered.
    With a reference number: date + amount + who + reference.
    Without one: also payment method and notes/description."""
    return sheets_schema.make_import_key(ledger_key, record)
