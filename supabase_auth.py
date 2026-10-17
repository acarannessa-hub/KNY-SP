"""
supabase_auth.py -- small client for Supabase Auth (the login service).

Why this file exists
  Passwords no longer live in your database. Supabase Auth stores and checks
  them. Flask still manages the login SESSION (Flask-Login) and still decides
  what each role can do; this module only answers two questions:
    * "Is this email + password correct?"      -> sign_in()
    * "Create / change / remove a login"       -> create_user(), update_user(),
                                                  delete_user()   (admin only)

Settings (environment variables / .env / Vercel):
    SUPABASE_URL              https://<project-ref>.supabase.co
    SUPABASE_PUBLISHABLE_KEY  sb_publishable_...  (used for sign-in)
    SUPABASE_SECRET_KEY       sb_secret_...       (SERVER ONLY: admin actions)

Security notes
  * The secret key is read from the environment only. Never put it in a
    template, in JavaScript, or in GitHub.
  * Every exception message raised here is safe to show to a user. Technical
    details go to the server log, never to the browser.
  * Only the Python standard library is used (no extra packages to install).
"""

import json
import logging
import os
import uuid
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15


class AuthError(Exception):
    """The request was refused. str(error) is safe to show to the user."""


class AuthUnavailable(AuthError):
    """Supabase could not be reached, or the server is misconfigured."""


GENERIC_UNAVAILABLE = (
    "The login service is temporarily unavailable. Please try again."
)


# --------------------------------------------------
# Settings
# --------------------------------------------------
def _setting(*names):
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _base_url():
    url = _setting("SUPABASE_URL").rstrip("/")
    if not url:
        log.error("SUPABASE_URL is not set.")
        raise AuthUnavailable(GENERIC_UNAVAILABLE)
    return url


def _publishable_key():
    key = _setting("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY")
    if not key:
        log.error("SUPABASE_PUBLISHABLE_KEY is not set.")
        raise AuthUnavailable(GENERIC_UNAVAILABLE)
    return key


def _secret_key():
    key = _setting("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        log.error("SUPABASE_SECRET_KEY is not set.")
        raise AuthUnavailable(GENERIC_UNAVAILABLE)
    return key


# --------------------------------------------------
# HTTP plumbing
# --------------------------------------------------
def _headers(key):
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "User-Agent": "kny-sp/1.0",
    }
    # New sb_publishable_ / sb_secret_ keys are sent in "apikey" ONLY.
    # Legacy JWT keys (anon / service_role) are also sent as a Bearer token.
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _call(method, path, key, body=None):
    """Return (status_code, json_payload). Raises AuthUnavailable when
    Supabase cannot be reached at all."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        _base_url() + path, data=data, headers=_headers(key), method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read() or b"{}")
        except ValueError:
            payload = {}
        return error.code, payload
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        log.error("Cannot reach Supabase Auth: %s", error)
        raise AuthUnavailable(GENERIC_UNAVAILABLE) from error


def _error_fields(payload):
    code = payload.get("error_code") or payload.get("code") or ""
    message = (
        payload.get("msg")
        or payload.get("message")
        or payload.get("error_description")
        or ""
    )
    return str(code), str(message)


def _raise_for_admin_error(status, payload):
    """Translate a failed admin call into a safe, readable AuthError."""
    code, message = _error_fields(payload)
    log.warning("Supabase admin call failed: HTTP %s %s %s",
                status, code, message)
    if status >= 500:
        raise AuthUnavailable(GENERIC_UNAVAILABLE)
    if status in (401, 403):
        # Wrong/missing secret key: a server problem, not the user's fault.
        raise AuthUnavailable(GENERIC_UNAVAILABLE)
    if status == 429:
        raise AuthError("Too many requests. Please wait a moment and retry.")
    if code == "email_exists" or "already" in message.lower():
        raise AuthError("A login with that email already exists.")
    if code == "weak_password":
        raise AuthError(
            "That password is too weak. Use a longer or less common password."
        )
    if code in ("validation_failed", "email_address_invalid"):
        raise AuthError("Enter a valid email address.")
    raise AuthError("The login service rejected that request.")


def _as_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise AuthUnavailable(GENERIC_UNAVAILABLE)


# --------------------------------------------------
# Public functions
# --------------------------------------------------
def sign_in(email, password):
    """
    Check an email + password with Supabase Auth.

    Returns {"id": <uuid.UUID>, "email": <str>} when correct, or None when the
    email/password is wrong. Raises AuthError if the service is unavailable or
    rate-limiting this person.
    """
    if not email or not password:
        return None

    status, payload = _call(
        "POST",
        "/auth/v1/token?grant_type=password",
        _publishable_key(),
        {"email": email, "password": password},
    )

    if status == 200:
        user = payload.get("user") or {}
        return {
            "id": _as_uuid(user.get("id")),
            "email": str(user.get("email") or email),
        }

    code, message = _error_fields(payload)
    if status == 429 or code == "over_request_rate_limit":
        raise AuthError(
            "Too many login attempts. Please wait a few minutes and retry."
        )
    if status >= 500:
        log.error("Supabase sign-in server error: HTTP %s", status)
        raise AuthUnavailable(GENERIC_UNAVAILABLE)
    if status in (401, 403):
        # Bad publishable key = our configuration problem.
        log.error("Supabase rejected our publishable key: HTTP %s", status)
        raise AuthUnavailable(GENERIC_UNAVAILABLE)
    # 400/422: wrong credentials, unconfirmed email, malformed email, etc.
    # Treated the same on purpose so we never reveal which emails exist.
    return None


def create_user(email, password):
    """Create a confirmed login. Returns the new user's id (uuid.UUID)."""
    status, payload = _call(
        "POST",
        "/auth/v1/admin/users",
        _secret_key(),
        {"email": email, "password": password, "email_confirm": True},
    )
    if status in (200, 201):
        return _as_uuid(payload.get("id"))
    _raise_for_admin_error(status, payload)


def update_user(user_id, email=None, password=None):
    """Change a login's email and/or password (admin action)."""
    body = {}
    if email is not None:
        body["email"] = email
        body["email_confirm"] = True   # no confirmation mail for admin edits
    if password is not None:
        body["password"] = password
    if not body:
        return
    status, payload = _call(
        "PUT",
        f"/auth/v1/admin/users/{_as_uuid(user_id)}",
        _secret_key(),
        body,
    )
    if status == 200:
        return
    _raise_for_admin_error(status, payload)


def delete_user(user_id):
    """
    Remove a login. Used only to undo create_user() when saving the matching
    profile row fails. Never raises: returns True if removed.
    """
    try:
        status, payload = _call(
            "DELETE",
            f"/auth/v1/admin/users/{_as_uuid(user_id)}",
            _secret_key(),
        )
    except AuthError:
        log.error("Could not delete orphan login %s", user_id)
        return False
    if status in (200, 204):
        return True
    log.error("Could not delete orphan login %s: HTTP %s", user_id, status)
    return False
