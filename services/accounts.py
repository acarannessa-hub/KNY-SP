"""Self-service password reset by email.

    request_reset(email, ip, link_for)   -> emails a one-time link (or silently does nothing)
    check_token(token)                   -> is this link still usable?
    complete_reset(token, new_password)  -> sets the new password in Supabase Auth

Security notes
- The page always answers the same way, so it cannot be used to find out
  which emails have accounts.
- Only a SHA-256 hash of the link is stored; the email history stores the
  email with the link removed.
- A link expires after 30 minutes, works once, and every other open link for
  the same account stops working when the password changes.
- At most 3 links per account and 10 per network address per hour.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

import supabase_auth
from models import db, Profile, PasswordResetToken
from services.finance import records as finance_records
from services.notifications import messages
from services.notifications import service as notify

log = logging.getLogger(__name__)

TOKEN_MINUTES = 30
INVITE_MINUTES = 72 * 60          # account invitations stay valid for 3 days
MAX_PER_ACCOUNT_PER_HOUR = 3
MAX_PER_IP_PER_HOUR = 10
MIN_PASSWORD_LENGTH = 8

INVALID_LINK = ("This link is invalid or has expired. Each link works only once and for "
                "a limited time. Please request a new one below.")


def _hash(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _aware(dt):
    return messages.as_utc(dt) if dt is not None else None


def _first_name(profile):
    return notify.first_name(profile.member) if profile.member else "there"


def request_reset(email, ip, link_for):
    """Send a reset link if `email` belongs to an active account.

    `link_for(token)` builds the full URL. Returns a status for logs/tests:
    sent, unknown, inactive, limited, failed."""
    email = (email or "").strip().lower()
    if not email:
        return "unknown"
    profile = Profile.query.filter(db.func.lower(Profile.email) == email).first()
    if profile is None:
        return "unknown"
    if profile.status != "active":
        return "inactive"

    hour_ago = _now() - timedelta(hours=1)
    recent_for_account = PasswordResetToken.query.filter(
        PasswordResetToken.profile_id == profile.id,
        PasswordResetToken.created_at >= hour_ago,
    ).count()
    recent_for_ip = PasswordResetToken.query.filter(
        PasswordResetToken.requested_ip == (ip or "")[:64],
        PasswordResetToken.created_at >= hour_ago,
    ).count() if ip else 0
    if recent_for_account >= MAX_PER_ACCOUNT_PER_HOUR or recent_for_ip >= MAX_PER_IP_PER_HOUR:
        return "limited"

    return _email_link(profile, ip, link_for, TOKEN_MINUTES, "password_reset",
                       "password reset request")


def _issue_token(profile, ip, minutes):
    """Store the hash of a new one-time link; returns the token (or None)."""
    token = secrets.token_urlsafe(32)
    db.session.add(PasswordResetToken(
        profile_id=profile.id,
        token_hash=_hash(token),
        created_at=_now(),
        expires_at=_now() + timedelta(minutes=minutes),
        requested_ip=(ip or "")[:64] or None,
    ))
    try:
        db.session.commit()
        return token
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Could not save a password link token")
        return None


def _email_link(profile, ip, link_for, minutes, kind, sent_by, role_label=""):
    token = _issue_token(profile, ip, minutes)
    if token is None:
        return "failed"
    link = link_for(token)
    if kind == "account_invite":
        subject, body = messages.account_invite(_first_name(profile), link, profile.email,
                                                role_label, minutes // 60)
    else:
        subject, body = messages.password_reset(_first_name(profile), link, minutes)
    item = notify.Outgoing(
        member=profile.member, email=profile.email, subject=subject, body=body,
        name=profile.member.full_name if profile.member else profile.email,
        log_body=body.replace(link, "[link removed]"),
    )
    result = notify.send_batch(kind, [item], sent_by=sent_by)
    if result.sent:
        return "sent"
    return "not_configured" if result.error and "not set up" in result.error else "failed"


def send_reset_link(profile, link_for, admin_email):
    """An administrator emails someone a reset link (no hourly limit)."""
    if profile.status != "active":
        return "inactive"
    return _email_link(profile, None, link_for, TOKEN_MINUTES, "password_reset",
                       admin_email or "administrator")


def send_invite(profile, link_for, admin_email, role_label):
    """Email a new account owner a link to set their first password (valid 3 days)."""
    return _email_link(profile, None, link_for, INVITE_MINUTES, "account_invite",
                       admin_email or "administrator", role_label=role_label)


def random_password():
    """A password nobody knows, used until an invited person sets their own."""
    return secrets.token_urlsafe(24) + "aA1!"


def check_token(token):
    """(PasswordResetToken, Profile) if the link can still be used, else (None, None)."""
    if not token or len(token) > 200:
        return None, None
    row = PasswordResetToken.query.filter_by(token_hash=_hash(token)).first()
    if row is None or row.used_at is not None or _aware(row.expires_at) <= _now():
        return None, None
    profile = db.session.get(Profile, row.profile_id)
    if profile is None or profile.status != "active":
        return None, None
    return row, profile


def complete_reset(token, new_password, confirm_password):
    """(ok, message). On success the link and all other open links are used up."""
    row, profile = check_token(token)
    if row is None:
        return False, INVALID_LINK
    if len(new_password or "") < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if new_password != confirm_password:
        return False, "The two passwords do not match."

    try:
        supabase_auth.update_user(profile.id, password=new_password)
    except supabase_auth.AuthError as error:
        return False, str(error)

    now = _now()
    PasswordResetToken.query.filter(
        PasswordResetToken.profile_id == profile.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)
    finance_records.audit("password_reset", "account", actor=profile, record_id=profile.id,
                          summary=f"Password reset by email link for {profile.email}")
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Password was changed but the reset link could not be marked used")

    notify_password_changed(profile, "using a reset link sent to this email")
    return True, "Your password has been changed. You can now log in with it."


def notify_password_changed(profile, how):
    """Tell the account owner their password changed (best effort, never raises)."""
    try:
        subject, body = messages.password_changed(_first_name(profile), how)
        item = notify.Outgoing(member=profile.member, email=profile.email,
                               subject=subject, body=body,
                               name=profile.member.full_name if profile.member else profile.email)
        notify.send_batch("password_changed", [item], sent_by="account security")
    except Exception:   # noqa: BLE001 - a notice must never break the password change
        db.session.rollback()
        log.exception("Could not send the password-changed notice")
