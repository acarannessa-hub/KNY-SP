"""Who gets which email, sending in batches, and the daily automatic reminders.

Every attempt is written to notification_log. A batch never emails the same
member twice: each email first *reserves* a dedupe key in the log (a unique
index), so a double click, a "continue sending" press, or two overlapping
scheduled runs cannot send a duplicate.
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from models import db, Member, Due, Event, NotificationLog
from . import messages
from .mailer import Mailer, MailError, is_configured

log = logging.getLogger(__name__)

KIND_LABELS = {
    "event_reminder": "Meeting/event reminder",
    "event_announcement": "Meeting/event announcement",
    "event_cancelled": "Cancellation notice",
    "dues_reminder": "Dues reminder",
    "warning": "Warning / notice",
    "test": "Test email",
    "password_reset": "Password reset link",
    "password_changed": "Password changed notice",
}

INTERRUPTED = "Sending was interrupted; this email may not have been delivered."


def time_budget():
    """Seconds one request may spend sending before it stops and reports the rest.

    Serverless requests have a time limit, so big batches are sent in rounds."""
    try:
        return max(3.0, float(os.getenv("NOTIFY_TIME_BUDGET") or 8))
    except ValueError:
        return 8.0


def new_batch_id():
    return uuid.uuid4().hex[:16]


def first_name(member):
    return (member.first_name or "").strip().split(" ")[0] or "member"


# --------------------------------------------------
# Recipients
# --------------------------------------------------
def active_members():
    return Member.query.filter_by(status="active").order_by(
        Member.last_name, Member.first_name
    ).all()


def reachable(members):
    """Split members into (with an email, without one)."""
    with_email, without = [], []
    for member in members:
        (with_email if member.notify_email else without).append(member)
    return with_email, without


@dataclass
class Outgoing:
    member: Member | None
    email: str
    subject: str
    body: str
    name: str = ""
    log_body: str | None = None     # what the history stores, if different (e.g. link removed)


@dataclass
class BatchResult:
    sent: int = 0
    failed: int = 0
    already: int = 0
    remaining: int = 0
    error: str = ""
    failures: list = field(default_factory=list)

    @property
    def attempted(self):
        return self.sent + self.failed

    def summary(self):
        parts = [f"{self.sent} sent"]
        if self.failed:
            parts.append(f"{self.failed} failed")
        if self.already:
            parts.append(f"{self.already} already sent earlier")
        if self.remaining:
            parts.append(f"{self.remaining} still to send")
        return ", ".join(parts)


def _reserve(row):
    db.session.add(row)
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def send_batch(kind, outgoing, *, sent_by, dedupe_prefix=None, event_id=None,
               batch_id=None, deadline=None):
    """Send each Outgoing email and log it. Stops at `deadline` (time.monotonic)."""
    result = BatchResult()
    if not outgoing:
        return result
    if not is_configured():
        result.error = ("Email is not set up yet. Add SMTP_USER and SMTP_PASSWORD "
                        "(a Gmail app password) in Vercel, then redeploy.")
        result.remaining = len(outgoing)
        return result
    deadline = deadline or (time.monotonic() + time_budget())

    def key_for(item):
        if not dedupe_prefix:
            return None
        who = item.member.membership_id if item.member is not None else item.email.lower()
        return f"{dedupe_prefix}:{who}"[:120]

    keys = [k for k in (key_for(i) for i in outgoing) if k]
    taken = set()
    if keys:
        taken = {k for (k,) in db.session.query(NotificationLog.dedupe_key)
                 .filter(NotificationLog.dedupe_key.in_(keys))}

    todo = []
    for item in outgoing:
        if key_for(item) in taken:
            result.already += 1
        else:
            todo.append(item)
    if not todo:
        return result

    try:
        with Mailer() as mailer:
            for index, item in enumerate(todo):
                if time.monotonic() > deadline:
                    result.remaining = len(todo) - index
                    break
                row = NotificationLog(
                    kind=kind,
                    batch_id=batch_id,
                    subject=item.subject[:255],
                    body=item.body if item.log_body is None else item.log_body,
                    recipient_email=item.email,
                    membership_id=item.member.membership_id if item.member is not None else None,
                    recipient_name=(item.name or (item.member.full_name if item.member is not None else ""))[:255],
                    event_id=event_id,
                    status="failed",
                    error=INTERRUPTED,
                    sent_by=sent_by,
                    dedupe_key=key_for(item),
                )
                if not _reserve(row):
                    result.already += 1
                    continue
                try:
                    mailer.send(item.email, item.subject, item.body)
                    row.status, row.error = "sent", None
                    result.sent += 1
                except MailError as error:
                    # Free the key so this person can be retried later.
                    row.status, row.error, row.dedupe_key = "failed", str(error), None
                    result.failed += 1
                    result.failures.append((row.recipient_name or item.email, str(error)))
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    log.exception("Could not update a notification log row")
    except MailError as error:
        result.error = str(error)
        result.remaining = len(todo) - result.attempted - result.already
    return result


# --------------------------------------------------
# Meetings and events
# --------------------------------------------------
def event_outgoing(event, builder):
    members, without = reachable(active_members())
    items = []
    for member in members:
        subject, body = builder(event, first_name(member))
        items.append(Outgoing(member=member, email=member.notify_email, subject=subject, body=body))
    return items, without


def reminder_stage(event, now):
    """Which automatic reminder is due for this event right now, if any."""
    if event.status != "scheduled" or messages.as_utc(event.starts_at) <= now:
        return None
    days = (messages.local(event.starts_at).date() - messages.today_in_manila(now)).days
    if days <= 1:
        return "d1"      # the day before (or the morning of, for same-day events)
    if days <= 3:
        return "d3"      # three days before
    return None


def run_daily_reminders(now=None, deadline=None):
    """Called by the daily scheduled job. Returns a short report dict."""
    now = now or datetime.now(timezone.utc)
    deadline = deadline or (time.monotonic() + time_budget())
    report = {"events": 0, "sent": 0, "failed": 0, "remaining": 0, "error": ""}
    if not is_configured():
        report["error"] = "email not configured"
        return report
    upcoming = Event.query.filter(
        Event.status == "scheduled",
        Event.starts_at > now,
        Event.starts_at <= now + timedelta(days=4),
    ).order_by(Event.starts_at).all()
    today = messages.today_in_manila(now)
    for event in upcoming:
        stage = reminder_stage(event, now)
        if not stage:
            continue
        report["events"] += 1
        items, _ = event_outgoing(
            event, lambda e, name: messages.event_reminder(e, name, today)
        )
        result = send_batch(
            "event_reminder", items, sent_by="automatic reminder",
            dedupe_prefix=f"event:{event.id}:{stage}", event_id=event.id,
            deadline=deadline,
        )
        report["sent"] += result.sent
        report["failed"] += result.failed
        report["remaining"] += result.remaining
        if result.error:
            report["error"] = result.error
            break
    return report


def next_reminder_text(event, now):
    """Plain-language note about the next automatic reminder for an event."""
    if event.status != "scheduled":
        return "Cancelled — no reminders"
    if messages.as_utc(event.starts_at) <= now:
        return "Already happened"
    start_day = messages.local(event.starts_at).date()
    today = messages.today_in_manila(now)
    days = (start_day - today).days
    if days > 3:
        return f"Reminders on {(start_day - timedelta(days=3)).strftime('%b %d')} and {(start_day - timedelta(days=1)).strftime('%b %d')}"
    if days > 1:
        return f"3-day reminder due now; next on {(start_day - timedelta(days=1)).strftime('%b %d')}"
    return "Final reminder due now"


# --------------------------------------------------
# Membership dues
# --------------------------------------------------
@dataclass
class DuesRow:
    member: Member
    email: str | None
    state: str            # paid / partial / unpaid / deferred / none
    balance: object = None
    amount_due: object = None

    @property
    def label(self):
        if self.state == "partial":
            return f"Partial — {messages.peso(self.balance)} left"
        if self.state == "unpaid":
            return f"Unpaid — {messages.peso(self.balance)}" if self.balance else "Unpaid"
        if self.state == "none":
            return "No payment recorded"
        return self.state.capitalize()

    @property
    def suggested(self):
        return bool(self.email) and self.state in {"partial", "unpaid"}


def dues_rows(year, quarter):
    dues = {d.membership_id: d for d in Due.query.filter_by(year=year, quarter=quarter)}
    rows = []
    for member in active_members():
        due = dues.get(member.membership_id)
        if due is None:
            state, balance, amount_due = "none", None, None
        else:
            state, balance, amount_due = due.status, due.balance, due.amount_due
            if state == "unpaid" and not balance:
                balance = amount_due
        rows.append(DuesRow(member, member.notify_email, state, balance, amount_due))
    return rows, len(dues)


def current_quarter(now=None):
    today = messages.today_in_manila(now or datetime.now(timezone.utc))
    return today.year, f"Q{(today.month - 1) // 3 + 1}"
