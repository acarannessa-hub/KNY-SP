"""
Preprocessing for the treasurer's membership-fee sheets.

Expected columns (one sheet per quarter, e.g. "Membership_Fees_Q1.csv"):

    Membership_ID, Last_Name, First_Name, Middle_Name, Year, Date, Mem_Type,
    Com_or_Pos, Amount, Payment_Method, Reference_Number, Status, Balance

Membership_ID is usually empty, so members are matched by NAME. Each row
describes what one member owed for one (year, quarter) and whether it was
paid, so a row becomes:

    * a DUES record    -> amount due, amount paid, balance, status
    * a PAYMENT record -> only when money was actually received
                          (Status PAID, including partial payments)

UNPAID / Deferred rows are obligations, NOT income, so they never create a
payment. Rows the program cannot decide on are flagged for review instead
of guessed (missing date, unknown member, contradictory status).

Pure Python: no database, no Flask. records.py supplies the member list.
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from . import cleaning

STATUS_ALIASES = {
    "paid": "paid",
    "unpaid": "unpaid",
    "not paid": "unpaid",
    "deferred": "deferred",
    "deffered": "deferred",      # spelling used in the sheets
    "defered": "deferred",
}

_QUARTER_IN_NAME = re.compile(r"(?:^|[^a-z0-9])q([1-4])(?:[^0-9]|$)", re.IGNORECASE)


def is_treasurer_format(headers):
    return {"last_name", "first_name"} <= set(headers)


def quarter_from_filename(filename):
    match = _QUARTER_IN_NAME.search(filename or "")
    return f"Q{match.group(1)}" if match else None


# --------------------------------------------------
# Names
# --------------------------------------------------
def _fold(text):
    text = unicodedata.normalize("NFKD", cleaning.present(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z ]+", " ", text.casefold())
    return re.sub(r"\s+", " ", text).strip()


def first_key(first_name):
    """'Shyra Joy E.' -> 'shyra joy' (a trailing middle initial is dropped)."""
    tokens = _fold(first_name).split()
    while len(tokens) > 1 and len(tokens[-1]) == 1:
        tokens.pop()
    return " ".join(tokens)


def person_key(last_name, first_name):
    return (_fold(last_name), first_key(first_name))


def display_name(first, middle, last):
    parts = [cleaning.present(first), cleaning.present(middle), cleaning.present(last)]
    return " ".join(p for p in parts if p).title()


@dataclass
class MemberIndex:
    """members: [(membership_id, first, middle, last, status)]"""
    members: list

    def __post_init__(self):
        self.by_last = {}
        for membership_id, first, middle, last, status in self.members:
            self.by_last.setdefault(_fold(last), []).append(
                (membership_id, first_key(first), _fold(middle), status,
                 display_name(first, middle, last))
            )

    def match(self, last, first, middle):
        """Return (membership_id, note) or (None, reason)."""
        candidates = self.by_last.get(_fold(last), [])
        if not candidates:
            return None, "no member with this last name"
        wanted = first_key(first)
        exact = [c for c in candidates if c[1] == wanted]
        if len(exact) > 1 and _fold(middle):
            exact = [c for c in exact if c[2] == _fold(middle)] or exact
        if len(exact) == 1:
            return exact[0][0], None
        if len(exact) > 1:
            return None, "several members share this name"
        # Spelling differences ("Jean" / "Jhean"): accept a very close match.
        scored = sorted(
            ((difflib.SequenceMatcher(None, wanted, c[1]).ratio(), c) for c in candidates),
            key=lambda pair: pair[0], reverse=True,
        )
        if scored and scored[0][0] >= 0.85 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
            best = scored[0][1]
            return best[0], f"matched to member {best[4]} ({best[0]})"
        return None, "no member with this first name"


# --------------------------------------------------
# Rows
# --------------------------------------------------
@dataclass
class FeeRow:
    row: int
    name: str
    person: tuple
    year: int | None = None
    quarter: str | None = None
    membership_id: str | None = None
    status: str | None = None
    amount_due: Decimal = Decimal("0")
    amount_paid: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")
    payment: dict | None = None          # raw values for cleaning.clean_record
    new_member: dict | None = None       # member to create, when approved
    notes: list = field(default_factory=list)      # auto-corrections / matches
    review: list = field(default_factory=list)     # [(kind, message)] needs a person
    error: str | None = None                       # cannot be imported at all


def _col(headers, *names):
    for name in names:
        if name in headers:
            return headers.index(name)
    return None


def _date_column(headers):
    index = _col(headers, "date", "payment_date", "date_paid")
    if index is not None:
        return index
    # One quarter sheet has an empty header where "Date" belongs (after Year).
    year = _col(headers, "year")
    if year is not None and year + 1 < len(headers) and headers[year + 1] == "":
        return year + 1
    return None


def _optional_amount(value):
    if not cleaning.present(value):
        return None
    return cleaning.parse_amount(value, allow_zero=True)


def analyze(headers, rows, quarter, index, today, overrides=None):
    """
    headers/rows : from ingestion.read_table()
    quarter      : "Q1".."Q4" for the whole sheet
    index        : MemberIndex of existing members
    overrides    : {row_number: {"date": str, "amount": str,
                                 "create_member": bool, "treat_as_paid": bool}}
    Returns [FeeRow].
    """
    overrides = overrides or {}
    cols = {
        "last": _col(headers, "last_name"),
        "first": _col(headers, "first_name"),
        "middle": _col(headers, "middle_name"),
        "membership_id": _col(headers, "membership_id"),
        "year": _col(headers, "year"),
        "date": _date_column(headers),
        "mem_type": _col(headers, "mem_type"),
        "position": _col(headers, "com_or_pos", "position"),
        "amount": _col(headers, "amount"),
        "method": _col(headers, "payment_method"),
        "reference": _col(headers, "reference_number", "reference_no"),
        "status": _col(headers, "status"),
        "balance": _col(headers, "balance"),
    }
    missing = [name for name in ("last", "first", "year", "amount", "status") if cols[name] is None]
    if missing:
        raise ValueError(
            "Missing column(s): "
            + ", ".join({"last": "Last_Name", "first": "First_Name", "year": "Year",
                         "amount": "Amount", "status": "Status"}[m] for m in missing)
        )

    def get(values, name):
        position = cols[name]
        if position is None or position >= len(values):
            return None
        return values[position]

    results = []
    for row_number, values in rows:
        fix = overrides.get(row_number, {})
        last, first, middle = get(values, "last"), get(values, "first"), get(values, "middle")
        if not cleaning.present(last) and not cleaning.present(first):
            continue
        item = FeeRow(
            row=row_number,
            name=display_name(first, middle, last),
            person=person_key(last, first),
            quarter=quarter,
        )
        results.append(item)

        # ---- year
        try:
            item.year = cleaning.parse_year(get(values, "year"), today)
        except cleaning.FieldError as error:
            item.error = f"Year {error}"
            continue
        if item.year is None:
            item.error = "Year is required."
            continue

        # ---- member
        typed_id = cleaning.present(get(values, "membership_id"))
        found = None
        if typed_id:
            found = next((m for m in index.members if m[0].casefold() == typed_id.casefold()), None)
        if found:
            item.membership_id = found[0]
        else:
            membership_id, note = index.match(last, first, middle)
            if membership_id:
                item.membership_id = membership_id
                if note:
                    item.notes.append(note)
            elif fix.get("create_member"):
                position = cleaning.present(get(values, "position"))
                former = position.casefold().startswith("former")
                item.new_member = {
                    "first_name": cleaning.present(first).title() or "",
                    "middle_name": cleaning.present(middle).title() or None,
                    "last_name": cleaning.present(last).title() or "",
                    "org_role": (position or cleaning.present(get(values, "mem_type")) or "Member")[:100],
                    "status": "inactive" if former else "active",
                }
            else:
                item.review.append(("member", f"Not found in Members ({note}). Tick to create this member."))

        # ---- status and amounts
        raw_status = cleaning.present(get(values, "status")).casefold()
        status = STATUS_ALIASES.get(raw_status)
        if status is None:
            item.error = f"Status '{cleaning.present(get(values, 'status'))}' is not PAID, UNPAID or Deferred."
            continue
        try:
            amount = _optional_amount(fix.get("amount") or get(values, "amount"))
            balance = _optional_amount(get(values, "balance")) or Decimal("0.00")
        except cleaning.FieldError as error:
            item.error = f"Amount or balance {error}"
            continue

        reference = cleaning.present(get(values, "reference"))
        raw_date = fix.get("date") or get(values, "date")
        has_date = bool(cleaning.present(raw_date))

        if status != "paid" and has_date and reference and balance == 0:
            if fix.get("treat_as_paid"):
                status = "paid"
                item.notes.append("status changed from UNPAID to PAID on review")
            else:
                item.review.append((
                    "conflict",
                    "Status says UNPAID, but the row has a payment date, a reference "
                    "number and a zero balance. Tick to record it as PAID.",
                ))

        if status == "paid":
            if amount is None:
                item.review.append(("amount", "Marked PAID but the amount is blank. Enter the amount paid."))
                amount = Decimal("0.00")
            item.amount_paid = amount
            item.balance = balance
            item.amount_due = amount + balance
            item.status = "partial" if balance > 0 else "paid"
            if amount > 0:
                try:
                    paid_on = cleaning.parse_date(raw_date, today)
                except cleaning.FieldError as error:
                    shown = cleaning.collapse(raw_date) or "blank"
                    item.review.append(("date", f"Payment date '{shown}' {error} Enter the date paid."))
                    paid_on = None
                item.payment = {
                    "membership_id": item.membership_id or "",
                    "year": item.year,
                    "quarter": quarter,
                    "payment_date": paid_on,
                    "amount": amount,
                    "payment_method": get(values, "method"),
                    "reference_no": reference,
                    "notes": "",
                }
        else:
            due = balance if balance > 0 else (amount or Decimal("0.00"))
            item.amount_due = due
            item.amount_paid = Decimal("0.00")
            item.balance = due
            item.status = status
    return results
