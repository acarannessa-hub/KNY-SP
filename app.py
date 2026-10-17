import csv
import io
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
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

from models import (
        db,
    Profile,
    Member,
    Fundraising,
    Sponsorship,
    MembershipFee,
    Attendance,
    Expense,
    ExportRequest
)
import supabase_auth


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

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "development-secret-key"
)

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


@app.route("/financial-dashboard")
def public_financial_dashboard():

    return render_template(
        "public/financial_dashboard.html"
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


def attendance_read_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        if current_user.role not in {"admin", "encoder", "viewer"}:
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


ATTENDANCE_STATUSES = ("Present", "Absent", "Late", "Excused")


def _parse_attendance_date(value, label):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError(f"Enter a valid {label}.") from error


def _parse_attendance_time(value, label):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as error:
        raise ValueError(f"Enter a valid {label} using HH:MM.") from error


def _attendance_filters(args):
    filters = {
        "attendance_date": args.get("attendance_date", "").strip(),
        "start_date": args.get("start_date", "").strip(),
        "end_date": args.get("end_date", "").strip(),
        "membership_id": args.get("membership_id", "").strip(),
        "search": args.get("search", "").strip(),
        "status": args.get("status", "").strip(),
    }
    selected_date = _parse_attendance_date(
        filters["attendance_date"], "attendance date"
    )
    start_date = _parse_attendance_date(
        filters["start_date"], "start date"
    )
    end_date = _parse_attendance_date(
        filters["end_date"], "end date"
    )
    if start_date and end_date and start_date > end_date:
        raise ValueError("Start date cannot be later than end date.")

    query = Attendance.query.join(Attendance.member)
    if selected_date:
        query = query.filter(Attendance.attendance_date == selected_date)
    if start_date:
        query = query.filter(Attendance.attendance_date >= start_date)
    if end_date:
        query = query.filter(Attendance.attendance_date <= end_date)
    if filters["membership_id"]:
        query = query.filter(
            Member.membership_id == filters["membership_id"]
        )
    if filters["search"]:
        search_pattern = f"%{filters['search']}%"
        full_name = (
            Member.first_name
            + " "
            + db.func.coalesce(Member.middle_name, "")
            + " "
            + Member.last_name
        )
        query = query.filter(
            db.or_(
                Member.membership_id.ilike(search_pattern),
                Member.first_name.ilike(search_pattern),
                Member.middle_name.ilike(search_pattern),
                Member.last_name.ilike(search_pattern),
                full_name.ilike(search_pattern)
            )
        )
    if filters["status"] in ATTENDANCE_STATUSES:
        query = query.filter(
            Attendance.attendance_status == filters["status"]
        )
    elif filters["status"]:
        filters["status"] = ""

    return query, filters


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
                Member.org_role.ilike(search_term)
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

    if not all((membership_id, first_name, last_name, org_role)):
        flash("Membership ID, first name, last name, and org role are required.", "danger")
        return redirect(url_for("manage_members"))

    if Member.query.filter_by(membership_id=membership_id).first():
        flash("That Membership ID is already in use.", "danger")
        return redirect(url_for("manage_members"))

    db.session.add(Member(
        membership_id=membership_id,
        first_name=first_name,
        middle_name=middle_name or None,
        last_name=last_name,
        org_role=org_role,
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

    if not all((membership_id, first_name, last_name, org_role)):
        flash("Membership ID, first name, last name, and org role are required.", "danger")
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
        user=current_user
    )


# ==================================================
# ATTENDANCE MANAGEMENT
# ==================================================

@app.route("/attendance")
@login_required
@attendance_read_required
def attendance_management():

    today = date.today()
    selected_date_text = request.args.get("attendance_date", "").strip()
    try:
        selected_date = _parse_attendance_date(
            selected_date_text, "attendance date"
        ) or today
    except ValueError as error:
        flash(str(error), "danger")
        selected_date = today

    members = Member.query.filter_by(status="active").order_by(
        Member.membership_id
    ).all()
    existing_records = Attendance.query.filter(
        Attendance.attendance_date == selected_date
    ).all()
    attendance_by_member = {
        record.membership_id: record for record in existing_records
    }

    recent_query = Attendance.query.join(Attendance.member).filter(
        Attendance.attendance_date >= today - timedelta(days=2),
        Attendance.attendance_date <= today
    )
    member_search = request.args.get("search", "").strip()
    membership_id = request.args.get("membership_id", "").strip()
    status = request.args.get("status", "").strip()
    if member_search:
        search_pattern = f"%{member_search}%"
        full_name = (
            Member.first_name
            + " "
            + db.func.coalesce(Member.middle_name, "")
            + " "
            + Member.last_name
        )
        recent_query = recent_query.filter(
            db.or_(
                Member.membership_id.ilike(search_pattern),
                Member.first_name.ilike(search_pattern),
                Member.middle_name.ilike(search_pattern),
                Member.last_name.ilike(search_pattern),
                full_name.ilike(search_pattern)
            )
        )
    if membership_id:
        recent_query = recent_query.filter(
            Member.membership_id == membership_id
        )
    if status in ATTENDANCE_STATUSES:
        recent_query = recent_query.filter(
            Attendance.attendance_status == status
        )
    elif status:
        status = ""

    recent_records = recent_query.order_by(
        Attendance.attendance_date.desc(),
        Member.last_name,
        Member.first_name
    ).all()

    return render_template(
        "attendance.html",
        members=members,
        attendance_by_member=attendance_by_member,
        selected_date=selected_date,
        recent_records=recent_records,
        attendance_statuses=ATTENDANCE_STATUSES,
        member_search=member_search,
        selected_membership_id=membership_id,
        selected_status=status
    )


@app.route(
    "/attendance/save",
    methods=["POST"]
)
@login_required
@encoder_required
def save_attendance():

    try:
        attendance_date = _parse_attendance_date(
            request.form.get("attendance_date", ""),
            "attendance date"
        )
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("attendance_management"))
    if attendance_date is None:
        flash("Attendance date is required.", "danger")
        return redirect(url_for("attendance_management"))

    members = Member.query.filter_by(status="active").all()
    updates = []
    for member in members:
        attendance_status = request.form.get(
            f"status_{member.membership_id}", ""
        ).strip()
        if not attendance_status:
            continue
        if attendance_status not in ATTENDANCE_STATUSES:
            flash(
                f"Invalid attendance status for {member.membership_id}.",
                "danger"
            )
            return redirect(url_for(
                "attendance_management",
                attendance_date=attendance_date.isoformat()
            ))
        try:
            time_in = _parse_attendance_time(
                request.form.get(f"time_in_{member.membership_id}", ""),
                "time in"
            )
            time_out = _parse_attendance_time(
                request.form.get(f"time_out_{member.membership_id}", ""),
                "time out"
            )
        except ValueError as error:
            flash(
                f"{member.membership_id}: {error}",
                "danger"
            )
            return redirect(url_for(
                "attendance_management",
                attendance_date=attendance_date.isoformat()
            ))
        updates.append((
            member,
            attendance_status,
            time_in,
            time_out,
            request.form.get(
                f"remarks_{member.membership_id}", ""
            ).strip()
        ))

    if not updates:
        flash("Choose an attendance status for at least one member.", "danger")
        return redirect(url_for(
            "attendance_management",
            attendance_date=attendance_date.isoformat()
        ))

    member_ids = [member.membership_id for member, *_ in updates]
    existing_records = Attendance.query.filter(
        Attendance.attendance_date == attendance_date,
        Attendance.membership_id.in_(member_ids)
    ).all()
    records_by_member = {
        record.membership_id: record for record in existing_records
    }
    for member, attendance_status, time_in, time_out, remarks in updates:
        record = records_by_member.get(member.membership_id)
        if record is None:
            record = Attendance(
                membership_id=member.membership_id,
                attendance_date=attendance_date
            )
            db.session.add(record)
        record.attendance_status = attendance_status
        record.time_in = time_in
        record.time_out = time_out
        record.remarks = remarks or None

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception(
            "Failed to save attendance for %s.", attendance_date
        )
        flash(
            "Attendance could not be saved. Please retry; duplicate "
            "member/date records are prevented.",
            "danger"
        )
        return redirect(url_for(
            "attendance_management",
            attendance_date=attendance_date.isoformat()
        ))

    flash(
        f"Attendance saved for {len(updates)} member(s) on "
        f"{attendance_date.isoformat()}.",
        "success"
    )
    return redirect(url_for(
        "attendance_management",
        attendance_date=attendance_date.isoformat()
    ))


@app.route(
    "/attendance/<int:attendance_id>/edit",
    methods=["POST"]
)
@login_required
@encoder_required
def edit_attendance(attendance_id):

    record = Attendance.query.get_or_404(attendance_id)
    attendance_status = request.form.get(
        "attendance_status", ""
    ).strip()
    if attendance_status not in ATTENDANCE_STATUSES:
        flash("Choose a valid attendance status.", "danger")
        return redirect(url_for("attendance_history"))
    try:
        time_in = _parse_attendance_time(
            request.form.get("time_in", ""),
            "time in"
        )
        time_out = _parse_attendance_time(
            request.form.get("time_out", ""),
            "time out"
        )
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("attendance_history"))

    record.attendance_status = attendance_status
    record.time_in = time_in
    record.time_out = time_out
    record.remarks = request.form.get("remarks", "").strip() or None
    db.session.commit()
    flash("Attendance record updated.", "success")
    return redirect(url_for(
        "attendance_history",
        **request.args.to_dict()
    ))


@app.route(
    "/attendance/<int:attendance_id>/delete",
    methods=["POST"]
)
@login_required
@admin_required
def delete_attendance(attendance_id):

    record = Attendance.query.get_or_404(attendance_id)
    db.session.delete(record)
    db.session.commit()
    flash("Attendance record deleted.", "success")
    return redirect(url_for(
        "attendance_history",
        **request.args.to_dict()
    ))


@app.route("/attendance/history")
@login_required
@attendance_read_required
def attendance_history():

    try:
        query, filters = _attendance_filters(request.args)
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("attendance_history"))

    records = query.order_by(
        Attendance.attendance_date.desc(),
        Member.last_name,
        Member.first_name
    ).all()
    members = Member.query.order_by(Member.membership_id).all()
    return render_template(
        "attendance_history.html",
        records=records,
        members=members,
        filters=filters,
        attendance_statuses=ATTENDANCE_STATUSES
    )


@app.route(
    "/attendance/import",
    methods=["POST"]
)
@login_required
@encoder_required
def import_attendance():

    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose an attendance CSV file to import.", "danger")
        return redirect(url_for("attendance_management"))
    try:
        content = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("The CSV file must use UTF-8 encoding.", "danger")
        return redirect(url_for("attendance_management"))

    reader = csv.DictReader(io.StringIO(content), strict=True)
    required_headers = {
        "membership_id",
        "attendance_date",
        "attendance_status"
    }
    if not reader.fieldnames:
        flash("The CSV file is empty or has no header row.", "danger")
        return redirect(url_for("attendance_management"))
    header_map = {
        (header or "").strip().casefold(): header
        for header in reader.fieldnames
    }
    if not required_headers.issubset(header_map):
        flash(
            "CSV headers must include Membership_ID, Attendance_Date, "
            "and Attendance_Status. Time_In, Time_Out, and Remarks are optional.",
            "danger"
        )
        return redirect(url_for("attendance_management"))
    try:
        rows = list(reader)
    except csv.Error:
        flash(
            "The CSV file contains malformed rows and was not imported.",
            "danger"
        )
        return redirect(url_for("attendance_management"))

    optional_headers = {
        "time_in", "time_out", "remarks"
    }
    members_by_id = {
        member.membership_id: member
        for member in Member.query.all()
    }
    errors = []
    validated_rows = []
    seen_pairs = set()
    for row_number, row in enumerate(rows, start=2):
        values = {
            field: (row.get(header_map[field]) or "").strip()
            for field in required_headers | (optional_headers & header_map.keys())
        }
        if not any(values.values()):
            continue
        membership_id = values["membership_id"]
        member = members_by_id.get(membership_id)
        if not member:
            errors.append(
                f"Row {row_number}: Membership_ID '{membership_id}' "
                "does not exist."
            )
            continue
        try:
            attendance_date = _parse_attendance_date(
                values["attendance_date"], "attendance date"
            )
        except ValueError:
            attendance_date = None
        if attendance_date is None:
            errors.append(f"Row {row_number}: invalid Attendance_Date.")
            continue
        status = values["attendance_status"].casefold()
        status_by_casefold = {
            item.casefold(): item for item in ATTENDANCE_STATUSES
        }
        attendance_status = status_by_casefold.get(status)
        if attendance_status is None:
            errors.append(f"Row {row_number}: invalid Attendance_Status.")
            continue
        pair = (membership_id, attendance_date)
        if pair in seen_pairs:
            errors.append(
                f"Row {row_number}: duplicate member/date pair in CSV."
            )
            continue
        seen_pairs.add(pair)
        try:
            time_in = _parse_attendance_time(
                values.get("time_in", ""), "time in"
            )
            time_out = _parse_attendance_time(
                values.get("time_out", ""), "time out"
            )
        except ValueError as error:
            errors.append(f"Row {row_number}: {error}")
            continue
        validated_rows.append({
            "membership_id": membership_id,
            "attendance_date": attendance_date,
            "attendance_status": attendance_status,
            "time_in": time_in,
            "time_out": time_out,
            "remarks": values.get("remarks", "") or None
        })

    existing_by_pair = {}
    grouped_by_date = {}
    for row in validated_rows:
        grouped_by_date.setdefault(
            row["attendance_date"], set()
        ).add(row["membership_id"])
    for attendance_date, member_ids in grouped_by_date.items():
        existing_records = Attendance.query.filter(
            Attendance.attendance_date == attendance_date,
            Attendance.membership_id.in_(member_ids)
        ).all()
        existing_by_pair.update({
            (record.membership_id, record.attendance_date): record
            for record in existing_records
        })

    imported = 0
    updated = 0
    for row in validated_rows:
        key = (row["membership_id"], row["attendance_date"])
        record = existing_by_pair.get(key)
        if record is None:
            record = Attendance(
                membership_id=row["membership_id"],
                attendance_date=row["attendance_date"]
            )
            db.session.add(record)
            existing_by_pair[key] = record
            imported += 1
        else:
            updated += 1
        record.attendance_status = row["attendance_status"]
        record.time_in = row["time_in"]
        record.time_out = row["time_out"]
        record.remarks = row["remarks"]

    if validated_rows:
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Failed to import attendance CSV.")
            flash(
                "Attendance CSV could not be saved. No import changes were "
                "committed.",
                "danger"
            )
            return redirect(url_for("attendance_management"))

    if imported or updated:
        flash(
            f"Attendance import complete: {imported} added, "
            f"{updated} existing record(s) updated.",
            "success"
        )
    if errors:
        details = " ".join(errors[:10])
        if len(errors) > 10:
            details += f" Plus {len(errors) - 10} additional invalid row(s)."
        flash(f"Skipped {len(errors)} row(s). {details}", "danger")
    if not validated_rows and not errors:
        flash("The CSV contains no attendance records.", "danger")
    return redirect(url_for("attendance_management"))


def _attendance_export_response(export_format):
    try:
        query, filters = _attendance_filters(request.args)
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("attendance_history"))

    records = query.order_by(
        Attendance.attendance_date.desc(),
        Member.last_name,
        Member.first_name
    ).all()
    if export_format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "Membership_ID",
            "Last_Name",
            "First_Name",
            "Middle_Name",
            "Org_Role",
            "Attendance_Date",
            "Attendance_Status",
            "Time_In",
            "Time_Out",
            "Remarks"
        ])
        for record in records:
            member = record.member
            writer.writerow([
                member.membership_id,
                member.last_name,
                member.first_name,
                member.middle_name or "",
                member.org_role,
                record.attendance_date.isoformat(),
                record.attendance_status,
                record.time_in.strftime("%H:%M") if record.time_in else "",
                record.time_out.strftime("%H:%M") if record.time_out else "",
                record.remarks or ""
            ])
        return Response(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition":
                    "attachment; filename=attendance-report.csv"
            }
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

    pdf_buffer = io.BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(letter),
        rightMargin=0.35 * inch,
        leftMargin=0.35 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AttendanceTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#5d4b9a")
    )
    cell_style = ParagraphStyle(
        "AttendanceCell",
        parent=styles["BodyText"],
        fontSize=7,
        leading=8
    )
    date_label = (
        filters["attendance_date"]
        or (
            f"{filters['start_date']} to {filters['end_date']}"
            if filters["start_date"] or filters["end_date"]
            else "All dates"
        )
    )
    status_counts = {
        status: sum(
            record.attendance_status == status for record in records
        )
        for status in ATTENDANCE_STATUSES
    }
    total = len(records)
    total_members = len({
        record.membership_id for record in records
    })
    attendance_rate = (
        (status_counts["Present"] + status_counts["Late"]) / total * 100
        if total else 0
    )
    story = [
        Paragraph("Organization Name (customize here)", styles["Heading2"]),
        Paragraph("Attendance Report", title_style),
        Paragraph(
            f"Date: {date_label} &nbsp;&nbsp; "
            f"Generated: {date.today().isoformat()}",
            styles["Normal"]
        ),
        Spacer(1, 10),
        Paragraph(
            f"Total Members: {total_members} &nbsp;&nbsp; "
            f"Attendance Records: {total} &nbsp;&nbsp; "
            f"Present: {status_counts['Present']} &nbsp;&nbsp; "
            f"Absent: {status_counts['Absent']} &nbsp;&nbsp; "
            f"Late: {status_counts['Late']} &nbsp;&nbsp; "
            f"Excused: {status_counts['Excused']} &nbsp;&nbsp; "
            f"Attendance Rate (Present + Late): {attendance_rate:.1f}%",
            styles["Normal"]
        ),
        Spacer(1, 10)
    ]
    table_data = [[
        "Membership ID", "Last Name", "First Name", "Middle Name",
        "Org Role", "Date", "Status", "Time In", "Time Out", "Remarks"
    ]]
    for record in records:
        member = record.member
        table_data.append([
            Paragraph(escape(member.membership_id), cell_style),
            Paragraph(escape(member.last_name), cell_style),
            Paragraph(escape(member.first_name), cell_style),
            Paragraph(escape(member.middle_name or ""), cell_style),
            Paragraph(escape(member.org_role), cell_style),
            record.attendance_date.isoformat(),
            record.attendance_status,
            record.time_in.strftime("%H:%M") if record.time_in else "",
            record.time_out.strftime("%H:%M") if record.time_out else "",
            Paragraph(escape(record.remarks or ""), cell_style)
        ])
    report_table = Table(
        table_data,
        repeatRows=1,
        colWidths=[
            0.78 * inch, 0.83 * inch, 0.83 * inch, 0.83 * inch,
            0.78 * inch, 0.68 * inch, 0.62 * inch, 0.52 * inch,
            0.52 * inch, 2.25 * inch
        ]
    )
    report_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5d4b9a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d9d6e3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#f4f2f8")
        ]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4)
    ]))
    story.append(report_table)
    document.build(story)
    pdf_buffer.seek(0)
    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                "attachment; filename=attendance-report.pdf"
        }
    )


@app.route("/attendance/export.csv")
@login_required
@encoder_required
def export_attendance_csv():
    return _attendance_export_response("csv")


@app.route("/attendance/export.pdf")
@login_required
@encoder_required
def export_attendance_pdf():
    return _attendance_export_response("pdf")


# ==================================================
# FUNDRAISING
# ==================================================

@app.route(
    "/financial/fundraising"
)
@login_required
@encoder_required
def fundraising():

    records = Fundraising.query.order_by(
        Fundraising.fundraising_date.desc()
    ).all()

    return render_template(
        "fundraising.html",
        records=records
    )


@app.route(
    "/financial/fundraising/add",
    methods=["POST"]
)
@login_required
@encoder_required
def add_fundraising():

    record = Fundraising(
        fundraising_date=request.form.get(
            "fundraising_date"
        ),
        amount=request.form.get(
            "amount"
        ),
        payment_method=request.form.get(
            "payment_method"
        ),
        reference_no=request.form.get(
            "reference_no"
        ),
        notes=request.form.get(
            "notes"
        )
    )

    db.session.add(record)

    db.session.commit()

    flash(
        "Fundraising record added successfully.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


@app.route(
    "/financial/fundraising/<int:id>/edit",
    methods=["POST"]
)
@login_required
@encoder_required
def edit_fundraising(id):

    record = Fundraising.query.get_or_404(
        id
    )

    record.fundraising_date = request.form.get(
        "fundraising_date"
    )

    record.amount = request.form.get(
        "amount"
    )

    record.payment_method = request.form.get(
        "payment_method"
    )

    record.reference_no = request.form.get(
        "reference_no"
    )

    record.notes = request.form.get(
        "notes"
    )

    db.session.commit()

    flash(
        "Fundraising record updated.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


@app.route(
    "/financial/fundraising/<int:id>/delete",
    methods=["POST"]
)
@login_required
@encoder_required
def delete_fundraising(id):

    record = Fundraising.query.get_or_404(
        id
    )

    db.session.delete(record)

    db.session.commit()

    flash(
        "Fundraising record deleted.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


# ==================================================
# SPONSORSHIPS
# ==================================================

@app.route(
    "/financial/sponsorships"
)
@login_required
@encoder_required
def sponsorships():

    records = Sponsorship.query.order_by(
        Sponsorship.sponsorship_date.desc()
    ).all()

    return render_template(
        "sponsorships.html",
        records=records
    )


@app.route(
    "/financial/sponsorships/add",
    methods=["POST"]
)
@login_required
@encoder_required
def add_sponsorship():

    record = Sponsorship(
        sponsorship_date=request.form.get(
            "sponsorship_date"
        ),
        sponsor_name=request.form.get(
            "sponsor_name"
        ),
        amount=request.form.get(
            "amount"
        ),
        payment_method=request.form.get(
            "payment_method"
        ),
        reference_no=request.form.get(
            "reference_no"
        ),
        notes=request.form.get(
            "notes"
        )
    )

    db.session.add(record)

    db.session.commit()

    flash(
        "Sponsorship record added successfully.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


@app.route(
    "/financial/sponsorships/<int:id>/edit",
    methods=["POST"]
)
@login_required
@encoder_required
def edit_sponsorship(id):

    record = Sponsorship.query.get_or_404(
        id
    )

    record.sponsorship_date = request.form.get(
        "sponsorship_date"
    )

    record.sponsor_name = request.form.get(
        "sponsor_name"
    )

    record.amount = request.form.get(
        "amount"
    )

    record.payment_method = request.form.get(
        "payment_method"
    )

    record.reference_no = request.form.get(
        "reference_no"
    )

    record.notes = request.form.get(
        "notes"
    )

    db.session.commit()

    flash(
        "Sponsorship record updated.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


@app.route(
    "/financial/sponsorships/<int:id>/delete",
    methods=["POST"]
)
@login_required
@encoder_required
def delete_sponsorship(id):

    record = Sponsorship.query.get_or_404(
        id
    )

    db.session.delete(record)

    db.session.commit()

    flash(
        "Sponsorship record deleted.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


# ==================================================
# MEMBERSHIP FEES
# ==================================================

@app.route(
    "/financial/membership-fees"
)
@login_required
@encoder_required
def membership_fees():

    records = MembershipFee.query.order_by(
        MembershipFee.payment_date.desc()
    ).all()
    members = Member.query.filter_by(
        status="active"
    ).order_by(Member.membership_id).all()
    all_members = Member.query.order_by(
        Member.membership_id
    ).all()

    return render_template(
        "membership_fees.html",
        records=records,
        members=members,
        all_members=all_members
    )


@app.route(
    "/financial/membership-fees/add",
    methods=["POST"]
)
@login_required
@encoder_required
def add_membership_fee():

    membership_id = request.form.get(
        "membership_id",
        ""
    ).strip()
    member = Member.query.filter_by(
        membership_id=membership_id,
        status="active"
    ).first()
    if not member:
        flash("Select an existing active member.", "danger")
        return redirect(url_for("membership_fees"))

    try:
        payment_date = datetime.strptime(
            request.form.get("payment_date", ""),
            "%Y-%m-%d"
        ).date()
        amount = Decimal(request.form.get("amount", ""))
    except (ValueError, InvalidOperation):
        flash("Enter a valid payment date and amount.", "danger")
        return redirect(url_for("membership_fees"))
    quarter = request.form.get("quarter", "")
    if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
        flash("Choose a valid membership-fee quarter.", "danger")
        return redirect(url_for("membership_fees"))
    if not amount.is_finite() or amount <= 0:
        flash("The payment amount must be greater than zero.", "danger")
        return redirect(url_for("membership_fees"))

    record = MembershipFee(
        membership_id=membership_id,
        quarter=quarter,
        payment_date=payment_date,
        amount=amount,
        payment_method=request.form.get(
            "payment_method"
        ),
        reference_no=request.form.get(
            "reference_no"
        ),
        notes=request.form.get(
            "notes"
        )
    )

    db.session.add(record)

    db.session.commit()

    flash(
        "Membership fee record added successfully.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


@app.route(
    "/financial/membership-fees/<int:id>/edit",
    methods=["POST"]
)
@login_required
@encoder_required
def edit_membership_fee(id):

    record = MembershipFee.query.get_or_404(
        id
    )

    membership_id = request.form.get("membership_id", "").strip()
    member = Member.query.filter_by(membership_id=membership_id).first()
    quarter = request.form.get("quarter", "")
    try:
        payment_date = datetime.strptime(
            request.form.get("payment_date", ""),
            "%Y-%m-%d"
        ).date()
        amount = Decimal(request.form.get("amount", ""))
    except (ValueError, InvalidOperation):
        flash("Enter a valid payment date and amount.", "danger")
        return redirect(url_for("membership_fees"))
    if not member:
        flash("Select an existing member.", "danger")
        return redirect(url_for("membership_fees"))
    if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
        flash("Choose a valid membership-fee quarter.", "danger")
        return redirect(url_for("membership_fees"))
    if not amount.is_finite() or amount <= 0:
        flash("The payment amount must be greater than zero.", "danger")
        return redirect(url_for("membership_fees"))

    record.membership_id = membership_id
    record.quarter = quarter
    record.payment_date = payment_date
    record.amount = amount

    record.payment_method = request.form.get(
        "payment_method"
    )

    record.reference_no = request.form.get(
        "reference_no"
    )

    record.notes = request.form.get(
        "notes"
    )

    db.session.commit()

    flash(
        "Membership fee record updated.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


@app.route(
    "/financial/membership-fees/import",
    methods=["POST"]
)
@login_required
@encoder_required
def import_membership_fees():

    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose a membership-fee CSV file to import.", "danger")
        return redirect(url_for("membership_fees"))

    try:
        content = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("The CSV file must use UTF-8 encoding.", "danger")
        return redirect(url_for("membership_fees"))

    reader = csv.DictReader(io.StringIO(content), strict=True)
    if not reader.fieldnames:
        flash("The CSV file is empty or has no header row.", "danger")
        return redirect(url_for("membership_fees"))

    header_map = {
        (header or "").strip().casefold(): header
        for header in reader.fieldnames
    }
    required_headers = {
        "membership_id",
        "quarter",
        "payment_date",
        "amount",
        "payment_method",
        "reference_no",
        "notes",
    }
    if not required_headers.issubset(header_map):
        flash(
            "CSV headers must include Membership_ID, Quarter, Payment_Date, "
            "Amount, Payment_Method, Reference_No, and Notes.",
            "danger"
        )
        return redirect(url_for("membership_fees"))

    try:
        csv_rows = list(reader)
    except csv.Error:
        flash("The CSV file contains malformed rows and was not imported.", "danger")
        return redirect(url_for("membership_fees"))

    members_by_id = {
        member.membership_id: member
        for member in Member.query.all()
    }
    imported = 0
    errors = []
    for row_number, row in enumerate(csv_rows, start=2):
        values = {
            field: (row.get(header_map[field]) or "").strip()
            for field in required_headers
        }
        if not any(values.values()):
            continue

        membership_id = values["membership_id"]
        member = members_by_id.get(membership_id)
        if not member:
            errors.append(
                f"Row {row_number}: Membership_ID '{membership_id}' "
                "does not exist."
            )
            continue
        quarter = values["quarter"].upper()
        if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
            errors.append(f"Row {row_number}: invalid Quarter.")
            continue
        try:
            payment_date = datetime.strptime(
                values["payment_date"],
                "%Y-%m-%d"
            ).date()
            amount = Decimal(values["amount"])
        except (ValueError, InvalidOperation):
            errors.append(
                f"Row {row_number}: invalid Payment_Date or Amount."
            )
            continue
        if not amount.is_finite() or amount <= 0:
            errors.append(
                f"Row {row_number}: Amount must be greater than zero."
            )
            continue

        db.session.add(MembershipFee(
            membership_id=member.membership_id,
            quarter=quarter,
            payment_date=payment_date,
            amount=amount,
            payment_method=values["payment_method"] or None,
            reference_no=values["reference_no"] or None,
            notes=values["notes"] or None
        ))
        imported += 1

    if imported:
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Failed to import membership-fee CSV.")
            flash(
                "The CSV import could not be saved; no imported rows were "
                "committed. Check the server log for details.",
                "danger"
            )
            return redirect(url_for("membership_fees"))

    if imported:
        flash(f"Imported {imported} membership-fee record(s).", "success")
    if errors:
        details = " ".join(errors[:10])
        if len(errors) > 10:
            details += f" Plus {len(errors) - 10} additional invalid row(s)."
        flash(f"Skipped {len(errors)} row(s). {details}", "danger")
    if not imported and not errors:
        flash("The CSV contains no membership-fee records.", "danger")

    return redirect(url_for("membership_fees"))


@app.route(
    "/financial/membership-fees/<int:id>/delete",
    methods=["POST"]
)
@login_required
@encoder_required
def delete_membership_fee(id):

    record = MembershipFee.query.get_or_404(
        id
    )

    db.session.delete(record)

    db.session.commit()

    flash(
        "Membership fee record deleted.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


# ==================================================
# EXPENSES
# ==================================================

@app.route(
    "/financial/expenses"
)
@login_required
@encoder_required
def expenses():

    records = Expense.query.order_by(
        Expense.expense_date.desc()
    ).all()

    return render_template(
        "expenses.html",
        records=records
    )


@app.route(
    "/financial/expenses/add",
    methods=["POST"]
)
@login_required
@encoder_required
def add_expense():

    record = Expense(
        expense_date=request.form.get(
            "expense_date"
        ),
        category=request.form.get(
            "category"
        ),
        description=request.form.get(
            "description"
        ),
        amount=request.form.get(
            "amount"
        ),
        payment_method=request.form.get(
            "payment_method"
        ),
        reference_no=request.form.get(
            "reference_no"
        ),
        notes=request.form.get(
            "notes"
        )
    )

    db.session.add(record)

    db.session.commit()

    flash(
        "Expense record added successfully.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


@app.route(
    "/financial/expenses/<int:id>/edit",
    methods=["POST"]
)
@login_required
@encoder_required
def edit_expense(id):

    record = Expense.query.get_or_404(
        id
    )

    record.expense_date = request.form.get(
        "expense_date"
    )

    record.category = request.form.get(
        "category"
    )

    record.description = request.form.get(
        "description"
    )

    record.amount = request.form.get(
        "amount"
    )

    record.payment_method = request.form.get(
        "payment_method"
    )

    record.reference_no = request.form.get(
        "reference_no"
    )

    record.notes = request.form.get(
        "notes"
    )

    db.session.commit()

    flash(
        "Expense record updated.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


@app.route(
    "/financial/expenses/<int:id>/delete",
    methods=["POST"]
)
@login_required
@encoder_required
def delete_expense(id):

    record = Expense.query.get_or_404(
        id
    )

    db.session.delete(record)

    db.session.commit()

    flash(
        "Expense record deleted.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )

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