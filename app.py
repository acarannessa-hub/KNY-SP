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


@app.route("/")
def public_home():

    return render_template(
        "public/landing.html"
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
        looker_embed_url=embed_url
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

    return render_template(
        "dashboard.html",
        user=current_user
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

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        flash(
            "If that email is registered, please contact an administrator to reset your password.",
            "success"
        )

        return redirect(
            url_for("forgot_password")
        )

    return render_template(
        "forgot_password.html"
    )


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
# ADMIN USER MANAGEMENT
# ==================================================

@app.route("/admin/users")
@login_required
@admin_required
def manage_users():

    search = request.args.get("search", "").strip()
    org_role = request.args.get("org_role", "").strip()
    system_role = request.args.get("system_role", "").strip()
    status = request.args.get("status", "").strip()

    query = Profile.query.join(Profile.member)
    if search:
        search_pattern = f"%{search}%"
        full_name = (
            Member.first_name
            + " "
            + db.func.coalesce(Member.middle_name, "")
            + " "
            + Member.last_name
        )
        name_without_middle = (
            Member.first_name + " " + Member.last_name
        )
        query = query.filter(
            db.or_(
                Member.first_name.ilike(search_pattern),
                Member.middle_name.ilike(search_pattern),
                Member.last_name.ilike(search_pattern),
                full_name.ilike(search_pattern),
                name_without_middle.ilike(search_pattern),
                Profile.email.ilike(search_pattern),
                Member.membership_id.ilike(search_pattern)
            )
        )
    if org_role:
        query = query.filter(Member.org_role == org_role)
    if system_role in {"admin", "encoder", "viewer"}:
        query = query.filter(Profile.role == system_role)
    elif system_role:
        system_role = ""
    if status in {"active", "inactive"}:
        query = query.filter(Profile.status == status)
    elif status:
        status = ""

    users = query.order_by(Profile.created_at.desc()).all()
    org_roles = [
        role for (role,) in db.session.query(Member.org_role)
        .distinct()
        .order_by(Member.org_role)
        .all()
        if role
    ]
    members = Member.query.order_by(
        Member.membership_id
    ).all()

    return render_template(
        "manage_users.html",
        user=current_user,
        users=users,
        members=members,
        org_roles=org_roles,
        search=search,
        selected_org_role=org_role,
        selected_system_role=system_role,
        selected_status=status
    )


# ==================================================
# ADMIN MEMBER MANAGEMENT
# ==================================================

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


@app.route("/admin/members")
@login_required
@admin_required
def manage_members():

    search = request.args.get("q", "").strip()
    query = Member.query
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Member.membership_id.ilike(search_term),
                Member.first_name.ilike(search_term),
                Member.middle_name.ilike(search_term),
                Member.last_name.ilike(search_term),
                Member.org_role.ilike(search_term),
                Member.email.ilike(search_term)
            )
        )

    members = query.order_by(Member.membership_id).all()
    return render_template(
        "manage_members.html",
        members=members,
        search=search
    )


@app.route(
    "/admin/members/add",
    methods=["POST"]
)
@login_required
@admin_required
def add_member():

    membership_id = request.form.get("membership_id", "").strip()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    middle_name = request.form.get("middle_name", "").strip()
    org_role = request.form.get("org_role", "Member").strip()
    email, email_error = _member_email(request.form.get("email"))

    if not all((membership_id, first_name, last_name, org_role)):
        flash("Membership ID, first name, last name, and org role are required.", "danger")
        return redirect(url_for("manage_members"))
    if email_error:
        flash(email_error, "danger")
        return redirect(url_for("manage_members"))

    if Member.query.filter_by(membership_id=membership_id).first():
        flash("That Membership ID is already in use.", "danger")
        return redirect(url_for("manage_members"))
    if email and _member_email_taken(email):
        flash("Another member already uses that email.", "danger")
        return redirect(url_for("manage_members"))

    db.session.add(Member(
        membership_id=membership_id,
        first_name=first_name,
        middle_name=middle_name or None,
        last_name=last_name,
        org_role=org_role,
        email=email,
        status="active"
    ))
    db.session.commit()
    flash("Member added successfully.", "success")
    return redirect(url_for("manage_members"))


@app.route(
    "/admin/members/<int:member_id>/edit",
    methods=["POST"]
)
@login_required
@admin_required
def edit_member(member_id):

    member = Member.query.get_or_404(member_id)
    membership_id = request.form.get("membership_id", "").strip()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    middle_name = request.form.get("middle_name", "").strip()
    org_role = request.form.get("org_role", "").strip()
    status = request.form.get("status", "")
    email, email_error = _member_email(request.form.get("email"))

    if not all((membership_id, first_name, last_name, org_role)):
        flash("Membership ID, first name, last name, and org role are required.", "danger")
        return redirect(url_for("manage_members"))
    if email_error:
        flash(email_error, "danger")
        return redirect(url_for("manage_members"))
    if email and _member_email_taken(email, exclude_id=member.id):
        flash("Another member already uses that email.", "danger")
        return redirect(url_for("manage_members"))
    if status not in {"active", "inactive"}:
        flash("Choose a valid member status.", "danger")
        return redirect(url_for("manage_members"))
    duplicate = Member.query.filter(
        Member.membership_id == membership_id,
        Member.id != member.id
    ).first()
    if duplicate:
        flash("That Membership ID is already in use.", "danger")
        return redirect(url_for("manage_members"))

    if membership_id != member.membership_id:
        for account in member.users:
            account.membership_id = membership_id
        for fee in member.membership_fees:
            fee.membership_id = membership_id

    member.membership_id = membership_id
    member.first_name = first_name
    member.middle_name = middle_name or None
    member.last_name = last_name
    member.org_role = org_role
    member.email = email
    member.status = status
    db.session.commit()
    flash("Member information updated.", "success")
    return redirect(url_for("manage_members"))


# ==================================================
# ADD USER
# ==================================================

@app.route(
    "/admin/users/add",
    methods=["GET", "POST"]
)
@login_required
@admin_required
def add_user():

    if request.method == "GET":

        members = Member.query.filter_by(status="active").order_by(
            Member.membership_id
        ).all()

        return render_template("add_user.html", members=members)

    membership_id = request.form.get(
        "membership_id",
        ""
    ).strip()

    # Supabase treats emails as case-insensitive and stores them in lowercase.
    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    )

    role = request.form.get(
        "role",
        ""
    )

    status = request.form.get(
        "status",
        "active"
    )

    if not email:
        flash("Email is required.", "danger")
        return redirect(url_for("manage_users"))

    # ------------------------------------------
    # VALIDATE REQUIRED FIELDS
    # ------------------------------------------

    member = Member.query.filter_by(
        membership_id=membership_id
    ).first()

    if not member or member.status != "active":

        flash(
            "Select an active organization member for this account.",
            "danger"
        )

        return redirect(
            url_for("manage_users")
        )

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("manage_users"))

    if role not in {"admin", "encoder", "viewer"}:
        flash("Choose a valid system role.", "danger")
        return redirect(url_for("manage_users"))

    if status not in {"active", "inactive"}:
        flash("Choose a valid account status.", "danger")
        return redirect(url_for("manage_users"))

    # ------------------------------------------
    # CHECK EXISTING EMAIL
    # ------------------------------------------

    existing_user = Profile.query.filter(
        db.func.lower(Profile.email) == email
    ).first()

    if existing_user:

        flash(
            "A user with that email already exists.",
            "danger"
        )

        return redirect(
            url_for("manage_users")
        )

    # ------------------------------------------
    # 1) CREATE THE LOGIN IN SUPABASE AUTH
    # ------------------------------------------

    try:
        auth_id = supabase_auth.create_user(email, password)
    except supabase_auth.AuthError as error:
        flash(str(error), "danger")
        return redirect(url_for("manage_users"))

    # ------------------------------------------
    # 2) CREATE THE PROFILE (role, status, member)
    # ------------------------------------------

    try:
        new_profile = Profile(
            id=auth_id,
            membership_id=membership_id,
            email=email,
            role=role,
            status=status
        )

        db.session.add(new_profile)
        # Notifications go to the member's email; fill it from the login if empty.
        if not member.email and not _member_email_taken(email):
            member.email = email
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Could not save the profile for a new login.")

        # Undo step 1 so no login exists without a profile.
        supabase_auth.delete_user(auth_id)

        flash(
            "The account could not be saved. Nothing was created.",
            "danger"
        )

        return redirect(url_for("manage_users"))

    flash(
        "User added successfully.",
        "success"
    )

    return redirect(
        url_for("manage_users")
    )

# ==================================================
# EDIT USER
# ==================================================

@app.route(
    "/admin/users/<uuid:user_id>/edit",
    methods=["GET", "POST"]
)
@login_required
@admin_required
def edit_user(user_id):

    user = Profile.query.get_or_404(
        user_id
    )

    if request.method == "GET":

        members = Member.query.order_by(Member.membership_id).all()

        return render_template(
            "edit_user.html",
            user=user,
            members=members
        )

    membership_id = request.form.get(
        "membership_id",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    role = request.form.get(
        "role",
        ""
    )

    status = request.form.get(
        "status",
        "active"
    )

    if not email:
        flash("Email is required.", "danger")
        return redirect(url_for("manage_users"))

    # ------------------------------------------
    # VALIDATE REQUIRED FIELDS
    # ------------------------------------------

    member = Member.query.filter_by(
        membership_id=membership_id
    ).first()

    if not member or not email:

        flash(
            "Select an existing member and provide an email address.",
            "danger"
        )

        return redirect(
            url_for("manage_users")
        )

    if role not in {"admin", "encoder", "viewer"}:
        flash("Choose a valid system role.", "danger")
        return redirect(url_for("manage_users"))

    if status not in {"active", "inactive"}:
        flash("Choose a valid account status.", "danger")
        return redirect(url_for("manage_users"))

    # ------------------------------------------
    # CHECK IF EMAIL IS ALREADY USED
    # ------------------------------------------

    existing_user = Profile.query.filter(
        db.func.lower(Profile.email) == email,
        Profile.id != user.id
    ).first()

    if existing_user:

        flash(
            "A user with that email already exists.",
            "danger"
        )

        return redirect(
            url_for("manage_users")
        )

    # ------------------------------------------
    # UPDATE USER INFORMATION
    # (database first, then the login email in Supabase; if Supabase
    #  refuses, the database change is rolled back too)
    # ------------------------------------------

    email_changed = email != (user.email or "").lower()

    user.membership_id = membership_id
    user.email = email
    user.role = role
    user.status = status

    try:
        db.session.flush()

        if email_changed:
            supabase_auth.update_user(user.id, email=email)

        db.session.commit()

    except supabase_auth.AuthError as error:
        db.session.rollback()
        flash(str(error), "danger")
        return redirect(url_for("manage_users"))

    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Could not update a user profile.")
        flash("The changes could not be saved.", "danger")
        return redirect(url_for("manage_users"))

    flash(
        "User information updated successfully.",
        "success"
    )

    return redirect(
        url_for("manage_users")
    )

# ==================================================
# CHANGE USER STATUS
# ==================================================

@app.route(
    "/admin/users/<uuid:user_id>/toggle-status",
    methods=["POST"]
)
@login_required
@admin_required
def toggle_user_status(user_id):

    user = Profile.query.get_or_404(
        user_id
    )

    # ------------------------------------------
    # PREVENT ADMIN FROM DISABLING OWN ACCOUNT
    # ------------------------------------------

    if user.id == current_user.id:

        flash(
            "You cannot deactivate your own account.",
            "danger"
        )

        return redirect(
            url_for("manage_users")
        )

    # ------------------------------------------
    # TOGGLE STATUS
    # ------------------------------------------

    if user.status == "active":

        user.status = "inactive"

    else:

        user.status = "active"

    db.session.commit()

    flash(
        "User status updated.",
        "success"
    )

    return redirect(
        url_for("manage_users")
    )


# ==================================================
# ADMIN RESET USER PASSWORD
# ==================================================

@app.route(
    "/admin/users/<uuid:user_id>/reset-password",
    methods=["POST"]
)
@login_required
@admin_required
def reset_password(user_id):

    user = Profile.query.get_or_404(
        user_id
    )

    new_password = request.form.get(
        "new_password",
        ""
    )

    if len(new_password) < 8:

        flash(
            "Password must be at least 8 characters.",
            "danger"
        )

        return redirect(
            url_for("manage_users")
        )

    try:
        supabase_auth.update_user(
            user.id,
            password=new_password
        )
    except supabase_auth.AuthError as error:
        flash(str(error), "danger")
        return redirect(url_for("manage_users"))

    flash(
        f"Password for {user.email} has been reset.",
        "success"
    )

    return redirect(
        url_for("manage_users")
    )

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
    export_requests = ExportRequest.query.filter_by(
        user_id=current_user.id
    ).order_by(
        ExportRequest.requested_at.desc()
    ).all()

    return render_template(
        "financial_management.html",
        fundraising=fundraising,
        sponsorships=sponsorships,
        membership_fees=membership_fees,
        expenses=expenses,
        export_requests=export_requests,
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
    "cancel": "Cancelled", "email": "Emails sent",
}
AUDIT_ENTITY_LABELS = {
    **{key: ledger.label for key, ledger in LEDGERS.items()},
    "members": "Members", "sheet": "Google Sheet",
    "event": "Meeting / event", "notification": "Notifications",
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
# FINANCIAL EXPORT REQUESTS
# ==================================================

FINANCIAL_EXPORT_TABLES = {
    "fundraising": ("Fundraising", Fundraising, Fundraising.fundraising_date),
    "sponsorships": ("Sponsorships", Sponsorship, Sponsorship.sponsorship_date),
    "membership_fees": ("Membership Fees", MembershipFee, MembershipFee.payment_date),
    "expenses": ("Expenses", Expense, Expense.expense_date),
}
FINANCIAL_EXPORT_FORMATS = {"csv", "pdf"}


def _validated_export_options(form):
    table_name = (form.get("table_name") or "").strip()
    export_format = (form.get("export_format") or "").strip().lower()
    if table_name not in {*FINANCIAL_EXPORT_TABLES, "all"}:
        raise ValueError("Select a valid financial table.")
    if export_format not in FINANCIAL_EXPORT_FORMATS:
        raise ValueError("Select CSV or PDF as the export format.")

    start_value = (form.get("start_date") or "").strip()
    end_value = (form.get("end_date") or "").strip()
    try:
        start_date = datetime.strptime(start_value, "%Y-%m-%d").date() if start_value else None
        end_date = datetime.strptime(end_value, "%Y-%m-%d").date() if end_value else None
    except ValueError as error:
        raise ValueError("Enter valid start and end dates.") from error
    if start_date and end_date and start_date > end_date:
        raise ValueError("Start date cannot be later than end date.")
    return table_name, export_format, start_date, end_date


def _financial_export_rows(table_name, start_date, end_date):
    tables = (
        FINANCIAL_EXPORT_TABLES
        if table_name == "all"
        else {table_name: FINANCIAL_EXPORT_TABLES[table_name]}
    )
    sections = []
    for key, (label, model, date_column) in tables.items():
        query = model.query
        if start_date:
            query = query.filter(date_column >= start_date)
        if end_date:
            query = query.filter(date_column <= end_date)
        records = query.order_by(date_column, model.id).all()
        rows = []
        for record in records:
            row = {
                "category": label,
                "date": getattr(record, date_column.key).isoformat(),
                "membership_id": "",
                "member_name": "",
                "org_role": "",
                "description": "",
                "amount": record.amount,
                "payment_method": record.payment_method or "",
                "reference_no": record.reference_no or "",
                "notes": record.notes or "",
            }
            if key == "membership_fees":
                row["membership_id"] = record.member.membership_id
                row["member_name"] = record.member.full_name
                row["org_role"] = record.member.org_role
                row["description"] = record.quarter
            elif key == "sponsorships":
                row["description"] = record.sponsor_name
            elif key == "expenses":
                row["description"] = " - ".join(
                    part for part in (
                        record.category,
                        record.description
                    )
                    if part
                )
            rows.append(row)
        sections.append((key, label, rows))
    return sections


def _generate_financial_export(table_name, export_format, start_date, end_date):
    sections = _financial_export_rows(table_name, start_date, end_date)
    generated_on = date.today().isoformat()
    title = (
        "All Financial Records"
        if table_name == "all"
        else FINANCIAL_EXPORT_TABLES[table_name][0]
    )
    filename_prefix = "financial" if table_name == "all" else table_name
    filename = f"{filename_prefix}_export_{generated_on}.{export_format}"
    period = (
        f"{start_date.isoformat() if start_date else 'Beginning'} to "
        f"{end_date.isoformat() if end_date else 'Present'}"
    )

    if export_format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "Category",
            "Date",
            "Membership_ID",
            "Member_Name",
            "Org_Role",
            "Description",
            "Amount",
            "Payment_Method",
            "Reference_No",
            "Notes"
        ])
        for _, _, rows in sections:
            for row in rows:
                writer.writerow([
                    row["category"],
                    row["date"],
                    row["membership_id"],
                    row["member_name"],
                    row["org_role"],
                    row["description"],
                    f"{row['amount']:.2f}",
                    row["payment_method"],
                    row["reference_no"],
                    row["notes"]
                ])
        return Response(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle
    )

    from xml.sax.saxutils import escape

    pdf_buffer = io.BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(letter),
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "FinancialExportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#5d4b9a")
    )
    cell_style = ParagraphStyle(
        "FinancialExportCell",
        parent=styles["BodyText"],
        fontSize=7,
        leading=8
    )
    story = [
        Paragraph("Organization Name (customize here)", styles["Heading2"]),
        Paragraph(escape(title), title_style),
        Paragraph(
            f"Date range: {escape(period)} &nbsp;&nbsp; "
            f"Generated: {generated_on}",
            styles["Normal"]
        ),
        Spacer(1, 12)
    ]
    grand_total = Decimal("0")
    category_totals = {}
    for _, label, rows in sections:
        story.append(Paragraph(escape(label), styles["Heading2"]))
        data = [[
            "Date", "Member / Payee", "Org Role", "Description",
            "Amount", "Payment", "Reference", "Notes"
        ]]
        if not rows:
            data.append(["No records found for this date range.", "", "", "", "", "", "", ""])
        total = Decimal("0")
        for row in rows:
            amount = Decimal(row["amount"])
            total += amount
            payee = row["member_name"] or row["description"]
            data.append([
                row["date"],
                Paragraph(escape(payee), cell_style),
                Paragraph(escape(row["org_role"]), cell_style),
                Paragraph(escape(row["description"]), cell_style),
                f"{amount:,.2f}",
                Paragraph(escape(row["payment_method"]), cell_style),
                Paragraph(escape(row["reference_no"]), cell_style),
                Paragraph(escape(row["notes"]), cell_style)
            ])
        category_totals[label] = total
        grand_total += total if label != "Expenses" else -total
        data.append(["", "", "", "Total", f"{total:,.2f}", "", "", ""])
        report_table = Table(
            data,
            repeatRows=1,
            colWidths=[
                0.78 * inch, 1.35 * inch, 1.0 * inch, 1.9 * inch,
                0.85 * inch, 0.95 * inch, 1.1 * inch, 2.1 * inch
            ]
        )
        table_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5d4b9a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d9d6e3")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e9e3f5")),
            ("FONTNAME", (3, -1), (4, -1), "Helvetica-Bold"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)
        ]
        if len(data) > 2:
            table_style.append((
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -2),
                [colors.white, colors.HexColor("#f4f2f8")]
            ))
        report_table.setStyle(TableStyle(table_style))
        story.extend((report_table, Spacer(1, 10)))

    if table_name == "all":
        summary = " | ".join(
            f"{label}: {amount:,.2f}"
            for label, amount in category_totals.items()
        )
        story.append(Paragraph(
            f"Category totals — {escape(summary)}",
            styles["Heading3"]
        ))
        story.append(Paragraph(
            f"Net total (income less expenses): {grand_total:,.2f}",
            styles["Heading3"]
        ))

    document.build(story)
    pdf_buffer.seek(0)
    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route(
    "/financial/export/request",
    methods=["POST"]
)
@login_required
def request_export():

    try:
        table_name, export_format, start_date, end_date = (
            _validated_export_options(request.form)
        )
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("financial_management"))

    if current_user.role == "admin":
        session.pop("verified_admin_export", None)
        session["admin_export_request"] = {
            "table_name": table_name,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "export_format": export_format
        }
        return redirect(url_for("verify_admin_export"))

    export_request = ExportRequest(
        user_id=current_user.id,
        table_name=table_name,
        start_date=start_date,
        end_date=end_date,
        export_format=export_format,
        status="pending"
    )
    db.session.add(export_request)
    db.session.commit()
    flash(
        "Export request submitted and is waiting for administrator approval.",
        "success"
    )
    return redirect(url_for("financial_management"))


@app.route("/admin/export-requests")
@login_required
@admin_required
def manage_export_requests():

    requests = ExportRequest.query.order_by(
        ExportRequest.requested_at.desc()
    ).all()
    return render_template(
        "manage_export_requests.html",
        export_requests=requests
    )


def _process_export_request(request_id, status):
    export_request = ExportRequest.query.filter_by(
        id=request_id
    ).with_for_update().first_or_404()
    if export_request.status != "pending":
        flash("This export request has already been processed.", "danger")
        return redirect(url_for("manage_export_requests"))

    export_request.status = status
    export_request.admin_id = current_user.id
    if status == "approved":
        export_request.approved_at = datetime.now(timezone.utc)
        export_request.rejected_at = None
        flash("Export request approved.", "success")
    else:
        export_request.rejected_at = datetime.now(timezone.utc)
        export_request.approved_at = None
        flash("Export request rejected.", "success")
    db.session.commit()
    return redirect(url_for("manage_export_requests"))


@app.route(
    "/admin/export-requests/<int:request_id>/approve",
    methods=["POST"]
)
@login_required
@admin_required
def approve_export_request(request_id):
    return _process_export_request(request_id, "approved")


@app.route(
    "/admin/export-requests/<int:request_id>/reject",
    methods=["POST"]
)
@login_required
@admin_required
def reject_export_request(request_id):
    return _process_export_request(request_id, "rejected")

# ==================================================
# ADMIN EXPORT CREDENTIAL VERIFICATION
# ==================================================

@app.route(
    "/financial/export/verify",
    methods=["GET", "POST"]
)
@login_required
def verify_admin_export():

    if current_user.role != "admin":
        abort(403)

    export_data = session.get("admin_export_request")
    if not export_data:
        flash("Export request expired. Please submit a new request.", "danger")
        return redirect(url_for("financial_management"))

    if request.method == "POST":
        password = request.form.get("password", "")
        if not password:
            flash("Please enter your password.", "danger")
            return redirect(url_for("verify_admin_export"))
        try:
            password_correct = password_is_correct(
                current_user,
                password
            )
        except supabase_auth.AuthError as error:
            flash(str(error), "danger")
            return redirect(url_for("verify_admin_export"))

        if not password_correct:
            flash("Incorrect password.", "danger")
            return redirect(url_for("verify_admin_export"))

        session["verified_admin_export"] = True
        return redirect(url_for("download_financial_export"))

    return render_template(
        "verify_export.html"
    )


# ==================================================
# FINANCIAL EXPORT DOWNLOAD
# ==================================================

@app.route(
    "/financial/export/download"
)
@login_required
def download_financial_export():

    if current_user.role != "admin":
        abort(403)

    export_data = session.get("admin_export_request")
    if not export_data:
        flash("No export request found.", "danger")
        return redirect(url_for("financial_management"))
    if not session.get("verified_admin_export"):
        flash("Please verify your password before downloading.", "danger")
        return redirect(url_for("verify_admin_export"))

    try:
        table_name, export_format, start_date, end_date = (
            _validated_export_options(export_data)
        )
    except ValueError:
        session.pop("admin_export_request", None)
        session.pop("verified_admin_export", None)
        flash("The export request is invalid. Please submit it again.", "danger")
        return redirect(url_for("financial_management"))

    response = _generate_financial_export(
        table_name, export_format, start_date, end_date
    )
    session.pop("admin_export_request", None)
    session.pop("verified_admin_export", None)
    return response


@app.route("/financial/export-requests/<int:request_id>/download")
@login_required
def download_approved_export(request_id):

    export_request = ExportRequest.query.get_or_404(request_id)
    if (
        current_user.role != "admin"
        and export_request.user_id != current_user.id
    ):
        abort(403)
    if export_request.status != "approved":
        abort(403)

    return _generate_financial_export(
        export_request.table_name,
        export_request.export_format,
        export_request.start_date,
        export_request.end_date
    )

# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )