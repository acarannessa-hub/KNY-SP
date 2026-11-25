"""Wording of every email the website sends. Each function returns (subject, body)."""

from datetime import date, timezone
from zoneinfo import ZoneInfo

from .mailer import ORG_NAME

MANILA = ZoneInfo("Asia/Manila")

WARNING_CATEGORIES = {
    "dues": "Unpaid membership dues",
    "meetings": "Missed meetings",
    "conduct": "Conduct",
    "other": "Other",
}


def as_utc(dt):
    """Stored times are UTC; some databases hand them back without a zone."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def local(dt):
    return as_utc(dt).astimezone(MANILA)


def when_text(dt):
    d = local(dt)
    hour = d.strftime("%I").lstrip("0") or "12"
    return f"{d.strftime('%A')}, {d.day} {d.strftime('%B %Y')}, {hour}:{d.strftime('%M %p')}"


def short_date(dt):
    d = local(dt)
    return f"{d.strftime('%b')} {d.day}"


def kind_word(event):
    return "meeting" if event.kind == "meeting" else "event"


def _details(event):
    lines = [f"What: {event.title}", f"When: {when_text(event.starts_at)}"]
    if event.location:
        lines.append(f"Where: {event.location}")
    text = "\n".join(lines)
    if event.description:
        text += "\n\n" + event.description.strip()
    return text


def _sign_off():
    return f"Thank you,\n{ORG_NAME}"


def event_reminder(event, first_name, today):
    days = (local(event.starts_at).date() - today).days
    if days <= 0:
        phrase, short = "today", "today"
    elif days == 1:
        phrase, short = "tomorrow", "tomorrow"
    else:
        phrase, short = f"in {days} days", f"in {days} days"
    subject = f"Reminder: {event.title} {short} ({short_date(event.starts_at)})"
    body = (
        f"Hi {first_name},\n\n"
        f"This is a reminder that our {kind_word(event)} is {phrase}.\n\n"
        f"{_details(event)}\n\n"
        f"See you there!\n\n{_sign_off()}"
    )
    return subject, body


def event_announcement(event, first_name):
    label = "New meeting" if event.kind == "meeting" else "Upcoming event"
    subject = f"{label}: {event.title} ({short_date(event.starts_at)})"
    body = (
        f"Hi {first_name},\n\n"
        f"You're invited to our upcoming {kind_word(event)}.\n\n"
        f"{_details(event)}\n\n"
        f"We'll send you a reminder a few days before.\n\n{_sign_off()}"
    )
    return subject, body


def event_cancelled(event, first_name):
    subject = f"Cancelled: {event.title} ({short_date(event.starts_at)})"
    body = (
        f"Hi {first_name},\n\n"
        f"Please note that our {kind_word(event)} \"{event.title}\" scheduled for "
        f"{when_text(event.starts_at)} has been cancelled.\n\n"
        f"We'll let you know if it is rescheduled.\n\n{_sign_off()}"
    )
    return subject, body


def peso(amount):
    return f"₱{amount:,.2f}"


def dues_reminder(first_name, year, quarter, state, balance=None, note=""):
    period = f"{quarter} {year}"   # quarter is "Q1".."Q4"
    subject = f"Reminder: {period} membership dues"
    if state == "partial" and balance:
        status = (f"our records show a partial payment for your {period} membership dues, "
                  f"with a remaining balance of {peso(balance)}.")
    elif state == "unpaid" and balance:
        status = f"our records show that your {period} membership dues of {peso(balance)} are not yet paid."
    else:
        status = f"our records don't show a payment for your {period} membership dues yet."
    body = f"Hi {first_name},\n\nThis is a friendly reminder that {status}"
    if note.strip():
        body += "\n\n" + note.strip()
    body += (
        "\n\nIf you have already paid, please reply with your proof of payment so the "
        "treasurer can update the records, and disregard this reminder.\n\n"
        f"{_sign_off()}"
    )
    return subject, body


def warning(first_name, category, message):
    label = WARNING_CATEGORIES.get(category, "Notice")
    subject = f"Notice from {ORG_NAME}: {label}"
    body = (
        f"Hi {first_name},\n\n{message.strip()}\n\n"
        "If you have questions or concerns, please reply to this email or talk to "
        f"one of the officers.\n\n{_sign_off()}"
    )
    return subject, body


def test_email(sender_name):
    subject = f"Test email from the {ORG_NAME} website"
    body = (
        f"Hi {sender_name},\n\n"
        "This is a test. If you can read this, the website can send email: dues "
        "reminders, meeting and event reminders, and notices will reach members.\n\n"
        f"{_sign_off()}"
    )
    return subject, body


def today_in_manila(now):
    return now.astimezone(MANILA).date() if now else date.today()
