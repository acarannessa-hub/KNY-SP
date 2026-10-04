import os

from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)
from flask_bcrypt import Bcrypt
from functools import wraps
from dotenv import load_dotenv

from models import (
    db,
    User,
    Fundraising,
    Sponsorship,
    MembershipFee,
    Expense
)


# ==================================================
# LOAD ENVIRONMENT VARIABLES
# ==================================================

load_dotenv()


# ==================================================
# CREATE APPLICATION
# ==================================================

app = Flask(__name__)


# ==================================================
# CONFIGURATION
# ==================================================

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "development-secret-key"
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# ==================================================
# INITIALIZE
# ==================================================

db.init_app(app)

bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)

login_manager.login_view = "login"


# ==================================================
# USER LOADER
# ==================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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

@app.route("/", methods=["GET", "POST"])
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

        user = User.query.filter_by(
            email=email
        ).first()

        if user is None:

            flash(
                "Invalid email or password.",
                "danger"
            )

            return redirect(url_for("login"))

        if user.status != "active":

            flash(
                "Your account is inactive.",
                "danger"
            )

            return redirect(url_for("login"))

        try:

            password_correct = bcrypt.check_password_hash(
                user.password_hash,
                password
            )

        except ValueError:

            password_correct = False

        if not password_correct:

            flash(
                "Invalid email or password.",
                "danger"
            )

            return redirect(url_for("login"))

        login_user(user)

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

            password_correct = bcrypt.check_password_hash(
                current_user.password_hash,
                current_password
            )

        except ValueError:

            password_correct = False

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
        # GENERATE NEW PASSWORD HASH
        # ------------------------------------------

        new_hash = bcrypt.generate_password_hash(
            new_password
        ).decode("utf-8")

        current_user.password_hash = new_hash

        db.session.commit()

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

    users = User.query.order_by(
        User.created_at.desc()
    ).all()

    return render_template(
        "manage_users.html",
        user=current_user,
        users=users
    )


# ==================================================
# ADD USER
# ==================================================

@app.route(
    "/admin/users/add",
    methods=["POST"]
)
@login_required
@admin_required
def add_user():

    full_name = request.form.get(
        "full_name",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    role = request.form.get(
        "role",
        "viewer"
    )

    status = request.form.get(
        "status",
        "active"
    )

    # ------------------------------------------
    # VALIDATE REQUIRED FIELDS
    # ------------------------------------------

    if not full_name or not email or not password:

        flash(
            "Please complete all required fields.",
            "danger"
        )

        return redirect(
            url_for("manage_users")
        )

    # ------------------------------------------
    # CHECK EXISTING EMAIL
    # ------------------------------------------

    existing_user = User.query.filter_by(
        email=email
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
    # HASH PASSWORD
    # ------------------------------------------

    password_hash = bcrypt.generate_password_hash(
        password
    ).decode("utf-8")

    # ------------------------------------------
    # CREATE USER
    # ------------------------------------------

    new_user = User(
        full_name=full_name,
        email=email,
        password_hash=password_hash,
        role=role,
        status=status
    )

    db.session.add(new_user)

    db.session.commit()

    flash(
        "User added successfully.",
        "success"
    )

    return redirect(
        url_for("manage_users")
    )


# ==================================================
# CHANGE USER STATUS
# ==================================================

@app.route(
    "/admin/users/<int:user_id>/toggle-status",
    methods=["POST"]
)
@login_required
@admin_required
def toggle_user_status(user_id):

    user = User.query.get_or_404(
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
    "/admin/users/<int:user_id>/reset-password",
    methods=["POST"]
)
@login_required
@admin_required
def reset_password(user_id):

    user = User.query.get_or_404(
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

    user.password_hash = bcrypt.generate_password_hash(
        new_password
    ).decode("utf-8")

    db.session.commit()

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

    return render_template(
        "financial_management.html",
        fundraising=fundraising,
        sponsorships=sponsorships,
        membership_fees=membership_fees,
        expenses=expenses,
        user=current_user
    )


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

    return render_template(
        "membership_fees.html",
        records=records
    )


@app.route(
    "/financial/membership-fees/add",
    methods=["POST"]
)
@login_required
@encoder_required
def add_membership_fee():

    record = MembershipFee(
        member_id=request.form.get(
            "member_id"
        ),
        quarter=request.form.get(
            "quarter"
        ),
        payment_date=request.form.get(
            "payment_date"
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

    record.member_id = request.form.get(
        "member_id"
    )

    record.quarter = request.form.get(
        "quarter"
    )

    record.payment_date = request.form.get(
        "payment_date"
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
        "Membership fee record updated.",
        "success"
    )

    return redirect(
        url_for("financial_management")
    )


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
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )