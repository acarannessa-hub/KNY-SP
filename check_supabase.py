"""
check_supabase.py -- verify your Supabase setup BEFORE changing the app.

READ-ONLY. It never creates, edits or deletes anything.
It never prints your keys, tokens, password or connection string.

Checks:
  1. Database   : can we connect, do the 4 tables exist, is there a profile
  2. Admin login: does YOUR email + password work, and is your profile an
                  active admin  (you type the password; it is not stored)
  3. Secret key : does the server-side key work for admin actions
                  (needed later to create users / reset passwords)

Settings are read from your .env file (same folder you run this from):

  SUPABASE_URL              https://<project-ref>.supabase.co
  SUPABASE_PUBLISHABLE_KEY  sb_publishable_...   (legacy: SUPABASE_ANON_KEY)
  SUPABASE_SECRET_KEY       sb_secret_...        (legacy: SUPABASE_SERVICE_ROLE_KEY)
  SUPABASE_DB_URL           postgresql://postgres.<ref>:<password>@...pooler.supabase.com:6543/postgres

NOTE: the variable is SUPABASE_DB_URL on purpose. Your existing DATABASE_URL
still points to RDS and the running app keeps using it until we switch.

Usage:
  python check_supabase.py
  python check_supabase.py --skip-login     (skip the password prompt)
"""

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REQUIRED_TABLES = {"members", "profiles", "attendance", "export_requests"}


# --------------------------------------------------
# Small helpers
# --------------------------------------------------
def normalize_db_url(url):
    """Supabase gives 'postgresql://...'; SQLAlchemy needs a driver name."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


def api_headers(key):
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "User-Agent": "kny-sp-check/1.0",
    }
    # New sb_publishable_/sb_secret_ keys go in the apikey header ONLY.
    # Legacy JWT keys (anon / service_role) are also sent as Bearer.
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def http_json(method, url, key, body=None, timeout=20):
    """Return (status_code, parsed_json). Raises ConnectionError if the
    server cannot be reached at all."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url, data=data, headers=api_headers(key), method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read() or b"{}")
        except ValueError:
            payload = {}
        return error.code, payload
    except urllib.error.URLError as error:
        raise ConnectionError(str(error.reason))


def say(ok, label, detail=""):
    mark = {True: "PASS", False: "FAIL", None: "SKIP"}[ok]
    print(f"[{mark}] {label}" + (f" -- {detail}" if detail else ""))


# --------------------------------------------------
# Check 1: database
# --------------------------------------------------
def check_database(db_url):
    """Returns (ok, engine_or_None)."""
    try:
        engine = create_engine(normalize_db_url(db_url), poolclass=NullPool)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except ModuleNotFoundError as error:
        say(False, "Database connection",
            f"missing package: {error.name}. Run: pip install psycopg2-binary")
        return False, None
    except SQLAlchemyError as error:
        reason = str(getattr(error, "orig", error)).strip().splitlines()[0]
        say(False, "Database connection", reason)
        print("       Tips: use the TRANSACTION POOLER string (port 6543) from "
              "the Connect button; if your DB password has symbols like "
              "@ : / # ?, reset it to letters+numbers only.")
        return False, None
    say(True, "Database connection")

    schema = "public" if engine.dialect.name == "postgresql" else None
    found = set(inspect(engine).get_table_names(schema=schema))
    missing = sorted(REQUIRED_TABLES - found)
    if missing:
        say(False, "Tables", "missing: " + ", ".join(missing)
            + "  (run 01_schema.sql in the SQL Editor)")
        return False, engine
    say(True, "Tables", "members, profiles, attendance, export_requests")

    with engine.connect() as connection:
        rows = connection.execute(
            text("select email, role, status from profiles order by email")
        ).fetchall()
    admins = [r for r in rows if r[1] == "admin" and r[2] == "active"]
    if not admins:
        say(False, "Admin profile",
            f"{len(rows)} profile(s) but no active admin "
            "(run 02_bootstrap_admin.sql)")
        return False, engine
    say(True, "Admin profile",
        f"{len(rows)} profile(s); active admin: "
        + ", ".join(r[0] for r in admins))
    return True, engine


# --------------------------------------------------
# Check 2: login through Supabase Auth
# --------------------------------------------------
def check_login(supabase_url, publishable_key, engine, email, password):
    url = f"{supabase_url}/auth/v1/token?grant_type=password"
    try:
        status, payload = http_json(
            "POST", url, publishable_key,
            {"email": email, "password": password}
        )
    except ConnectionError as error:
        say(False, "Admin login", f"cannot reach Supabase: {error}")
        return False

    if status != 200:
        code = payload.get("error_code") or payload.get("error") or status
        message = payload.get("msg") or payload.get("error_description") or ""
        hint = ""
        if code == "invalid_credentials":
            hint = "  (wrong email/password, or user not created in step 3)"
        elif code == "email_not_confirmed":
            hint = "  (recreate the user with 'Auto Confirm User' ON)"
        elif status in (401, 403):
            hint = "  (check SUPABASE_PUBLISHABLE_KEY)"
        say(False, "Admin login", f"{code} {message}".strip() + hint)
        return False

    user_id = str((payload.get("user") or {}).get("id") or "")
    if not user_id:
        say(False, "Admin login", "login worked but no user id returned")
        return False
    say(True, "Admin login", "Supabase Auth accepted your email + password")

    if engine is None:
        say(None, "Profile link", "skipped (database check failed)")
        return True
    with engine.connect() as connection:
        row = connection.execute(
            text("select role, status from profiles "
                 "where cast(id as text) = :uid"),
            {"uid": user_id},
        ).first()
    if row is None:
        say(False, "Profile link",
            "login works but has no profile row (run 02_bootstrap_admin.sql "
            "with this same email)")
        return False
    ok = row[0] == "admin" and row[1] == "active"
    say(ok, "Profile link", f"role={row[0]}, status={row[1]}")
    return ok


# --------------------------------------------------
# Check 3: secret (server-side) key
# --------------------------------------------------
def check_secret_key(supabase_url, secret_key):
    if not secret_key:
        say(None, "Secret key", "SUPABASE_SECRET_KEY not set (needed later)")
        return True
    url = f"{supabase_url}/auth/v1/admin/users?page=1&per_page=1"
    try:
        status, payload = http_json("GET", url, secret_key)
    except ConnectionError as error:
        say(False, "Secret key", f"cannot reach Supabase: {error}")
        return False
    if status == 200:
        say(True, "Secret key", "server-side admin access works")
        return True
    message = payload.get("msg") or payload.get("message") or ""
    say(False, "Secret key", f"HTTP {status} {message}".strip())
    return False


# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Check Supabase setup.")
    parser.add_argument("--skip-login", action="store_true",
                        help="do not prompt for email/password")
    args = parser.parse_args()

    supabase_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    publishable = (os.getenv("SUPABASE_PUBLISHABLE_KEY")
                   or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    secret = (os.getenv("SUPABASE_SECRET_KEY")
              or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    db_url = (os.getenv("SUPABASE_DB_URL") or "").strip()

    missing = [name for name, value in (
        ("SUPABASE_URL", supabase_url),
        ("SUPABASE_PUBLISHABLE_KEY", publishable),
        ("SUPABASE_DB_URL", db_url),
    ) if not value]
    if missing:
        sys.exit("Missing in .env: " + ", ".join(missing))
    local = supabase_url.startswith(("http://127.0.0.1", "http://localhost"))
    if not (supabase_url.startswith("https://") or local):
        sys.exit("SUPABASE_URL must look like https://<project-ref>.supabase.co")

    print("KNY-SP Supabase check\n" + "=" * 24)
    results = []

    db_ok, engine = check_database(db_url)
    results.append(db_ok)

    if args.skip_login:
        say(None, "Admin login", "skipped (--skip-login)")
    else:
        print("\nType the email + password of the admin account you made in "
              "Supabase.\n(The password is hidden and is not saved anywhere.)")
        email = input("Admin email: ").strip()
        password = getpass.getpass("Admin password: ")
        results.append(
            check_login(supabase_url, publishable, engine, email, password)
        )

    results.append(check_secret_key(supabase_url, secret))

    print("\n" + ("ALL CHECKS PASSED." if all(results)
                  else "SOME CHECKS FAILED - fix the FAIL lines above, then "
                       "run again."))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
