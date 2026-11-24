"""
Database operations for the financial ledgers.

Every write path goes through here:

    form add/edit  -> create() / update()
    CSV / Excel    -> import_file()
    delete         -> delete()

Each one cleans and validates (cleaning.py), checks for duplicates, commits
in a single transaction, then refreshes the Google Sheet mirror. Routes only
translate the returned Outcome / ImportReport into flash messages.

Needs a Flask app context (uses Flask-SQLAlchemy).
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.exc import SQLAlchemyError

import google_sheets as gs
from models import db, Expense, Fundraising, Member, MembershipFee, Sponsorship

from . import cleaning, ingestion, sheets_mirror
from .ledgers import LEDGERS

log = logging.getLogger(__name__)

MODELS = {
    "fundraising": Fundraising,
    "sponsorships": Sponsorship,
    "membership_fees": MembershipFee,
    "expenses": Expense,
}

SAVE_FAILED = "The record could not be saved. Nothing was changed. Please try again."


@dataclass
class Outcome:
    ok: bool
    errors: list = field(default_factory=list)
    record: object = None
    mirror_warning: str | None = None


@dataclass
class ImportReport:
    total_rows: int = 0
    added: int = 0
    problems: list = field(default_factory=list)   # "Row 5: ..." messages
    duplicates: int = 0
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


def _clean(ledger_key, raw, require_active_member=True, lookups=None):
    lookups = lookups if lookups is not None else _lookups(ledger_key)
    return cleaning.clean_record(
        ledger_key,
        raw,
        require_active_member=require_active_member,
        **lookups,
    )


def _lookups(ledger_key):
    if ledger_key == "membership_fees":
        return {"members": _members()}
    if ledger_key == "expenses":
        return {"known_categories": _categories()}
    return {}


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


def safe_mirror(ledger_key):
    """Mirror if enabled. Returns a warning message instead of raising."""
    if not sheets_mirror.is_enabled():
        return None
    try:
        mirror(ledger_key)
    except gs.SheetsError as error:
        log.warning("Sheet mirror failed for %s: %s", ledger_key, getattr(error, "hint", ""))
        return sheets_mirror.warning_for(error)
    except Exception:  # noqa: BLE001 - the database save already succeeded
        log.exception("Unexpected error mirroring %s", ledger_key)
        return sheets_mirror.warning_for("unexpected error")
    return None


def resync_all():
    """Mirror every ledger. Returns [(label, ok, message)]."""
    results = []
    for key, ledger in LEDGERS.items():
        try:
            mirror(key)
            results.append((ledger.label, True, "synced"))
        except gs.SheetsError as error:
            hint = getattr(error, "hint", "")
            results.append((ledger.label, False, f"{error} {hint}".strip()))
        except Exception:  # noqa: BLE001
            log.exception("Unexpected error mirroring %s", key)
            results.append((ledger.label, False, "unexpected error (see server log)"))
    return results


# --------------------------------------------------
# Writes
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

    # Editing an old payment of a member who has since left is allowed.
    cleaned, errors = _clean(ledger_key, raw, require_active_member=False)
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


def import_file(ledger_key, filename, data):
    """
    Bulk import from CSV / XLSX. Valid, non-duplicate rows are saved in ONE
    transaction; every other row is reported with its row number.
    Raises ingestion.IngestionError when the file itself is unusable.
    """
    rows = ingestion.read_rows(ledger_key, filename, data)
    report = ImportReport(total_rows=len(rows))
    ledger = LEDGERS[ledger_key]
    lookups = _lookups(ledger_key)

    valid = []
    for row_number, raw in rows:
        # Imports usually hold past payments, so inactive members are allowed.
        cleaned, errors = _clean(
            ledger_key, raw, require_active_member=False, lookups=lookups
        )
        if errors:
            report.problems.append(f"Row {row_number}: " + " ".join(errors))
        else:
            valid.append((row_number, cleaned))

    if valid:
        dates = [cleaned[ledger.date_field] for _, cleaned in valid]
        existing = _existing_fingerprints(ledger_key, min(dates), max(dates))
    else:
        existing = set()

    seen = {}
    model = MODELS[ledger_key]
    for row_number, cleaned in valid:
        key = cleaning.fingerprint(ledger_key, cleaned)
        if key in existing:
            report.duplicates += 1
            report.problems.append(f"Row {row_number}: already recorded in the system.")
            continue
        if key in seen:
            report.duplicates += 1
            report.problems.append(
                f"Row {row_number}: duplicate of row {seen[key]} in this file."
            )
            continue
        seen[key] = row_number
        db.session.add(model(**cleaned))
        report.added += 1

    if report.added:
        if not _commit():
            report.problems.insert(0, "The import could not be saved. No rows were added.")
            report.added = 0
            return report
        report.mirror_warning = safe_mirror(ledger_key)
    return report
