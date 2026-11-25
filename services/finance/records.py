"""
Database operations for the financial ledgers.

Every write path goes through here:

    form add/edit  -> create() / update()
    CSV / Excel    -> analyze_upload() (preview) -> confirm_upload()
    delete         -> delete()

Each one cleans and validates (cleaning.py), checks for duplicates, commits
in a single transaction, then refreshes the Google Sheet mirror. Routes only
translate the returned objects into pages and flash messages.

Imports are two-step: analyze_upload() saves nothing and returns a Preview
(ready / auto-corrected / needs review / skipped / duplicate rows); the
person reviews it, fills in what is missing, and confirm_upload() re-runs
the same analysis with those answers and saves the ready rows.

Needs a Flask app context (uses Flask-SQLAlchemy).
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError

import google_sheets as gs
from models import db, Due, Expense, Fundraising, Member, MembershipFee, Sponsorship

from . import cleaning, ingestion, membership_import, public_dataset, sheets_mirror
from .ledgers import LEDGERS

log = logging.getLogger(__name__)

MODELS = {
    "fundraising": Fundraising,
    "sponsorships": Sponsorship,
    "membership_fees": MembershipFee,
    "expenses": Expense,
}

SAVE_FAILED = "The record could not be saved. Nothing was changed. Please try again."

DUES_TAB = "dues"
DUES_SUMMARY_TAB = "dues_summary"


@dataclass
class Outcome:
    ok: bool
    errors: list = field(default_factory=list)
    record: object = None
    mirror_warning: str | None = None


# --------------------------------------------------
# Lookups passed into the (database-free) cleaning step
# --------------------------------------------------
def _members():
    return {
        member.membership_id.casefold(): (member.membership_id, member.status)
        for member in Member.query.all()
    }


def _categories():
    return {
        category.casefold(): category
        for (category,) in db.session.query(Expense.category).distinct()
        if category
    }


def _lookups(ledger_key):
    if ledger_key == "membership_fees":
        return {"members": _members()}
    if ledger_key == "expenses":
        return {"known_categories": _categories()}
    return {}


def _clean(ledger_key, raw, require_active_member=True, lookups=None):
    lookups = lookups if lookups is not None else _lookups(ledger_key)
    return cleaning.clean_record(
        ledger_key,
        raw,
        require_active_member=require_active_member,
        **lookups,
    )


def _values(ledger_key, record):
    return {name: getattr(record, name) for name in LEDGERS[ledger_key].field_names}


# --------------------------------------------------
# Duplicates
# --------------------------------------------------
def _existing_fingerprints(ledger_key, start, end, exclude_id=None):
    """Fingerprints of saved records dated between start and end (one query)."""
    model = MODELS[ledger_key]
    date_column = getattr(model, LEDGERS[ledger_key].date_field)
    query = model.query.filter(date_column >= start, date_column <= end)
    if exclude_id is not None:
        query = query.filter(model.id != exclude_id)
    return {
        cleaning.fingerprint(ledger_key, _values(ledger_key, record))
        for record in query.all()
    }


def _duplicate_message(ledger_key, cleaned):
    ledger = LEDGERS[ledger_key]
    when = cleaned[ledger.date_field].isoformat()
    return (
        f"This looks like a duplicate of an existing {ledger.noun} "
        f"({when}, ₱{cleaned['amount']:,.2f}). If it is a separate transaction, "
        "add a reference number or a note that tells them apart."
    )


def is_duplicate(ledger_key, cleaned, exclude_id=None):
    day = cleaned[LEDGERS[ledger_key].date_field]
    return cleaning.fingerprint(ledger_key, cleaned) in _existing_fingerprints(
        ledger_key, day, day, exclude_id
    )


# --------------------------------------------------
# Google Sheet mirror
# --------------------------------------------------
def mirror(ledger_key):
    """Copy one ledger to its Google Sheet tab. Raises gs.SheetsError."""
    model = MODELS[ledger_key]
    ledger = LEDGERS[ledger_key]
    records = model.query.order_by(
        getattr(model, ledger.date_field), model.id
    ).all()
    rows = []
    for record in records:
        extras = None
        if ledger_key == "membership_fees":
            member = record.member
            extras = {
                "member_name": member.full_name if member else "",
                "org_role": member.org_role if member else "",
            }
        rows.append(sheets_mirror.row_values(
            ledger_key, record.id, _values(ledger_key, record),
            created_at=record.created_at, extras=extras,
        ))
    sheets_mirror.push_ledger(ledger_key, rows)


def _dues_rows():
    return Due.query.order_by(Due.year, Due.quarter, Due.membership_id).all()


def mirror_dues():
    """PRIVATE 'dues' tab: per-member status (names included)."""
    header = ["membership_id", "member_name", "year", "quarter", "period",
              "amount_due", "amount_paid", "balance", "status"]
    rows = [header]
    for due in _dues_rows():
        rows.append([
            due.membership_id,
            due.member.full_name if due.member else "",
            due.year, due.quarter, f"{due.year}-{due.quarter}",
            float(due.amount_due), float(due.amount_paid), float(due.balance),
            due.status,
        ])
    gs.replace_derived_tab(DUES_TAB, rows)


def mirror_public():
    """Rebuild the PUBLIC tabs used by Looker Studio: 'transactions' (all
    ledgers, no personal data) and 'dues_summary' (totals per quarter, no
    names). Raises gs.SheetsError."""
    rows_by_ledger = {
        key: [_values(key, record) for record in MODELS[key].query.all()]
        for key in LEDGERS
    }
    gs.replace_derived_tab(
        public_dataset.PUBLIC_TAB,
        public_dataset.build_table(rows_by_ledger),
    )
    gs.replace_derived_tab(
        DUES_SUMMARY_TAB,
        public_dataset.build_dues_summary(_dues_rows()),
    )


def safe_mirror(ledger_key, include_dues=False):
    """Mirror the ledger and the public tabs if enabled. Returns a warning
    message instead of raising."""
    if not sheets_mirror.is_enabled():
        return None
    try:
        mirror(ledger_key)
        if include_dues:
            mirror_dues()
        mirror_public()
    except gs.SheetsError as error:
        log.warning("Sheet mirror failed for %s: %s", ledger_key, getattr(error, "hint", ""))
        return sheets_mirror.warning_for(error)
    except Exception:  # noqa: BLE001 - the database save already succeeded
        log.exception("Unexpected error mirroring %s", ledger_key)
        return sheets_mirror.warning_for("unexpected error")
    return None


def resync_all():
    """Mirror every ledger, the dues and the public tabs. Returns [(label, ok, message)]."""
    jobs = [(ledger.label, lambda key=key: mirror(key)) for key, ledger in LEDGERS.items()]
    jobs.append(("Dues", mirror_dues))
    jobs.append(("Public transactions", mirror_public))

    results = []
    for label, job in jobs:
        try:
            job()
            results.append((label, True, "synced"))
        except gs.SheetsError as error:
            hint = getattr(error, "hint", "")
            results.append((label, False, f"{error} {hint}".strip()))
        except Exception:  # noqa: BLE001
            log.exception("Unexpected error mirroring %s", label)
            results.append((label, False, "unexpected error (see server log)"))
    return results


# --------------------------------------------------
# Single-record writes
# --------------------------------------------------
def _commit():
    try:
        db.session.commit()
        return True
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Financial record commit failed")
        return False


def create(ledger_key, raw):
    cleaned, errors = _clean(ledger_key, raw, require_active_member=True)
    if errors:
        return Outcome(False, errors)
    if is_duplicate(ledger_key, cleaned):
        return Outcome(False, [_duplicate_message(ledger_key, cleaned)])

    record = MODELS[ledger_key](**cleaned)
    db.session.add(record)
    if not _commit():
        return Outcome(False, [SAVE_FAILED])
    return Outcome(True, record=record, mirror_warning=safe_mirror(ledger_key))


def update(ledger_key, record_id, raw):
    record = db.session.get(MODELS[ledger_key], record_id)
    if record is None:
        return Outcome(False, ["That record no longer exists."])

    # Fields the edit form does not send keep their saved value, so an older
    # form can never wipe Activity, Income type, Year, ...
    merged = _values(ledger_key, record)
    merged.update({name: raw.get(name) for name in merged if name in raw})

    # Editing an old payment of a member who has since left is allowed.
    cleaned, errors = _clean(ledger_key, merged, require_active_member=False)
    if errors:
        return Outcome(False, errors)
    if is_duplicate(ledger_key, cleaned, exclude_id=record.id):
        return Outcome(False, [_duplicate_message(ledger_key, cleaned)])

    for name, value in cleaned.items():
        setattr(record, name, value)
    if not _commit():
        return Outcome(False, [SAVE_FAILED])
    return Outcome(True, record=record, mirror_warning=safe_mirror(ledger_key))


def delete(ledger_key, record_id):
    record = db.session.get(MODELS[ledger_key], record_id)
    if record is None:
        return Outcome(False, ["That record no longer exists."])
    db.session.delete(record)
    if not _commit():
        return Outcome(False, ["The record could not be deleted. Please try again."])
    return Outcome(True, mirror_warning=safe_mirror(ledger_key))


# --------------------------------------------------
# Imports: preview, then confirm
# --------------------------------------------------
@dataclass
class Preview:
    ledger_key: str
    quarter: str | None = None
    total_rows: int = 0
    ready: list = field(default_factory=list)       # {row, display, corrections}
    review: list = field(default_factory=list)      # {row, display, problems}
    skipped: list = field(default_factory=list)     # {row, reason}
    duplicates: list = field(default_factory=list)  # {row, reason}
    new_members: list = field(default_factory=list) # display names to be created
    dues_updates: int = 0
    # what confirm_upload() saves
    records: list = field(default_factory=list)     # cleaned ledger rows
    dues: list = field(default_factory=list)        # dues dicts
    members_to_create: dict = field(default_factory=dict)  # placeholder -> spec


@dataclass
class ImportReport:
    added: int = 0
    dues_saved: int = 0
    members_created: int = 0
    left_for_review: int = 0
    skipped: int = 0
    duplicates: int = 0
    error: str | None = None
    mirror_warning: str | None = None


def _display_value(value):
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def _corrections(ledger_key, raw, cleaned):
    """['Amount: "P 3,000.00" -> 3000.00', ...] for values the cleaner changed."""
    changes = []
    for fld in LEDGERS[ledger_key].fields:
        # Re-formatting a valid date (8/31/2025 -> 2025-08-31) is not news.
        if fld.name not in raw or fld.kind == "date":
            continue
        before = cleaning.collapse(raw.get(fld.name))
        after = _display_value(cleaned.get(fld.name))
        if before != after and before.casefold() != after.casefold():
            changes.append(f'{fld.label}: "{before or "blank"}" → {after or "blank"}')
    return changes


def _display(ledger_key, values):
    ledger = LEDGERS[ledger_key]
    label = {
        "fundraising": values.get("activity") or values.get("income_type") or "",
        "sponsorships": values.get("sponsor_name") or "",
        "expenses": values.get("activity") or values.get("category") or "",
        "membership_fees": values.get("membership_id") or "",
    }[ledger_key]
    detail = {
        "fundraising": values.get("income_type") or "",
        "sponsorships": values.get("activity") or "",
        "expenses": " · ".join(filter(None, [cleaning.collapse(values.get("category")),
                                             cleaning.collapse(values.get("description"))])),
        "membership_fees": values.get("quarter") or "",
    }[ledger_key]
    return {
        "date": _display_value(values.get(ledger.date_field)) or cleaning.collapse(values.get(ledger.date_field)),
        "label": cleaning.collapse(label),
        "detail": cleaning.collapse(detail),
        "amount": _display_value(values.get("amount")) if isinstance(values.get("amount"), Decimal)
        else cleaning.collapse(values.get("amount")),
    }


def analyze_upload(ledger_key, headers, rows, quarter=None, overrides=None):
    """Build a Preview without saving anything. Raises ingestion.IngestionError."""
    overrides = overrides or {}
    if ledger_key == "membership_fees" and membership_import.is_treasurer_format(headers):
        if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
            raise ingestion.IngestionError(
                "Choose the quarter for this membership-fee sheet (or put Q1-Q4 in the file name)."
            )
        return _analyze_fee_sheet(headers, rows, quarter, overrides)
    return _analyze_ledger(ledger_key, headers, rows, overrides)


def _analyze_ledger(ledger_key, headers, rows, overrides):
    ledger = LEDGERS[ledger_key]
    matched = ingestion.match_columns(ledger_key, headers, rows)
    preview = Preview(ledger_key=ledger_key, total_rows=len(matched))
    lookups = _lookups(ledger_key)
    date_label = ledger.field(ledger.date_field).label + " "

    valid = []
    for row_number, raw in matched:
        fix = overrides.get(row_number, {})
        if fix.get("date"):
            raw = {**raw, ledger.date_field: fix["date"]}
        # Imports usually hold past payments, so inactive members are allowed.
        cleaned, errors = _clean(ledger_key, raw, require_active_member=False, lookups=lookups)
        other = [e for e in errors if not e.startswith(date_label)]
        if other:
            preview.skipped.append({"row": row_number, "reason": " ".join(errors)})
        elif errors:
            shown = cleaning.collapse(raw.get(ledger.date_field)) or "blank"
            preview.review.append({
                "row": row_number,
                "display": _display(ledger_key, {**raw, **{k: v for k, v in cleaned.items() if v is not None}}),
                "problems": [("date", f"Date '{shown}': {errors[0][len(date_label):]} Enter the correct date.")],
            })
        else:
            valid.append((row_number, raw, cleaned))

    if valid:
        dates = [cleaned[ledger.date_field] for _, _, cleaned in valid]
        existing = _existing_fingerprints(ledger_key, min(dates), max(dates))
    else:
        existing = set()

    seen = {}
    for row_number, raw, cleaned in valid:
        key = cleaning.fingerprint(ledger_key, cleaned)
        if key in existing:
            preview.duplicates.append({"row": row_number, "reason": "already recorded in the system"})
            continue
        if key in seen:
            preview.duplicates.append({"row": row_number, "reason": f"same as row {seen[key]} in this file"})
            continue
        seen[key] = row_number
        preview.records.append(cleaned)
        preview.ready.append({
            "row": row_number,
            "display": _display(ledger_key, cleaned),
            "corrections": _corrections(ledger_key, raw, cleaned),
        })
    return preview


def _analyze_fee_sheet(headers, rows, quarter, overrides):
    today = date.today()
    members = Member.query.all()
    index = membership_import.MemberIndex([
        (m.membership_id, m.first_name, m.middle_name, m.last_name, m.status) for m in members
    ])
    try:
        items = membership_import.analyze(headers, rows, quarter, index, today, overrides)
    except ValueError as error:
        raise ingestion.IngestionError(str(error))

    preview = Preview(ledger_key="membership_fees", quarter=quarter, total_rows=len(items))
    member_lookup = {m.membership_id.casefold(): (m.membership_id, m.status) for m in members}
    placeholders = {}            # person key -> placeholder id
    existing_dues = {
        (d.membership_id, d.year, d.quarter) for d in Due.query.filter_by(quarter=quarter).all()
    }

    payments = []
    seen_periods = {}
    for item in items:
        base = {
            "date": _display_value(item.payment["payment_date"]) if item.payment and item.payment["payment_date"] else "",
            "label": item.name,
            "detail": f"{item.year or '?'}-{quarter} · {(item.status or '').upper()}",
            "amount": f"{item.amount_paid:.2f}",
        }
        if item.error:
            preview.skipped.append({"row": item.row, "reason": f"{item.name}: {item.error}"})
            continue
        if item.review:
            preview.review.append({"row": item.row, "display": base, "problems": item.review})
            continue

        member_ref = item.membership_id
        if member_ref is None and item.new_member:
            member_ref = placeholders.get(item.person)
            if member_ref is None:
                member_ref = f"__new_{len(placeholders) + 1}"
                placeholders[item.person] = member_ref
                preview.members_to_create[member_ref] = item.new_member
                preview.new_members.append(item.name)
                member_lookup[member_ref.casefold()] = (member_ref, item.new_member["status"])

        period = (member_ref, item.year, quarter)
        if period in seen_periods:
            preview.duplicates.append({
                "row": item.row,
                "reason": f"{item.name} {item.year}-{quarter} is already on row {seen_periods[period]}",
            })
            continue
        seen_periods[period] = item.row

        if (member_ref, item.year, quarter) in existing_dues:
            preview.dues_updates += 1
        preview.dues.append({
            "membership_id": member_ref, "year": item.year, "quarter": quarter,
            "amount_due": item.amount_due, "amount_paid": item.amount_paid,
            "balance": item.balance, "status": item.status,
        })

        corrections = list(item.notes)
        if item.payment:
            payment_raw = {**item.payment, "membership_id": member_ref}
            cleaned, errors = cleaning.clean_record(
                "membership_fees", payment_raw, today=today,
                members=member_lookup, require_active_member=False,
            )
            if errors:
                preview.skipped.append({"row": item.row, "reason": f"{item.name}: " + " ".join(errors)})
                preview.dues.pop()
                continue
            payments.append((item.row, cleaned))
        preview.ready.append({"row": item.row, "display": base, "corrections": corrections})

    # Payment duplicates against what is already saved.
    real = [(row, cleaned) for row, cleaned in payments if not cleaned["membership_id"].startswith("__new_")]
    if real:
        dates = [cleaned["payment_date"] for _, cleaned in real]
        existing = _existing_fingerprints("membership_fees", min(dates), max(dates))
    else:
        existing = set()
    seen = set()
    for row, cleaned in payments:
        key = cleaning.fingerprint("membership_fees", cleaned)
        if key in existing or key in seen:
            # The dues line is still saved; only the payment is not repeated.
            preview.duplicates.append({"row": row, "reason": "payment already recorded (dues status still updated)"})
            continue
        seen.add(key)
        preview.records.append(cleaned)
    return preview


def _new_membership_id(taken):
    year = date.today().year
    prefix = f"KNYC-{year}-"
    numbers = [int(mid[len(prefix):]) for mid in taken if mid.startswith(prefix) and mid[len(prefix):].isdigit()]
    number = max(numbers, default=0) + 1
    while f"{prefix}{number:03d}" in taken:
        number += 1
    return f"{prefix}{number:03d}"


def confirm_upload(ledger_key, headers, rows, quarter=None, overrides=None):
    """Re-run the analysis with the reviewer's answers and save the ready rows."""
    preview = analyze_upload(ledger_key, headers, rows, quarter, overrides)
    report = ImportReport(
        left_for_review=len(preview.review),
        skipped=len(preview.skipped),
        duplicates=len(preview.duplicates),
    )

    id_map = {}
    if preview.members_to_create:
        taken = {mid for (mid,) in db.session.query(Member.membership_id)}
        for placeholder, spec in preview.members_to_create.items():
            new_id = _new_membership_id(taken)
            taken.add(new_id)
            id_map[placeholder] = new_id
            db.session.add(Member(membership_id=new_id, **spec))
        db.session.flush()
        report.members_created = len(id_map)

    model = MODELS[ledger_key]
    for cleaned in preview.records:
        if ledger_key == "membership_fees":
            cleaned = {**cleaned, "membership_id": id_map.get(cleaned["membership_id"], cleaned["membership_id"])}
        db.session.add(model(**cleaned))
        report.added += 1

    for due in preview.dues:
        membership_id = id_map.get(due["membership_id"], due["membership_id"])
        record = Due.query.filter_by(
            membership_id=membership_id, year=due["year"], quarter=due["quarter"]
        ).first()
        if record is None:
            record = Due(membership_id=membership_id, year=due["year"], quarter=due["quarter"])
            db.session.add(record)
        record.amount_due = due["amount_due"]
        record.amount_paid = due["amount_paid"]
        record.balance = due["balance"]
        record.status = due["status"]
        report.dues_saved += 1

    if report.added or report.dues_saved or report.members_created:
        if not _commit():
            return ImportReport(error="The import could not be saved. Nothing was changed.")
        report.mirror_warning = safe_mirror(ledger_key, include_dues=bool(preview.dues))
    return report
