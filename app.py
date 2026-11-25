import csv
import hmac
import io
import json
import os
import re
import time
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from xml.sax.saxutils import escape

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
    session,
    send_from_directory,
    Response
)
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import SQLAlchemyError
from functools import wraps
from dotenv import load_dotenv
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from models import (
        db,
    Profile,
    Member,
    Fundraising,
    Sponsorship,
    MembershipFee,
    Expense,
    ExportRequest,
    Due,
    AuditLog,
    Event,
    NotificationLog
)
import supabase_auth
import google_sheets
from services.finance import LEDGERS
from services.finance import ingestion as finance_ingestion
from services.finance import membership_import as finance_membership_import
from services.finance import records as finance_records
from services.finance import sheets_mirror as finance_sheets_mirror
from services.notifications import mailer as notify_mailer
from services.notifications import messages as notify_messages
from services.notifications import service as notify
from services import accounts
from services import exports


# ==================================================
# LOAD ENVIRONMENT VARIABLES
# ==================================================

load_dotenv()


# ==================================================
# CREATE APPLICATION
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_SITE_DIR = os.path.join(BASE_DIR, "public_site")
PUBLIC_TEMPLATE_DIR = os.path.join(PUBLIC_SITE_DIR, "templates")
PUBLIC_STATIC_DIR = os.path.join(PUBLIC_SITE_DIR, "static")
PRIVATE_STATIC_DIR = os.path.join(BASE_DIR, "templates", "static")

app = Flask(
    __name__,
    static_folder=PRIVATE_STATIC_DIR
)

app.jinja_loader = ChoiceLoader(
    [
        app.jinja_loader,
        PrefixLoader(
            {"public": FileSystemLoader(PUBLIC_TEMPLATE_DIR)},
            delimiter="/"
        ),
        FileSystemLoader(PUBLIC_TEMPLATE_DIR)
    ]
)


# ==================================================
# CONFIGURATION
# ==================================================

ON_VERCEL = bool(os.getenv("VERCEL"))

_secret_key = (os.getenv("SECRET_KEY") or "").strip()
if not _secret_key:
    if ON_VERCEL:
        # A known default key would let anyone forge login sessions.
        raise RuntimeError("SECRET_KEY must be set in the Vercel environment variables.")
    _secret_key = "development-secret-key"   # local development only
app.config["SECRET_KEY"] = _secret_key

# Session cookie: not readable by JavaScript, not sent on cross-site requests
# (first line of defence against CSRF), HTTPS-only when deployed.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = ON_VERCEL

def _database_url():
    """Supabase Postgres connection string (use the TRANSACTION POOLER one,
    port 6543). Required: the app refuses to start without it."""
    url = (os.getenv("SUPABASE_DB_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set. Add your Supabase pooler connection "
            "string to .env (and to the Vercel environment variables)."
        )
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


app.config["SQLALCHEMY_DATABASE_URI"] = _database_url()

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Vercel runs each request in a short-lived serverless function and Supabase's
# pooler already pools connections, so the app keeps no connection pool of its
# own (NullPool) and every request opens/closes a connection through the pooler.
_engine_options = {"poolclass": NullPool}
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
    _engine_options["connect_args"] = {"connect_timeout": 10}
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = _engine_options

# ==================================================
# PUBLIC WEBSITE
# ==================================================

@app.route("/public-static/<path:filename>", endpoint="public_static")
def public_static(filename):

    return send_from_directory(
        PUBLIC_STATIC_DIR,
        filename
    )


def _public_finance_summary():
    """Totals only (no names, payers, references or notes): safe to publish.

    Returns None if the database can't be reached, so public pages still load."""
    try:
        def total(model):
            return db.session.query(db.func.coalesce(db.func.sum(model.amount), 0)).scalar() or Decimal("0")

        fundraising_total = total(Fundraising)
        sponsorship_total = total(Sponsorship)
        fees_total = total(MembershipFee)
        expense_total = total(Expense)
        income_total = fundraising_total + sponsorship_total + fees_total

        by_income_type = [
            (label or "Other fundraising", amount)
            for label, amount in db.session.query(
                Fundraising.income_type, db.func.sum(Fundraising.amount)
            ).group_by(Fundraising.income_type).order_by(db.func.sum(Fundraising.amount).desc())
        ]
        by_category = [
            (label or "Uncategorized", amount)
            for label, amount in db.session.query(
                Expense.category, db.func.sum(Expense.amount)
            ).group_by(Expense.category).order_by(db.func.sum(Expense.amount).desc())
        ]
        monthly = exports.build("summary")[0].rows[-12:]
        dates = [d for (d,) in db.session.query(db.func.max(Fundraising.fundraising_date))] + \
                [d for (d,) in db.session.query(db.func.max(Sponsorship.sponsorship_date))] + \
                [d for (d,) in db.session.query(db.func.max(MembershipFee.payment_date))] + \
                [d for (d,) in db.session.query(db.func.max(Expense.expense_date))]
        latest = max((d for d in dates if d), default=None)
        return {
            "fundraising": fundraising_total,
            "sponsorships": sponsorship_total,
            "membership_fees": fees_total,
            "expenses": expense_total,
            "income": income_total,
            "balance": income_total - expense_total,
            "by_income_type": by_income_type,
            "by_category": by_category,
            "monthly": monthly,
            "latest": latest,
        }
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Public finance summary failed.")
        return None


@app.route("/")
def public_home():

    return render_template(
        "public/landing.html",
        finance=_public_finance_summary()
    )


@app.route("/introduction")
def public_introduction():

    return render_template(
        "public/introduction.html"
    )


@app.route("/advocacies")
def public_advocacies():

    return render_template(
        "public/advocacies.html"
    )


@app.route("/constitution")
def public_constitution():

    return render_template(
        "public/constitution.html"
    )


@app.route("/best-practices")
def public_best_practices():

    return render_template(
        "public/best_practices.html"
    )


@app.route("/roster")
def public_roster():

    return render_template(
        "public/roster.html"
    )


LOOKER_HOSTS = ("https://lookerstudio.google.com/", "https://datastudio.google.com/")


def _looker_report_urls():
    """(report_url, embed_url) from LOOKER_STUDIO_URL, or (None, None).

    Paste the report's normal share link into LOOKER_STUDIO_URL; the embed
    address is derived from it. Only Looker Studio addresses are accepted,
    so the page can never be made to frame another site."""
    url = (os.getenv("LOOKER_STUDIO_URL") or "").strip()
    if not url.startswith(LOOKER_HOSTS) or "/reporting/" not in url:
        return None, None
    if "/embed/reporting/" in url:
        return url.replace("/embed/reporting/", "/reporting/", 1), url
    return url, url.replace("/reporting/", "/embed/reporting/", 1)


@app.route("/financial-dashboard")
def public_financial_dashboard():

    report_url, embed_url = _looker_report_urls()
    return render_template(
        "public/financial_dashboard.html",
        looker_report_url=report_url,
        looker_embed_url=embed_url,
        finance=_public_finance_summary()
    )


@app.route("/events")
def public_events():

    return render_template(
        "public/events.html"
    )


@app.route(
    "/contact",
    methods=["GET", "POST"]
)
def public_contact():

    if request.method == "POST":

        name = request.form.get(
            "name"
        )

        email = request.form.get(
            "email"
        )

        subject = request.form.get(
            "subject"
        )

        message = request.form.get(
            "message"
        )

        # EMAIL FUNCTION WILL BE ADDED LATER

        flash(
            "Your message has been submitted successfully.",
            "success"
        )

        return redirect(
            url_for("public_contact")
        )

    return render_template(
        "public/contact.html"
    )
    return render_template("public/contact.html")


# ==================================================
# INITIALIZE
# ==================================================

db.init_app(app)

# The database schema is managed in Supabase (see kny_supabase/*.sql), NOT by
# the app. The old create_all() and the MySQL-only migrations no longer run.

login_manager = LoginManager()
login_manager.init_app(app)

login_manager.login_view = "login"


# ==================================================
# CSRF PROTECTION
#
# Every POST must carry the per-session token that only pages from this site
# can read (templates add it with {{ csrf_token() }}). A form submitted from
# another website cannot know the token, so it is refused.
# ==================================================

CSRF_SESSION_KEY = "_csrf_token"
CSRF_FIELD = "csrf_token"
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def csrf_token():
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


def _safe_back_url():
    """Where to send someone whose form was refused: the page they came
    from if it is on this site, otherwise a sensible default."""
    referrer = request.referrer or ""
    if referrer.startswith(request.host_url):
        return referrer
    return url_for("dashboard") if current_user.is_authenticated else url_for("login")


@app.before_request
def csrf_protect():
    if request.method in CSRF_SAFE_METHODS:
        return None
    expected = session.get(CSRF_SESSION_KEY)
    sent = request.form.get(CSRF_FIELD) or request.headers.get("X-CSRF-Token", "")
    if expected and sent and hmac.compare_digest(str(sent), str(expected)):
        return None
    app.logger.warning("CSRF check failed for %s %s", request.method, request.path)
    flash(
        "That form could not be submitted because it expired or did not come "
        "from this site. Please try again.",
        "danger"
    )
    return redirect(_safe_back_url(), code=303)


@app.context_processor
def portal_navigation_context():
    """Counts shown in the portal sidebar (one cheap query, admins only)."""
    pending = 0
    try:
        if current_user.is_authenticated and current_user.role == "admin":
            pending = ExportRequest.query.filter_by(status="pending").count()
    except SQLAlchemyError:
        db.session.rollback()
    return {"nav_pending_exports": pending}


# ==================================================
# USER LOADER
# ==================================================

@login_manager.user_loader
def load_user(user_id):

    # Old sessions held a numeric id from the MySQL days; those are not valid
    # UUIDs, so they simply count as "logged out" and the person signs in again.
    try:
        profile_id = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        return None

    profile = db.session.get(Profile, profile_id)

    # A deactivated account loses access on its very next request.
    if profile is None or profile.status != "active":
        return None

    return profile


def password_is_correct(profile, password):
    """Re-check a signed-in person's password with Supabase Auth.

    Raises supabase_auth.AuthError (safe message) if the login service is
    unavailable, so callers can tell that apart from a wrong password."""
    auth_user = supabase_auth.sign_in(profile.email, password)
    return auth_user is not None and auth_user["id"] == profile.id


# ==================================================
# ROLE DECORATORS
# ==================================================

def encoder_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        if current_user.role not in ["admin", "encoder"]:
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        if current_user.role != "admin":
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


# ==================================================
# LOGIN
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        # Supabase Auth checks the password. We never see or store a hash.
        try:
            auth_user = supabase_auth.sign_in(email, password)
        except supabase_auth.AuthError as error:
            flash(str(error), "danger")
            return redirect(url_for("login"))

        if auth_user is None:
            flash(
                "Invalid email or password.",
                "danger"
            )
            return redirect(url_for("login"))

        # The password is right; now find this login's profile (role/status).
        profile = db.session.get(Profile, auth_user["id"])

        if profile is None:
            flash(
                "Your account is not set up yet. Please contact an administrator.",
                "danger"
            )
            return redirect(url_for("login"))

        if profile.status != "active":
            flash(
                "Your account is inactive.",
                "danger"
            )
            return redirect(url_for("login"))

        login_user(profile)

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "login.html"
    )

# ==================================================
# DASHBOARD
# ==================================================

@app.route("/dashboard")
@login_required
def dashboard():
    """Overview: money at a glance, then what needs this person's attention."""
    def total(model):
        return db.session.query(db.func.coalesce(db.func.sum(model.amount), 0)).scalar() or Decimal("0")

    def total_since(model, date_col, start):
        return (db.session.query(db.func.coalesce(db.func.sum(model.amount), 0))
                .filter(date_col >= start).scalar() or Decimal("0"))

    now = datetime.now(timezone.utc)
    year_start = date(notify_messages.today_in_manila(now).year, 1, 1)
    income = total(Fundraising) + total(Sponsorship) + total(MembershipFee)
    spent = total(Expense)
    income_year = (total_since(Fundraising, Fundraising.fundraising_date, year_start)
                   + total_since(Sponsorship, Sponsorship.sponsorship_date, year_start)
                   + total_since(MembershipFee, MembershipFee.payment_date, year_start))
    spent_year = total_since(Expense, Expense.expense_date, year_start)

    upcoming = Event.query.filter(
        Event.status == "scheduled", Event.starts_at > now
    ).order_by(Event.starts_at).limit(4).all()

    role = current_user.role
    attention = []
    recent = []
    if role == "admin":
        pending = ExportRequest.query.filter_by(status="pending").count()
        if pending:
            attention.append({"icon": "inbox", "tone": "warn",
                              "text": f"{pending} export request{'s' if pending != 1 else ''} waiting for your decision",
                              "action": "Review", "url": url_for("manage_export_requests")})
        if not notify_mailer.is_configured():
            attention.append({"icon": "mail", "tone": "warn",
                              "text": "Email isn't connected, so reminders and notices can't be sent",
                              "action": "Set up", "url": url_for("notifications") + "#setup"})
        _, missing = notify.reachable(notify.active_members())
        if missing:
            attention.append({"icon": "users", "tone": "info",
                              "text": f"{len(missing)} active member{'s have' if len(missing) != 1 else ' has'} no email and won't get reminders",
                              "action": "Add emails", "url": url_for("manage_members")})
        if not upcoming:
            attention.append({"icon": "calendar", "tone": "info",
                              "text": "No meetings or events are scheduled",
                              "action": "Schedule one", "url": url_for("manage_events")})
        recent = AuditLog.query.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(6).all()

    return render_template(
        "dashboard.html",
        user=current_user,
        first_name=(current_user.member.first_name.split(" ")[0]
                    if current_user.member and current_user.member.first_name else ""),
        income=income, spent=spent, balance=income - spent,
        income_year=income_year, spent_year=spent_year, year=year_start.year,
        upcoming=upcoming,
        attention=attention,
        recent=recent,
        audit_actions=AUDIT_ACTION_LABELS,
        audit_entities=AUDIT_ENTITY_LABELS,
        sheets_enabled=finance_sheets_mirror.is_enabled() and role in ("admin", "encoder"),
        local=notify_messages.local,
        when_text=notify_messages.when_text,
    )


# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(
        url_for("login")
    )


# ==================================================
# FORGOT PASSWORD
# ==================================================

@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():

    if current_user.is_authenticated:
        return redirect(url_for("change_password"))

    if request.method == "POST":
        email = request.form.get("email", "")
        try:
            status = accounts.request_reset(email, _client_ip(), _reset_link)
        except Exception:   # never reveal anything about the account
            db.session.rollback()
            app.logger.exception("Password reset request failed.")
            status = "failed"
        if status in {"failed", "limited"}:
            app.logger.warning("Password reset request not sent (%s).", status)

        # Same answer whatever happened, so nobody can test which emails exist.
        flash(
            "If that email belongs to an active account, we've sent a link to reset "
            "the password. It works for 30 minutes. Check your Spam folder too, and "
            "if nothing arrives, contact an administrator.",
            "success"
        )
        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.remote_addr) or ""


def _reset_link(token):
    base = (os.getenv("SITE_URL") or "").strip().rstrip("/")
    path = url_for("reset_password_with_link", token=token)
    return f"{base}{path}" if base else url_for("reset_password_with_link", token=token, _external=True)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password_with_link(token):

    if request.method == "POST":
        ok, message = accounts.complete_reset(
            token,
            request.form.get("password", ""),
            request.form.get("confirm_password", ""),
        )
        if ok:
            if current_user.is_authenticated:
                logout_user()
            flash(message, "success")
            return redirect(url_for("login"))
        flash(message, "danger")
        if message == accounts.INVALID_LINK:
            return redirect(url_for("forgot_password"))
        return redirect(url_for("reset_password_with_link", token=token))

    row, profile = accounts.check_token(token)
    if row is None:
        flash(accounts.INVALID_LINK, "danger")
        return redirect(url_for("forgot_password"))

    response = app.make_response(render_template("reset_password.html", email=profile.email))
    # The link is a secret: never cache this page or leak it to other sites.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ==================================================
# CHANGE PASSWORD
# ==================================================

@app.route(
    "/change-password",
    methods=["GET", "POST"]
)
@login_required
def change_password():

    if request.method == "POST":

        current_password = request.form.get(
            "current_password",
            ""
        )

        new_password = request.form.get(
            "new_password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        # ------------------------------------------
        # CHECK CURRENT PASSWORD
        # ------------------------------------------

        try:
            password_correct = password_is_correct(
                current_user,
                current_password
            )
        except supabase_auth.AuthError as error:
            flash(str(error), "danger")
            return redirect(
                url_for("change_password")
            )

        if not password_correct:

            flash(
                "Current password is incorrect.",
                "danger"
            )

            return redirect(
                url_for("change_password")
            )

        # ------------------------------------------
        # CHECK NEW PASSWORD LENGTH
        # ------------------------------------------

        if len(new_password) < 8:

            flash(
                "New password must be at least 8 characters.",
                "danger"
            )

            return redirect(
                url_for("change_password")
            )

        # ------------------------------------------
        # CONFIRM PASSWORD
        # ------------------------------------------

        if new_password != confirm_password:

            flash(
                "New passwords do not match.",
                "danger"
            )

            return redirect(
                url_for("change_password")
            )

        # ------------------------------------------
        # SAVE NEW PASSWORD IN SUPABASE AUTH
        # ------------------------------------------

        try:
            supabase_auth.update_user(
                current_user.id,
                password=new_password
            )
        except supabase_auth.AuthError as error:
            flash(str(error), "danger")
            return redirect(
                url_for("change_password")
            )

        accounts.notify_password_changed(current_user, "from your account's Change Password page")

        flash(
            "Password changed successfully.",
            "success"
        )

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "change_password.html"
    )

# ==================================================
# USER MANAGEMENT: MEMBERS (the roster) AND PORTAL ACCOUNTS (logins)
#
# Members are everyone in the organization; an account is a login for a
# member, with a system role. Every change is written to the audit log.
# ==================================================

SYSTEM_ROLES = {
    "admin": "Admin",
    "encoder": "Encoder",
    "viewer": "Viewer",
}
SYSTEM_ROLE_HELP = {
    "admin": "Everything: finances, members, accounts, notifications, audit log.",
    "encoder": "Adds and edits financial records.",
    "viewer": "Can log in and view the dashboard and public transparency page.",
}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _member_email(raw):
    """(clean email or None, error message or "")."""
    email = (raw or "").strip().lower()
    if not email:
        return None, ""
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        return None, "Enter a valid email address (or leave it blank)."
    return email, ""


def _member_email_taken(email, exclude_id=None):
    query = Member.query.filter(db.func.lower(Member.email) == email)
    if exclude_id is not None:
        query = query.filter(Member.id != exclude_id)
    return query.first() is not None


def _member_snapshot(member):
    return {
        "membership_id": member.membership_id, "first_name": member.first_name,
        "middle_name": member.middle_name or "", "last_name": member.last_name,
        "org_role": member.org_role, "email": member.email or "", "status": member.status,
    }


def _account_snapshot(profile):
    return {
        "email": profile.email, "membership_id": profile.membership_id,
        "role": profile.role, "status": profile.status,
    }


def _audit_and_commit(action, entity, record_id, summary, before=None, after=None):
    finance_records.audit(action, entity, actor=current_user, record_id=record_id,
                          summary=summary, before=before, after=after)
    db.session.commit()


def _other_active_admins(profile_id):
    return Profile.query.filter(
        Profile.role == "admin", Profile.status == "active", Profile.id != profile_id
    ).count()


def _account_link(token):
    return _reset_link(token)


# ------------------------------ members ------------------------------

@app.route("/admin/members")
@login_required
@admin_required
def manage_members():
    members = Member.query.order_by(Member.last_name, Member.first_name).all()
    rows = []
    for member in members:
        accounts_for = [a for a in member.users or []]
        account = next((a for a in accounts_for if a.status == "active"), None) or (accounts_for[0] if accounts_for else None)
        rows.append({
            "member": member,
            "account": account,
            "notify_email": member.notify_email,
            "values": _member_snapshot(member),
        })
    active = [r for r in rows if r["member"].status == "active"]
    org_roles = sorted({m.org_role for m in members if m.org_role} | {"Member"})
    return render_template(
        "manage_members.html",
        rows=rows,
        org_roles=org_roles,
        stats={
            "active": len(active),
            "with_email": sum(1 for r in active if r["notify_email"]),
            "with_login": sum(1 for r in active if r["account"] is not None),
            "inactive": len(rows) - len(active),
        },
        focus=request.args.get("q", "").strip(),
    )


def _member_form(form):
    values = {
        "membership_id": (form.get("membership_id") or "").strip(),
        "first_name": (form.get("first_name") or "").strip(),
        "middle_name": (form.get("middle_name") or "").strip() or None,
        "last_name": (form.get("last_name") or "").strip(),
        "org_role": (form.get("org_role") or "Member").strip() or "Member",
        "status": form.get("status") or "active",
    }
    email, email_error = _member_email(form.get("email"))
    values["email"] = email
    if not all((values["membership_id"], values["first_name"], values["last_name"])):
        return values, "Membership ID, first name and last name are required."
    if email_error:
        return values, email_error
    if values["status"] not in {"active", "inactive"}:
        return values, "Choose a valid member status."
    return values, ""


@app.route("/admin/members/add", methods=["POST"])
@login_required
@admin_required
def add_member():
    values, error = _member_form(request.form)
    if not error and Member.query.filter_by(membership_id=values["membership_id"]).first():
        error = "That Membership ID is already in use."
    if not error and values["email"] and _member_email_taken(values["email"]):
        error = "Another member already uses that email."
    if error:
        flash(error, "danger")
        return redirect(url_for("manage_members"))
    member = Member(**values)
    db.session.add(member)
    db.session.flush()
    _audit_and_commit("create", "members", member.membership_id,
                      f"Added member {member.full_name} ({member.membership_id})",
                      after=_member_snapshot(member))
    flash(f"{member.full_name} added.", "success")
    return redirect(url_for("manage_members"))


@app.route("/admin/members/<int:member_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_member(member_id):
    member = db.get_or_404(Member, member_id)
    values, error = _member_form(request.form)
    if not error:
        duplicate = Member.query.filter(
            Member.membership_id == values["membership_id"], Member.id != member.id
        ).first()
        if duplicate:
            error = "That Membership ID is already in use."
    if not error and values["email"] and _member_email_taken(values["email"], exclude_id=member.id):
        error = "Another member already uses that email."
    if error:
        flash(error, "danger")
        return redirect(url_for("manage_members"))

    before = _member_snapshot(member)
    if values["membership_id"] != member.membership_id:
        for account in member.users:
            account.membership_id = values["membership_id"]
        for fee in member.membership_fees:
            fee.membership_id = values["membership_id"]
    for key, value in values.items():
        setattr(member, key, value)
    after = _member_snapshot(member)
    if after != before:
        _audit_and_commit("update", "members", member.membership_id,
                          f"Edited member {member.full_name} ({member.membership_id})",
                          before=before, after=after)
    flash("Member saved.", "success")
    return redirect(url_for("manage_members"))


# ------------------------------ accounts ------------------------------

@app.route("/admin/users")
@login_required
@admin_required
def manage_users():
    accounts_list = Profile.query.order_by(Profile.created_at.desc()).all()
    members_without_login = [
        m for m in Member.query.filter_by(status="active").order_by(Member.last_name, Member.first_name)
        if not any(a.status == "active" for a in m.users or [])
    ]
    counts = {role: 0 for role in SYSTEM_ROLES}
    for account in accounts_list:
        if account.status == "active" and account.role in counts:
            counts[account.role] += 1
    return render_template(
        "manage_users.html",
        accounts=accounts_list,
        members=members_without_login,
        roles=SYSTEM_ROLES,
        role_help=SYSTEM_ROLE_HELP,
        counts=counts,
        inactive=sum(1 for a in accounts_list if a.status != "active"),
        email_ready=notify_mailer.is_configured(),
        local=notify_messages.local,
    )


@app.route("/admin/users/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_user():
    if request.method == "GET":
        return redirect(url_for("manage_users"))

    membership_id = request.form.get("membership_id", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "")
    mode = request.form.get("password_mode", "invite")
    password = request.form.get("password", "")

    member = Member.query.filter_by(membership_id=membership_id).first()
    error = ""
    if not member or member.status != "active":
        error = "Choose an active member for this account."
    elif not email or not EMAIL_PATTERN.match(email):
        error = "Enter a valid login email."
    elif role not in SYSTEM_ROLES:
        error = "Choose a valid system role."
    elif mode not in {"invite", "set"}:
        error = "Choose how the person gets their password."
    elif mode == "set" and len(password) < 8:
        error = "The password must be at least 8 characters."
    elif mode == "invite" and not notify_mailer.is_configured():
        error = "Email isn't connected, so an invitation can't be sent. Choose “Set a password now” instead."
    elif Profile.query.filter(db.func.lower(Profile.email) == email).first():
        error = "An account with that email already exists."
    if error:
        flash(error, "danger")
        return redirect(url_for("manage_users"))

    # 1) the login in Supabase Auth (an unknown random password for invitations)
    try:
        auth_id = supabase_auth.create_user(
            email, password if mode == "set" else accounts.random_password())
    except supabase_auth.AuthError as auth_error:
        flash(str(auth_error), "danger")
        return redirect(url_for("manage_users"))

    # 2) the profile (role, status, member)
    try:
        profile = Profile(id=auth_id, membership_id=membership_id, email=email,
                          role=role, status="active")
        db.session.add(profile)
        if not member.email and not _member_email_taken(email):
            member.email = email      # notifications go to the member's email
        db.session.flush()
        finance_records.audit("create", "account", actor=current_user, record_id=profile.id,
                              summary=f"Created {SYSTEM_ROLES[role]} account for {member.full_name} ({email})",
                              after=_account_snapshot(profile))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Could not save the profile for a new login.")
        supabase_auth.delete_user(auth_id)      # no login without a profile
        flash("The account could not be saved. Nothing was created.", "danger")
        return redirect(url_for("manage_users"))

    if mode == "invite":
        status = accounts.send_invite(profile, _account_link, current_user.email, SYSTEM_ROLES[role])
        if status == "sent":
            flash(f"Account created. {member.full_name} was emailed a link to set their password (valid 3 days).", "success")
        else:
            flash("Account created, but the invitation email could not be sent. "
                  "Use “Send reset link” to try again.", "warning")
    else:
        flash(f"Account created for {member.full_name}. Give them the password privately; "
              "they can change it after logging in.", "success")
    return redirect(url_for("manage_users"))


@app.route("/admin/users/<uuid:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = db.get_or_404(Profile, user_id)
    if request.method == "GET":
        return redirect(url_for("manage_users"))

    membership_id = request.form.get("membership_id", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "")
    status = request.form.get("status", "active")

    error = ""
    if not Member.query.filter_by(membership_id=membership_id).first():
        error = "Choose an existing member."
    elif not email or not EMAIL_PATTERN.match(email):
        error = "Enter a valid login email."
    elif role not in SYSTEM_ROLES or status not in {"active", "inactive"}:
        error = "Choose a valid role and status."
    elif Profile.query.filter(db.func.lower(Profile.email) == email, Profile.id != user.id).first():
        error = "An account with that email already exists."
    elif user.id == current_user.id and (role != "admin" or status != "active"):
        error = "You can't remove your own admin access. Ask another admin to do it."
    elif (user.role == "admin" and user.status == "active"
          and (role != "admin" or status != "active") and _other_active_admins(user.id) == 0):
        error = "This is the only active admin. Make someone else an admin first."
    if error:
        flash(error, "danger")
        return redirect(url_for("manage_users"))

    before = _account_snapshot(user)
    email_changed = email != (user.email or "").lower()
    user.membership_id = membership_id
    user.email = email
    user.role = role
    user.status = status
    try:
        db.session.flush()
        if email_changed:
            supabase_auth.update_user(user.id, email=email)
        after = _account_snapshot(user)
        if after != before:
            finance_records.audit("update", "account", actor=current_user, record_id=user.id,
                                  summary=f"Edited account {email}", before=before, after=after)
        db.session.commit()
    except supabase_auth.AuthError as auth_error:
        db.session.rollback()
        flash(str(auth_error), "danger")
        return redirect(url_for("manage_users"))
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Could not update a user profile.")
        flash("The changes could not be saved.", "danger")
        return redirect(url_for("manage_users"))

    flash("Account saved.", "success")
    return redirect(url_for("manage_users"))


@app.route("/admin/users/<uuid:user_id>/toggle-status", methods=["POST"])
@login_required
@admin_required
def toggle_user_status(user_id):
    user = db.get_or_404(Profile, user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("manage_users"))
    if user.status == "active" and user.role == "admin" and _other_active_admins(user.id) == 0:
        flash("This is the only active admin. Make someone else an admin first.", "danger")
        return redirect(url_for("manage_users"))
    before = _account_snapshot(user)
    user.status = "inactive" if user.status == "active" else "active"
    verb = "Deactivated" if user.status == "inactive" else "Reactivated"
    _audit_and_commit("update", "account", user.id, f"{verb} account {user.email}",
                      before=before, after=_account_snapshot(user))
    flash(f"{verb} {user.email}." + (" They can no longer log in." if user.status == "inactive" else ""), "success")
    return redirect(url_for("manage_users"))


@app.route("/admin/users/<uuid:user_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def reset_password(user_id):
    user = db.get_or_404(Profile, user_id)
    new_password = request.form.get("new_password", "")
    if len(new_password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("manage_users"))
    try:
        supabase_auth.update_user(user.id, password=new_password)
    except supabase_auth.AuthError as auth_error:
        flash(str(auth_error), "danger")
        return redirect(url_for("manage_users"))
    _audit_and_commit("password_set", "account", user.id, f"Set a new password for {user.email}")
    accounts.notify_password_changed(user, "by an administrator")
    flash(f"New password set for {user.email}. Give it to them privately.", "success")
    return redirect(url_for("manage_users"))


@app.route("/admin/users/<uuid:user_id>/send-reset", methods=["POST"])
@login_required
@admin_required
def send_reset_link_admin(user_id):
    user = db.get_or_404(Profile, user_id)
    status = accounts.send_reset_link(user, _account_link, current_user.email)
    if status == "sent":
        _audit_and_commit("reset_link", "account", user.id, f"Emailed a password reset link to {user.email}")
        flash(f"Reset link emailed to {user.email}. It works once, for 30 minutes.", "success")
    elif status == "inactive":
        flash("That account is inactive. Reactivate it first.", "danger")
    elif status == "not_configured":
        flash("Email isn't connected yet, so no link was sent.", "danger")
    else:
        flash("The email could not be sent. Please try again in a few minutes.", "danger")
    return redirect(url_for("manage_users"))


# ==================================================
# NOTIFICATIONS: MEETINGS & EVENTS, DUES REMINDERS, WARNINGS
#
# Emails go to each active member's email (or their login email). Sending
# and logging live in services/notifications/. Big batches are sent in
# rounds; a "Continue sending" banner re-posts the same batch, and the log's
# unique keys guarantee nobody receives the same email twice.
# ==================================================

EVENT_KINDS = {"meeting": "Meeting", "event": "Event"}


class _Form(dict):
    """Lets a plain dict stand in for request.form when remembering a batch."""
    def items(self, multi=False):
        return list(super().items())


def _actor_label():
    return getattr(current_user, "email", None) or "admin"


def _form_items(form, skip=("csrf_token",)):
    return [(k, v) for k, v in form.items(multi=True) if k not in skip]


def _flash_batch(result, what, endpoint_url=None, form=None):
    """Flash the outcome of a send, and remember unfinished batches."""
    if result.error and not result.attempted:
        flash(result.error, "danger")
    elif result.attempted or result.already:
        category = "success" if not (result.failed or result.remaining or result.error) else "warning"
        flash(f"{what}: {result.summary()}.", category)
        for name, error in result.failures[:5]:
            flash(f"Not delivered to {name}: {error}", "danger")
        if result.error:
            flash(result.error, "danger")
    if result.remaining and endpoint_url and form is not None and not (result.error and not result.attempted):
        session["notify_pending"] = {
            "url": endpoint_url, "label": what,
            "remaining": result.remaining, "fields": _form_items(form),
        }
    else:
        session.pop("notify_pending", None)


def _audit_send(summary, record_id=None):
    finance_records.audit("email", "notification", actor=current_user,
                          record_id=record_id, summary=summary)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()


def _event_from_form(form):
    """(values dict, error) for the add/edit event forms."""
    title = (form.get("title") or "").strip()
    kind = form.get("kind") or "meeting"
    day = (form.get("date") or "").strip()
    clock = (form.get("time") or "").strip()
    if not title:
        return None, "Give the meeting or event a title."
    if kind not in EVENT_KINDS:
        return None, "Choose Meeting or Event."
    try:
        local_dt = datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None, "Enter a valid date and start time."
    starts_at = local_dt.replace(tzinfo=notify_messages.MANILA).astimezone(timezone.utc)
    return {
        "title": title[:200],
        "kind": kind,
        "starts_at": starts_at,
        "location": (form.get("location") or "").strip()[:255] or None,
        "description": (form.get("description") or "").strip() or None,
    }, ""


def _event_snapshot(event):
    return {
        "title": event.title, "kind": event.kind,
        "starts_at": notify_messages.when_text(event.starts_at),
        "location": event.location or "", "description": event.description or "",
        "status": event.status,
    }


@app.route("/admin/events")
@login_required
@admin_required
def manage_events():
    now = datetime.now(timezone.utc)
    events = Event.query.order_by(Event.starts_at).all()
    upcoming = [e for e in events
                if e.status == "scheduled" and notify_messages.as_utc(e.starts_at) > now]
    past = sorted((e for e in events if e not in upcoming),
                  key=lambda e: notify_messages.as_utc(e.starts_at), reverse=True)[:50]
    sent_counts = dict(
        db.session.query(NotificationLog.event_id, db.func.count(NotificationLog.id))
        .filter(NotificationLog.status == "sent", NotificationLog.event_id.isnot(None))
        .group_by(NotificationLog.event_id).all()
    )
    reachable, missing = notify.reachable(notify.active_members())
    return render_template(
        "events.html",
        upcoming=upcoming,
        past=past,
        sent_counts=sent_counts,
        next_note={e.id: notify.next_reminder_text(e, now) for e in upcoming},
        local=notify_messages.local,
        when_text=notify_messages.when_text,
        kinds=EVENT_KINDS,
        reachable_count=len(reachable),
        missing_count=len(missing),
        email_ready=notify_mailer.is_configured(),
        batch_id=notify.new_batch_id(),
        pending=session.get("notify_pending"),
    )


def _announce(event, batch_id, builder, kind, what):
    items, _ = notify.event_outgoing(event, builder)
    result = notify.send_batch(
        kind, items, sent_by=_actor_label(), batch_id=batch_id,
        dedupe_prefix=f"batch:{batch_id}", event_id=event.id,
    )
    if result.attempted:
        _audit_send(f"{what} for “{event.title}”: {result.summary()}", record_id=event.id)
    return result


@app.route("/admin/events/add", methods=["POST"])
@login_required
@admin_required
def add_event():
    values, error = _event_from_form(request.form)
    if error:
        flash(error, "danger")
        return redirect(url_for("manage_events"))
    event = Event(status="scheduled", created_by=_actor_label(), **values)
    db.session.add(event)
    db.session.flush()
    finance_records.audit("create", "event", actor=current_user, record_id=event.id,
                          summary=f"Scheduled {event.kind} “{event.title}”",
                          after=_event_snapshot(event))
    db.session.commit()
    flash(f"“{event.title}” scheduled. Members get automatic email reminders 3 days and 1 day before.", "success")
    if request.form.get("announce"):
        batch_id = request.form.get("batch_id") or notify.new_batch_id()
        result = _announce(event, batch_id, notify_messages.event_announcement,
                           "event_announcement", "Announcement")
        _flash_batch(result, "Announcement emails",
                     url_for("email_event", event_id=event.id),
                     _Form({"mode": "announce", "batch_id": batch_id}))
    return redirect(url_for("manage_events"))


@app.route("/admin/events/<int:event_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_event(event_id):
    event = db.get_or_404(Event, event_id)
    values, error = _event_from_form(request.form)
    if error:
        flash(error, "danger")
        return redirect(url_for("manage_events"))
    before = _event_snapshot(event)
    for key, value in values.items():
        setattr(event, key, value)
    finance_records.audit("update", "event", actor=current_user, record_id=event.id,
                          summary=f"Edited {event.kind} “{event.title}”",
                          before=before, after=_event_snapshot(event))
    db.session.commit()
    flash("Changes saved. Use “Email members” if they should know about the change.", "success")
    return redirect(url_for("manage_events"))


@app.route("/admin/events/<int:event_id>/email", methods=["POST"])
@login_required
@admin_required
def email_event(event_id):
    event = db.get_or_404(Event, event_id)
    if event.status != "scheduled":
        flash("This meeting/event was cancelled.", "danger")
        return redirect(url_for("manage_events"))
    batch_id = request.form.get("batch_id") or notify.new_batch_id()
    if request.form.get("mode") == "reminder":
        today = notify_messages.today_in_manila(datetime.now(timezone.utc))
        result = _announce(
            event, batch_id,
            lambda e, name: notify_messages.event_reminder(e, name, today),
            "event_reminder", "Reminder")
        what = "Reminder emails"
    else:
        result = _announce(event, batch_id, notify_messages.event_announcement,
                           "event_announcement", "Announcement")
        what = "Announcement emails"
    _flash_batch(result, what, url_for("email_event", event_id=event.id), request.form)
    return redirect(url_for("manage_events"))


@app.route("/admin/events/<int:event_id>/cancel", methods=["POST"])
@login_required
@admin_required
def cancel_event(event_id):
    event = db.get_or_404(Event, event_id)
    if event.status != "cancelled":
        before = _event_snapshot(event)
        event.status = "cancelled"
        finance_records.audit("cancel", "event", actor=current_user, record_id=event.id,
                              summary=f"Cancelled {event.kind} “{event.title}”",
                              before=before, after=_event_snapshot(event))
        db.session.commit()
        flash(f"“{event.title}” cancelled. No more reminders will be sent.", "success")
    if request.form.get("notify"):
        batch_id = request.form.get("batch_id") or notify.new_batch_id()
        items, _ = notify.event_outgoing(event, notify_messages.event_cancelled)
        result = notify.send_batch(
            "event_cancelled", items, sent_by=_actor_label(), batch_id=batch_id,
            dedupe_prefix=f"batch:{batch_id}", event_id=event.id,
        )
        if result.attempted:
            _audit_send(f"Cancellation notice for “{event.title}”: {result.summary()}", record_id=event.id)
        _flash_batch(result, "Cancellation emails", url_for("cancel_event", event_id=event.id), request.form)
    return redirect(url_for("manage_events"))


@app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_event(event_id):
    event = db.get_or_404(Event, event_id)
    finance_records.audit("delete", "event", actor=current_user, record_id=event.id,
                          summary=f"Deleted {event.kind} “{event.title}”",
                          before=_event_snapshot(event))
    db.session.delete(event)
    db.session.commit()
    flash("Deleted. Emails already sent stay in the email history.", "success")
    return redirect(url_for("manage_events"))


NOTIFY_HISTORY_SIZE = 500


@app.route("/admin/notifications")
@login_required
@admin_required
def notifications():
    entries = NotificationLog.query.order_by(
        NotificationLog.created_at.desc(), NotificationLog.id.desc()
    ).limit(NOTIFY_HISTORY_SIZE).all()
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    sent_today = NotificationLog.query.filter(
        NotificationLog.status == "sent", NotificationLog.created_at >= since
    ).count()
    reachable, missing = notify.reachable(notify.active_members())
    return render_template(
        "notifications.html",
        entries=entries,
        total=NotificationLog.query.count(),
        page_size=NOTIFY_HISTORY_SIZE,
        kind_labels=notify.KIND_LABELS,
        local=notify_messages.local,
        email_ready=notify_mailer.is_configured(),
        sender=notify_mailer.sender_address(),
        sent_today=sent_today,
        reachable_count=len(reachable),
        missing=missing,
        pending=session.get("notify_pending"),
    )


@app.route("/admin/notifications/test", methods=["POST"])
@login_required
@admin_required
def send_test_email():
    member = current_user.member
    name = notify.first_name(member) if member else "there"
    subject, body = notify_messages.test_email(name)
    item = notify.Outgoing(member=None, email=current_user.email, subject=subject,
                           body=body, name=member.full_name if member else current_user.email)
    result = notify.send_batch("test", [item], sent_by=_actor_label())
    if result.sent:
        flash(f"Test email sent to {current_user.email}. Check your inbox (and Spam).", "success")
    else:
        _flash_batch(result, "Test email")
    return redirect(url_for("notifications"))


@app.route("/admin/notifications/dues", methods=["GET", "POST"])
@login_required
@admin_required
def dues_reminders():
    default_year, default_quarter = notify.current_quarter()
    source = request.form if request.method == "POST" else request.args
    try:
        year = int(source.get("year") or default_year)
    except ValueError:
        year = default_year
    quarter = source.get("quarter") or default_quarter
    if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
        quarter = default_quarter

    rows, recorded = notify.dues_rows(year, quarter)

    if request.method == "POST":
        chosen = set(request.form.getlist("membership_id"))
        note = (request.form.get("note") or "").strip()[:2000]
        batch_id = request.form.get("batch_id") or notify.new_batch_id()
        items = []
        for row in rows:
            if row.member.membership_id in chosen and row.email and row.state != "paid":
                subject, body = notify_messages.dues_reminder(
                    notify.first_name(row.member), year, quarter, row.state, row.balance, note)
                items.append(notify.Outgoing(member=row.member, email=row.email,
                                             subject=subject, body=body))
        if not items:
            flash("Tick at least one member who has an email and hasn't fully paid.", "danger")
            return redirect(url_for("dues_reminders", year=year, quarter=quarter))
        result = notify.send_batch("dues_reminder", items, sent_by=_actor_label(),
                                   batch_id=batch_id, dedupe_prefix=f"batch:{batch_id}")
        if result.attempted:
            _audit_send(f"Dues reminders for {quarter} {year}: {result.summary()}")
        _flash_batch(result, f"{quarter} {year} dues reminders",
                     url_for("dues_reminders"), request.form)
        return redirect(url_for("dues_reminders", year=year, quarter=quarter))

    sample_row = next((r for r in rows if r.suggested), None) or (rows[0] if rows else None)
    sample = None
    if sample_row:
        sample = notify_messages.dues_reminder(
            notify.first_name(sample_row.member), year, quarter,
            sample_row.state if sample_row.state in {"partial", "unpaid"} else "none",
            sample_row.balance)
    return render_template(
        "dues_reminders.html",
        rows=rows,
        recorded=recorded,
        year=year,
        quarter=quarter,
        years=list(range(default_year - 2, default_year + 2)),
        sample=sample,
        email_ready=notify_mailer.is_configured(),
        batch_id=notify.new_batch_id(),
        pending=session.get("notify_pending"),
    )


@app.route("/admin/notifications/warning", methods=["GET", "POST"])
@login_required
@admin_required
def send_warning():
    members = notify.active_members()
    if request.method == "POST":
        chosen = set(request.form.getlist("membership_id"))
        category = request.form.get("category", "other")
        message = (request.form.get("message") or "").strip()
        batch_id = request.form.get("batch_id") or notify.new_batch_id()
        if category not in notify_messages.WARNING_CATEGORIES:
            category = "other"
        if not chosen:
            flash("Choose at least one member.", "danger")
            return redirect(url_for("send_warning"))
        if len(message) < 10:
            flash("Write the message to send (at least a sentence).", "danger")
            return redirect(url_for("send_warning"))
        items, skipped = [], []
        for member in members:
            if member.membership_id not in chosen:
                continue
            if not member.notify_email:
                skipped.append(member.full_name)
                continue
            subject, body = notify_messages.warning(notify.first_name(member), category, message[:5000])
            items.append(notify.Outgoing(member=member, email=member.notify_email,
                                         subject=subject, body=body))
        if skipped:
            flash("No email on file for: " + ", ".join(skipped) + ". Add it on the Members page.", "warning")
        result = notify.send_batch("warning", items, sent_by=_actor_label(),
                                   batch_id=batch_id, dedupe_prefix=f"batch:{batch_id}")
        if result.attempted:
            label = notify_messages.WARNING_CATEGORIES[category]
            _audit_send(f"Warning ({label}): {result.summary()}")
        _flash_batch(result, "Warning emails", url_for("send_warning"), request.form)
        return redirect(url_for("send_warning"))

    return render_template(
        "send_warning.html",
        members=members,
        categories=notify_messages.WARNING_CATEGORIES,
        email_ready=notify_mailer.is_configured(),
        batch_id=notify.new_batch_id(),
        pending=session.get("notify_pending"),
    )


@app.route("/admin/notifications/pending/dismiss", methods=["POST"])
@login_required
@admin_required
def dismiss_pending_batch():
    session.pop("notify_pending", None)
    return redirect(_safe_back_url())


# ==================================================
# FINANCIAL MANAGEMENT
# ==================================================

@app.route("/financial-management")
@login_required
def financial_management():

    fundraising = Fundraising.query.order_by(
        Fundraising.fundraising_date.desc()
    ).all()

    sponsorships = Sponsorship.query.order_by(
        Sponsorship.sponsorship_date.desc()
    ).all()

    membership_fees = MembershipFee.query.order_by(
        MembershipFee.payment_date.desc()
    ).all()

    expenses = Expense.query.order_by(
        Expense.expense_date.desc()
    ).all()
    return render_template(
        "financial_management.html",
        fundraising=fundraising,
        sponsorships=sponsorships,
        membership_fees=membership_fees,
        expenses=expenses,
        user=current_user,
        sheets_mirror_enabled=finance_sheets_mirror.is_enabled(),
        sheets_robot_email=(
            google_sheets.service_account_email()
            if current_user.role == "admin" else ""
        )
    )


# ==================================================
# FINANCIAL RECORDS
# (fundraising, sponsorships, membership fees, expenses)
#
# These routes stay thin. Cleaning, validation, duplicate detection, saving
# and the Google Sheet mirror all live in services/finance/, so the web form,
# CSV import and Excel import follow exactly the same rules.
# ==================================================

# ledger key -> endpoint of its management page
LEDGER_PAGES = {
    "fundraising": "fundraising",
    "sponsorships": "sponsorships",
    "membership_fees": "membership_fees",
    "expenses": "expenses",
}


def _back_to_ledger(ledger_key):
    return redirect(url_for(LEDGER_PAGES[ledger_key]))


def _flash_outcome(outcome, success_message):
    if outcome.ok:
        flash(success_message, "success")
    for error in outcome.errors:
        flash(error, "danger")
    if outcome.mirror_warning:
        flash(outcome.mirror_warning, "warning")


# What each ledger page shows. Table columns: (field, heading, format).
# Form fields: name, label, input type, plus options. Fields not listed in
# "columns" (payer, notes, ...) are still editable in the Edit form.
_METHOD = {"name": "payment_method", "label": "Payment method", "type": "text",
           "list": ["Cash", "GCash", "Maya", "Bank Transfer", "MariBank", "BPI", "Landbank", "GoTyme Bank"]}
_REFERENCE = {"name": "reference_no", "label": "Reference / O.R. no.", "type": "text"}
_NOTES = {"name": "notes", "label": "Notes", "type": "textarea", "full": True}
_AMOUNT = {"name": "amount", "label": "Amount (₱)", "type": "money", "required": True}

LEDGER_UI = {
    "fundraising": {
        "description": "Money raised through donations, registration fees and other fundraising activities.",
        "endpoints": ("add_fundraising", "edit_fundraising", "delete_fundraising"),
        "columns": [("fundraising_date", "Date", "date"), ("activity", "Activity", ""),
                    ("income_type", "Type", ""), ("payment_method", "Method", ""),
                    ("amount", "Amount", "money")],
        "fields": [
            {"name": "fundraising_date", "label": "Date", "type": "date", "required": True},
            _AMOUNT,
            {"name": "activity", "label": "Activity / event", "type": "text", "full": True},
            {"name": "income_type", "label": "Income type", "type": "text",
             "list": ["Donation", "Registration Fee", "Sponsorship", "Event Proceeds"]},
            _METHOD, _REFERENCE,
            {"name": "payer", "label": "Account no. / name (private)", "type": "text", "full": True,
             "hint": "Never shown on the public dashboard."},
            _NOTES,
        ],
    },
    "sponsorships": {
        "description": "Contributions from individuals, businesses and organizations.",
        "endpoints": ("add_sponsorship", "edit_sponsorship", "delete_sponsorship"),
        "columns": [("sponsorship_date", "Date", "date"), ("sponsor_name", "Sponsor", ""),
                    ("sponsor_type", "Type", ""), ("activity", "Purpose", ""),
                    ("amount", "Amount", "money")],
        "fields": [
            {"name": "sponsorship_date", "label": "Date", "type": "date", "required": True},
            _AMOUNT,
            {"name": "sponsor_name", "label": "Sponsor", "type": "text", "required": True, "full": True},
            {"name": "sponsor_type", "label": "Sponsor type", "type": "select",
             "options": ["", "Individual", "Business", "Organization", "Government"]},
            {"name": "activity", "label": "Purpose / activity", "type": "text"},
            _METHOD, _REFERENCE, _NOTES,
        ],
    },
    "membership_fees": {
        "description": "Quarterly membership dues paid by members.",
        "endpoints": ("add_membership_fee", "edit_membership_fee", "delete_membership_fee"),
        "columns": [("payment_date", "Paid on", "date"), ("member", "Member", ""),
                    ("period", "Period", ""), ("payment_method", "Method", ""),
                    ("amount", "Amount", "money")],
        "fields": [
            {"name": "membership_id", "label": "Member", "type": "member", "required": True, "full": True},
            {"name": "year", "label": "Dues year", "type": "number", "min": 2000, "max": 2100,
             "hint": "Leave blank to use the payment year."},
            {"name": "quarter", "label": "Quarter", "type": "select", "required": True,
             "options": ["", "Q1", "Q2", "Q3", "Q4"]},
            {"name": "payment_date", "label": "Payment date", "type": "date", "required": True},
            _AMOUNT, _METHOD, _REFERENCE, _NOTES,
        ],
    },
    "expenses": {
        "description": "Money spent on activities, materials, food, transportation and other costs.",
        "endpoints": ("add_expense", "edit_expense", "delete_expense"),
        "columns": [("expense_date", "Date", "date"), ("activity", "Activity", ""),
                    ("category", "Category", ""), ("description", "Description", ""),
                    ("amount", "Amount", "money")],
        "fields": [
            {"name": "expense_date", "label": "Date", "type": "date", "required": True},
            _AMOUNT,
            {"name": "activity", "label": "Activity / event", "type": "text", "full": True},
            {"name": "category", "label": "Category", "type": "text", "required": True, "list": "categories"},
            {"name": "description", "label": "Description", "type": "text"},
            _METHOD, _REFERENCE, _NOTES,
        ],
    },
}


def _form_value(value):
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def _ledger_rows(ledger_key, records):
    """Each record as display cells + the values the Edit form needs."""
    ui = LEDGER_UI[ledger_key]
    names = LEDGERS[ledger_key].field_names
    rows = []
    for record in records:
        values = {name: _form_value(getattr(record, name)) for name in names}
        cells = {}
        for field, _, _ in ui["columns"]:
            if field == "member":
                member = getattr(record, "member", None)
                cells[field] = f"{record.membership_id} — {member.full_name}" if member else record.membership_id
            elif field == "period":
                cells[field] = f"{record.year or ''}-{record.quarter}".strip("-")
            else:
                cells[field] = values.get(field, "")
        rows.append({
            "id": record.id,
            "values": values,
            "cells": cells,
            "amount": float(record.amount),
            "search": " ".join([*values.values(), *cells.values()]).lower(),
        })
    return rows


def _ledger_page(ledger_key, template="ledger.html", **extra):
    model = finance_records.MODELS[ledger_key]
    date_column = getattr(model, LEDGERS[ledger_key].date_field)
    records = model.query.order_by(date_column.desc(), model.id.desc()).all()
    required, optional = finance_ingestion.expected_columns(ledger_key)
    ui = LEDGER_UI[ledger_key]
    add_ep, edit_ep, delete_ep = ui["endpoints"]
    categories = sorted({
        c for (c,) in db.session.query(Expense.category).distinct() if c
    }) if ledger_key == "expenses" else []
    return render_template(
        template,
        ledger=LEDGERS[ledger_key],
        ledger_key=ledger_key,
        ui=ui,
        rows=_ledger_rows(ledger_key, records),
        total_amount=sum((r.amount for r in records), Decimal("0")),
        add_url=url_for(add_ep),
        edit_url_pattern=url_for(edit_ep, id=0).replace("/0/", "/__ID__/"),
        delete_url_pattern=url_for(delete_ep, id=0).replace("/0/", "/__ID__/"),
        import_url=(url_for("import_membership_fees") if ledger_key == "membership_fees"
                    else url_for("import_financial_records", ledger_key=ledger_key)),
        import_required_columns=required,
        import_optional_columns=optional,
        categories=categories,
        sheets_mirror_enabled=finance_sheets_mirror.is_enabled(),
        **extra
    )


def _add_record(ledger_key):
    outcome = finance_records.create(ledger_key, request.form, actor=current_user)
    noun = LEDGERS[ledger_key].noun
    _flash_outcome(outcome, f"{noun.capitalize()} added.")
    return _back_to_ledger(ledger_key)


def _edit_record(ledger_key, record_id):
    outcome = finance_records.update(ledger_key, record_id, request.form, actor=current_user)
    noun = LEDGERS[ledger_key].noun
    _flash_outcome(outcome, f"{noun.capitalize()} updated.")
    return _back_to_ledger(ledger_key)


def _delete_record(ledger_key, record_id):
    outcome = finance_records.delete(ledger_key, record_id, actor=current_user)
    noun = LEDGERS[ledger_key].noun
    _flash_outcome(outcome, f"{noun.capitalize()} deleted. Administrators can restore it from the Audit Log.")
    return _back_to_ledger(ledger_key)


IMPORT_TOKEN_MAX_AGE = 3600   # seconds a preview stays valid


def _import_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="finance-import")


def _import_overrides(form):
    """Reviewer answers from the preview page, keyed by row number."""
    overrides = {}
    for name, value in form.items():
        for prefix, key in (("fix_date_", "date"), ("fix_amount_", "amount"),
                            ("create_member_", "create_member"),
                            ("treat_as_paid_", "treat_as_paid")):
            if name.startswith(prefix) and name[len(prefix):].isdigit():
                row = int(name[len(prefix):])
                if key in ("create_member", "treat_as_paid"):
                    overrides.setdefault(row, {})[key] = value == "1"
                elif value.strip():
                    overrides.setdefault(row, {})[key] = value.strip()
    return overrides


def _render_import_preview(ledger_key, payload, token, overrides=None):
    try:
        preview = finance_records.analyze_upload(
            ledger_key, payload["headers"], payload["rows"],
            payload.get("quarter"), overrides,
        )
    except finance_ingestion.IngestionError as error:
        flash(str(error), "danger")
        return _back_to_ledger(ledger_key)
    return render_template(
        "import_preview.html",
        preview=preview,
        ledger=LEDGERS[ledger_key],
        ledger_key=ledger_key,
        filename=payload.get("filename", ""),
        token=token,
        overrides=overrides or {},
    )


def _import_records(ledger_key):
    """Step 1: read the upload and show a preview. Nothing is saved."""
    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose a CSV or Excel (.xlsx) file to import.", "danger")
        return _back_to_ledger(ledger_key)

    data = uploaded_file.read(finance_ingestion.MAX_UPLOAD_BYTES + 1)
    try:
        headers, rows = finance_ingestion.read_table(uploaded_file.filename, data)
    except finance_ingestion.IngestionError as error:
        flash(str(error), "danger")
        return _back_to_ledger(ledger_key)

    quarter = (request.form.get("quarter") or "").strip().upper() or \
        finance_membership_import.quarter_from_filename(uploaded_file.filename)
    payload = {
        "ledger": ledger_key,
        "quarter": quarter,
        "filename": uploaded_file.filename,
        "headers": headers,
        "rows": rows,
    }
    token = _import_serializer().dumps(payload)
    return _render_import_preview(ledger_key, payload, token)


@app.route("/financial/<ledger_key>/import/confirm", methods=["POST"])
@login_required
@encoder_required
def confirm_financial_import(ledger_key):
    """Step 2: re-check with the reviewer's answers, or save."""
    if ledger_key not in LEDGERS:
        abort(404)
    token = request.form.get("token", "")
    try:
        payload = _import_serializer().loads(token, max_age=IMPORT_TOKEN_MAX_AGE)
    except SignatureExpired:
        flash("This preview expired. Upload the file again.", "danger")
        return _back_to_ledger(ledger_key)
    except BadSignature:
        abort(400)
    if payload.get("ledger") != ledger_key:
        abort(400)

    overrides = _import_overrides(request.form)
    if request.form.get("action") != "confirm":
        return _render_import_preview(ledger_key, payload, token, overrides)

    try:
        report = finance_records.confirm_upload(
            ledger_key, payload["headers"], payload["rows"],
            payload.get("quarter"), overrides,
            actor=current_user, filename=payload.get("filename", ""),
        )
    except finance_ingestion.IngestionError as error:
        flash(str(error), "danger")
        return _back_to_ledger(ledger_key)

    if report.error:
        flash(report.error, "danger")
        return _back_to_ledger(ledger_key)

    parts = [f"{report.added} record(s) imported into {LEDGERS[ledger_key].label}"]
    if report.dues_saved:
        parts.append(f"{report.dues_saved} dues status line(s) saved")
    if report.members_created:
        parts.append(f"{report.members_created} new member(s) created (check their IDs on the Members page)")
    flash("Import complete: " + "; ".join(parts) + ".", "success")
    not_imported = report.left_for_review + report.skipped
    if not_imported or report.duplicates:
        flash(
            f"Not imported: {report.left_for_review} row(s) still needing review, "
            f"{report.skipped} row(s) with errors, {report.duplicates} duplicate(s). "
            "Fix them in the spreadsheet and upload it again; rows already "
            "imported are recognized and not added twice.",
            "warning"
        )
    if report.mirror_warning:
        flash(report.mirror_warning, "warning")
    return _back_to_ledger(ledger_key)


# ---------------- Fundraising ----------------

@app.route("/financial/fundraising")
@login_required
@encoder_required
def fundraising():
    return _ledger_page("fundraising")


@app.route("/financial/fundraising/add", methods=["POST"])
@login_required
@encoder_required
def add_fundraising():
    return _add_record("fundraising")


@app.route("/financial/fundraising/<int:id>/edit", methods=["POST"])
@login_required
@encoder_required
def edit_fundraising(id):
    return _edit_record("fundraising", id)


@app.route("/financial/fundraising/<int:id>/delete", methods=["POST"])
@login_required
@encoder_required
def delete_fundraising(id):
    return _delete_record("fundraising", id)


# ---------------- Sponsorships ----------------

@app.route("/financial/sponsorships")
@login_required
@encoder_required
def sponsorships():
    return _ledger_page("sponsorships")


@app.route("/financial/sponsorships/add", methods=["POST"])
@login_required
@encoder_required
def add_sponsorship():
    return _add_record("sponsorships")


@app.route("/financial/sponsorships/<int:id>/edit", methods=["POST"])
@login_required
@encoder_required
def edit_sponsorship(id):
    return _edit_record("sponsorships", id)


@app.route("/financial/sponsorships/<int:id>/delete", methods=["POST"])
@login_required
@encoder_required
def delete_sponsorship(id):
    return _delete_record("sponsorships", id)


# ---------------- Membership fees ----------------

@app.route("/financial/membership-fees")
@login_required
@encoder_required
def membership_fees():
    members = Member.query.filter_by(
        status="active"
    ).order_by(Member.membership_id).all()
    all_members = Member.query.order_by(
        Member.membership_id
    ).all()
    dues = Due.query.order_by(
        Due.year.desc(), Due.quarter.desc(), Due.status, Due.membership_id
    ).all()
    return _ledger_page(
        "membership_fees",
        members=members,
        all_members=all_members,
        dues=dues
    )


@app.route("/financial/membership-fees/add", methods=["POST"])
@login_required
@encoder_required
def add_membership_fee():
    return _add_record("membership_fees")


@app.route("/financial/membership-fees/<int:id>/edit", methods=["POST"])
@login_required
@encoder_required
def edit_membership_fee(id):
    return _edit_record("membership_fees", id)


@app.route("/financial/membership-fees/<int:id>/delete", methods=["POST"])
@login_required
@encoder_required
def delete_membership_fee(id):
    return _delete_record("membership_fees", id)


@app.route("/financial/membership-fees/import", methods=["POST"])
@login_required
@encoder_required
def import_membership_fees():
    return _import_records("membership_fees")


# ---------------- Expenses ----------------

@app.route("/financial/expenses")
@login_required
@encoder_required
def expenses():
    return _ledger_page("expenses")


@app.route("/financial/expenses/add", methods=["POST"])
@login_required
@encoder_required
def add_expense():
    return _add_record("expenses")


@app.route("/financial/expenses/<int:id>/edit", methods=["POST"])
@login_required
@encoder_required
def edit_expense(id):
    return _edit_record("expenses", id)


@app.route("/financial/expenses/<int:id>/delete", methods=["POST"])
@login_required
@encoder_required
def delete_expense(id):
    return _delete_record("expenses", id)


# ---------------- Import (any ledger) ----------------

@app.route("/financial/<ledger_key>/import", methods=["POST"])
@login_required
@encoder_required
def import_financial_records(ledger_key):
    if ledger_key not in LEDGERS:
        abort(404)
    return _import_records(ledger_key)


# ---------------- Google Sheet mirror ----------------

@app.route("/financial/sheet-status")
@login_required
@encoder_required
def finance_sheet_status():
    """JSON: does the Google Sheet match the database? Read-only."""
    ledger_key = request.args.get("ledger", "").strip()
    if ledger_key and ledger_key not in LEDGERS:
        abort(404)
    try:
        status = finance_records.sync_status([ledger_key] if ledger_key else None)
    except Exception:  # noqa: BLE001 - never break the page over a status check
        app.logger.exception("Sheet status check failed")
        status = {"enabled": True, "ok": False, "ledgers": [], "error": "The check could not be completed."}
    status["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    response = app.response_class(
        response=json.dumps(status), mimetype="application/json"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/admin/finance/sheets/resync", methods=["POST"])
@login_required
@admin_required
def resync_finance_sheet():
    if not finance_sheets_mirror.is_enabled():
        flash(
            "The Google Sheet mirror is not set up. Add GOOGLE_SHEET_ID and "
            "GOOGLE_SERVICE_ACCOUNT_B64 to the environment first.",
            "danger"
        )
        return redirect(url_for("financial_management"))

    results = finance_records.resync_all()
    failed = [(label, message) for label, ok, message in results if not ok]
    synced = [label for label, ok, _ in results if ok]
    finance_records.audit(
        "resync", "sheet", actor=current_user,
        summary="Resynced Google Sheet: " + (", ".join(synced) or "nothing")
        + (f"; failed: {', '.join(label for label, _ in failed)}" if failed else ""),
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Could not write the resync audit entry.")
    if synced:
        flash("Google Sheet updated: " + ", ".join(synced) + ".", "success")
    for label, message in failed:
        flash(f"{label} could not be synced: {message}", "danger")
    return redirect(url_for("financial_management"))


# ==================================================
# AUDIT LOG (admin)
# ==================================================

AUDIT_ACTION_LABELS = {
    "create": "Added", "update": "Edited", "delete": "Deleted", "import": "Imported",
    "restore": "Restored", "resync": "Sheet resync", "member_create": "Member created",
    "cancel": "Cancelled", "email": "Emails sent", "password_reset": "Password reset",
    "password_set": "Password set by admin", "reset_link": "Reset link sent",
    "export": "Exported", "request": "Export requested", "approve": "Approved",
    "reject": "Rejected", "download": "Downloaded",
}
AUDIT_ENTITY_LABELS = {
    **{key: ledger.label for key, ledger in LEDGERS.items()},
    "members": "Members", "sheet": "Google Sheet",
    "event": "Meeting / event", "notification": "Notifications", "account": "Account",
    "export": "Export",
}
AUDIT_PAGE_SIZE = 500


@app.route("/admin/audit-log")
@login_required
@admin_required
def audit_log():
    entries = AuditLog.query.order_by(
        AuditLog.occurred_at.desc(), AuditLog.id.desc()
    ).limit(AUDIT_PAGE_SIZE).all()
    restored = {
        related for (related,) in db.session.query(AuditLog.related_id)
        .filter(AuditLog.action == "restore", AuditLog.related_id.isnot(None))
    }
    rows = []
    for entry in entries:
        changes = []
        if entry.before and entry.after:
            for key in entry.after:
                if key != "id" and entry.before.get(key) != entry.after.get(key):
                    changes.append((key.replace("_", " ").capitalize(),
                                    entry.before.get(key), entry.after.get(key)))
        rows.append({
            "entry": entry,
            "when": entry.occurred_at,
            "action": AUDIT_ACTION_LABELS.get(entry.action, entry.action),
            "entity": AUDIT_ENTITY_LABELS.get(entry.entity, entry.entity),
            "changes": changes,
            "snapshot": entry.before if entry.action == "delete" else entry.after,
            "can_restore": (entry.action == "delete" and entry.entity in LEDGERS
                            and entry.before and entry.id not in restored),
            "restored": entry.id in restored,
        })
    return render_template(
        "audit_log.html",
        rows=rows,
        total=AuditLog.query.count(),
        page_size=AUDIT_PAGE_SIZE,
    )


@app.route("/admin/audit-log/<int:entry_id>/restore", methods=["POST"])
@login_required
@admin_required
def restore_audit_entry(entry_id):
    outcome = finance_records.restore(entry_id, actor=current_user)
    _flash_outcome(outcome, "Record restored.")
    return redirect(url_for("audit_log"))


# ==================================================
# KEEP-ALIVE (Vercel Cron)
#
# Supabase free projects pause after about a week without activity.
# vercel.json calls this once a day; it runs one tiny query. When the
# CRON_SECRET environment variable is set, Vercel sends it as a Bearer
# token and any other caller is refused.
# ==================================================

def _cron_authorized():
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if not secret:
        return True
    supplied = request.headers.get("Authorization", "")
    return hmac.compare_digest(supplied, f"Bearer {secret}")


def _run_reminders_safely():
    try:
        return notify.run_daily_reminders()
    except Exception:   # a reminder problem must never break the keep-alive
        db.session.rollback()
        app.logger.exception("Daily reminders failed.")
        return {"error": "reminders failed"}


@app.route("/api/keepalive")
def keepalive():
    if not _cron_authorized():
        abort(401)
    try:
        db.session.execute(db.text("select 1 from members limit 1"))
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Keep-alive query failed.")
        return {"ok": False}, 503
    return {"ok": True, "reminders": _run_reminders_safely()}


# A second daily run (evening in Manila) sends anything the morning run
# could not finish. Duplicates are impossible: each email is reserved first.
@app.route("/api/reminders")
def daily_reminders():
    if not _cron_authorized():
        abort(401)
    return {"ok": True, "reminders": _run_reminders_safely()}

# ==================================================
# EXPORT MANAGEMENT
#
# Who gets what:
#   * Monthly summary (totals only): any logged-in user downloads at once.
#   * Anything with personal data: admins download after re-entering their
#     password; everyone else sends a request with a purpose, an admin
#     approves (the download then works for a limited number of days) or
#     rejects with a reason, and the requester is emailed either way.
# Every export, approval, rejection and download is in the audit log.
# The file-building lives in services/exports.py.
# ==================================================

EXPORT_DEFAULT_DAYS = 7
EXPORT_MAX_DAYS = 30


def _export_options(form):
    """(dataset_key, fmt, start, end) or raises ValueError with a friendly message."""
    dataset_key = (form.get("dataset") or form.get("table_name") or "").strip()
    fmt = (form.get("export_format") or "").strip().lower()
    if dataset_key not in exports.DATASETS:
        raise ValueError("Choose what to export.")
    if exports.DATASETS[dataset_key].admin_only and current_user.role != "admin":
        raise ValueError("Only administrators can export that.")
    if fmt not in exports.FORMATS:
        raise ValueError("Choose Excel, CSV or PDF.")
    start = end = None
    if exports.DATASETS[dataset_key].uses_dates:
        try:
            start_value = (form.get("start_date") or "").strip()
            end_value = (form.get("end_date") or "").strip()
            start = datetime.strptime(start_value, "%Y-%m-%d").date() if start_value else None
            end = datetime.strptime(end_value, "%Y-%m-%d").date() if end_value else None
        except ValueError as error:
            raise ValueError("Enter valid dates (or leave them blank for everything).") from error
        if start and end and start > end:
            raise ValueError("The start date is after the end date.")
    return dataset_key, fmt, start, end


def _export_summary(dataset_key, fmt, start, end):
    period = exports._period_label(start, end) if exports.DATASETS[dataset_key].uses_dates else "current"
    return f"{exports.DATASETS[dataset_key].label} ({period}) as {fmt.upper()}"


def _send_export(dataset_key, fmt, start, end):
    sections = exports.build(dataset_key, start, end)
    meta = exports.Meta(
        dataset=exports.DATASETS[dataset_key], start=start, end=end,
        generated_by=current_user.email,
        generated_at=notify_messages.local(datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M"),
    )
    data, mimetype, ext = exports.render(sections, fmt, meta)
    return Response(data, mimetype=mimetype, headers={
        "Content-Disposition": f"attachment; filename={exports.filename(meta, ext)}",
        "Cache-Control": "no-store",
    })


def _expires(export_request):
    if export_request.expires_at is not None:
        return notify_messages.as_utc(export_request.expires_at)
    if export_request.approved_at is not None:
        return notify_messages.as_utc(export_request.approved_at) + timedelta(days=EXPORT_DEFAULT_DAYS)
    return None


def _request_state(export_request, now):
    if export_request.status == "approved":
        expires = _expires(export_request)
        return "expired" if expires and expires <= now else "ready"
    return export_request.status


def _request_rows(requests_list):
    now = datetime.now(timezone.utc)
    rows = []
    for r in requests_list:
        dataset = exports.DATASETS.get(r.table_name)
        rows.append({
            "req": r,
            "label": dataset.label if dataset else r.table_name.replace("_", " ").title(),
            "period": (exports._period_label(r.start_date, r.end_date)
                       if not dataset or dataset.uses_dates else "Current"),
            "state": _request_state(r, now),
            "expires": _expires(r),
            "name": r.requester.member.full_name if r.requester and r.requester.member else (r.requester.email if r.requester else ""),
        })
    return rows


def _email_export(kind, profile, subject, body):
    try:
        item = notify.Outgoing(member=profile.member, email=profile.email, subject=subject, body=body,
                               name=profile.member.full_name if profile.member else profile.email)
        notify.send_batch(kind, [item], sent_by="export management")
    except Exception:   # an email problem must never block the export workflow
        db.session.rollback()
        app.logger.exception("Export email failed.")


@app.route("/exports", methods=["GET", "POST"])
@login_required
def exports_page():
    if request.method == "POST":
        try:
            dataset_key, fmt, start, end = _export_options(request.form)
        except ValueError as error:
            flash(str(error), "danger")
            return redirect(url_for("exports_page"))
        summary = _export_summary(dataset_key, fmt, start, end)

        if exports.needs_approval(dataset_key, current_user.role):
            purpose = (request.form.get("purpose") or "").strip()
            if len(purpose) < 5:
                flash("Say briefly what the export is for, so an admin can approve it.", "danger")
                return redirect(url_for("exports_page"))
            export_request = ExportRequest(
                user_id=current_user.id, table_name=dataset_key, start_date=start, end_date=end,
                export_format=fmt, status="pending", purpose=purpose[:1000],
            )
            db.session.add(export_request)
            db.session.flush()
            finance_records.audit("request", "export", actor=current_user, record_id=export_request.id,
                                  summary=f"Requested {summary}. Purpose: {purpose[:300]}")
            db.session.commit()
            for admin in Profile.query.filter_by(role="admin", status="active"):
                subject, body = notify_messages.export_requested(
                    notify.first_name(admin.member) if admin.member else "admin",
                    current_user.email, summary, purpose, url_for("manage_export_requests", _external=True))
                _email_export("export_request", admin, subject, body)
            flash("Request sent. An administrator will review it, and you'll get an email when it's decided.", "success")
            return redirect(url_for("exports_page"))

        if current_user.role == "admin" and exports.DATASETS[dataset_key].personal:
            try:
                ok = password_is_correct(current_user, request.form.get("password", ""))
            except supabase_auth.AuthError as error:
                flash(str(error), "danger")
                return redirect(url_for("exports_page"))
            if not ok:
                flash("Incorrect password. Exports with personal data need your password.", "danger")
                return redirect(url_for("exports_page"))

        finance_records.audit("export", "export", actor=current_user, summary=f"Downloaded {summary}")
        db.session.commit()
        return _send_export(dataset_key, fmt, start, end)

    mine = ExportRequest.query.filter_by(user_id=current_user.id).order_by(
        ExportRequest.requested_at.desc()).limit(50).all()
    pending = (ExportRequest.query.filter_by(status="pending").count()
               if current_user.role == "admin" else 0)
    return render_template(
        "exports.html",
        datasets=exports.datasets_for(current_user.role),
        formats=exports.FORMATS,
        my_requests=_request_rows(mine),
        pending=pending,
        local=notify_messages.local,
    )


@app.route("/admin/export-requests")
@login_required
@admin_required
def manage_export_requests():
    all_requests = ExportRequest.query.order_by(ExportRequest.requested_at.desc()).limit(500).all()
    rows = _request_rows(all_requests)
    return render_template(
        "manage_export_requests.html",
        rows=rows,
        pending=[r for r in rows if r["state"] == "pending"],
        default_days=EXPORT_DEFAULT_DAYS,
        max_days=EXPORT_MAX_DAYS,
        local=notify_messages.local,
    )


def _decide(request_id, approve):
    export_request = ExportRequest.query.filter_by(id=request_id).with_for_update().first_or_404()
    if export_request.status != "pending":
        flash("This request was already decided.", "danger")
        return redirect(url_for("manage_export_requests"))
    note = (request.form.get("note") or "").strip()[:1000]
    now = datetime.now(timezone.utc)
    dataset = exports.DATASETS.get(export_request.table_name)
    summary = _export_summary(export_request.table_name, export_request.export_format,
                              export_request.start_date, export_request.end_date) if dataset else export_request.table_name
    requester = export_request.requester

    if approve:
        try:
            days = int(request.form.get("days") or EXPORT_DEFAULT_DAYS)
        except ValueError:
            days = EXPORT_DEFAULT_DAYS
        days = max(1, min(days, EXPORT_MAX_DAYS))
        export_request.status = "approved"
        export_request.approved_at = now
        export_request.expires_at = now + timedelta(days=days)
        action, verb = "approve", "Approved"
    else:
        if len(note) < 3:
            flash("Give a short reason for rejecting, so the requester knows why.", "danger")
            return redirect(url_for("manage_export_requests"))
        export_request.status = "rejected"
        export_request.rejected_at = now
        action, verb = "reject", "Rejected"
    export_request.admin_id = current_user.id
    export_request.decision_note = note or None
    finance_records.audit(action, "export", actor=current_user, record_id=export_request.id,
                          summary=f"{verb} {requester.email if requester else ''}'s request: {summary}"
                                  + (f". Note: {note}" if note else ""))
    db.session.commit()

    if requester is not None:
        subject, body = notify_messages.export_decided(
            notify.first_name(requester.member) if requester.member else "there",
            approve, summary, note,
            notify_messages.when_text(export_request.expires_at) if approve else "",
            url_for("exports_page", _external=True))
        _email_export("export_decision", requester, subject, body)
    flash(f"{verb}. {requester.email if requester else 'The requester'} has been emailed.", "success")
    return redirect(url_for("manage_export_requests"))


@app.route("/admin/export-requests/<int:request_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_export_request(request_id):
    return _decide(request_id, True)


@app.route("/admin/export-requests/<int:request_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_export_request(request_id):
    return _decide(request_id, False)


@app.route("/exports/requests/<int:request_id>/download")
@login_required
def download_approved_export(request_id):
    export_request = db.get_or_404(ExportRequest, request_id)
    if current_user.role != "admin" and export_request.user_id != current_user.id:
        abort(403)
    state = _request_state(export_request, datetime.now(timezone.utc))
    if state != "ready" or export_request.table_name not in exports.DATASETS:
        flash("This export isn't available: it is pending, rejected or expired. Send a new request.", "danger")
        return redirect(url_for("exports_page"))
    export_request.download_count = (export_request.download_count or 0) + 1
    export_request.last_downloaded_at = datetime.now(timezone.utc)
    summary = _export_summary(export_request.table_name, export_request.export_format,
                              export_request.start_date, export_request.end_date)
    finance_records.audit("download", "export", actor=current_user, record_id=export_request.id,
                          summary=f"Downloaded approved request #{export_request.id}: {summary}")
    db.session.commit()
    return _send_export(export_request.table_name, export_request.export_format,
                        export_request.start_date, export_request.end_date)


# Old addresses from before Export Management moved to its own page.
@app.route("/financial/export/request", methods=["POST"])
@app.route("/financial/export/verify", methods=["GET", "POST"])
@app.route("/financial/export/download")
@login_required
def legacy_export_routes():
    return redirect(url_for("exports_page"))


@app.route("/financial/export-requests/<int:request_id>/download")
@login_required
def legacy_download_approved_export(request_id):
    return redirect(url_for("download_approved_export", request_id=request_id))

# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )