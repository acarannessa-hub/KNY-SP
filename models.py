from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


# ==================================================
# USER
# ==================================================

class User(db.Model, UserMixin):

    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    full_name = db.Column(
        db.String(150),
        nullable=False
    )

    email = db.Column(
        db.String(150),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(50),
        nullable=False,
        default="viewer"
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="active"
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp()
    )


# ==================================================
# FUNDRAISING
# ==================================================

class Fundraising(db.Model):

    __tablename__ = "fundraising"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    fundraising_date = db.Column(
        db.Date,
        nullable=False
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    payment_method = db.Column(
        db.String(50)
    )

    reference_no = db.Column(
        db.String(100)
    )

    notes = db.Column(
        db.Text
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp()
    )


# ==================================================
# SPONSORSHIPS
# ==================================================

class Sponsorship(db.Model):

    __tablename__ = "sponsorships"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    sponsorship_date = db.Column(
        db.Date,
        nullable=False
    )

    sponsor_name = db.Column(
        db.String(150),
        nullable=False
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    payment_method = db.Column(
        db.String(50)
    )

    reference_no = db.Column(
        db.String(100)
    )

    notes = db.Column(
        db.Text
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp()
    )


# ==================================================
# MEMBERSHIP FEES
# ==================================================

class MembershipFee(db.Model):

    __tablename__ = "membership_fees"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    member_id = db.Column(
        db.Integer,
        db.ForeignKey("members.id"),
        nullable=False
    )

    quarter = db.Column(
        db.Enum(
            "Q1",
            "Q2",
            "Q3",
            "Q4"
        ),
        nullable=False
    )

    payment_date = db.Column(
        db.Date,
        nullable=False
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    payment_method = db.Column(
        db.String(50)
    )

    reference_no = db.Column(
        db.String(100)
    )

    notes = db.Column(
        db.Text
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp()
    )


# ==================================================
# EXPENSES
# ==================================================

class Expense(db.Model):

    __tablename__ = "expenses"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    expense_date = db.Column(
        db.Date,
        nullable=False
    )

    category = db.Column(
        db.String(100),
        nullable=False
    )

    description = db.Column(
        db.Text
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    payment_method = db.Column(
        db.String(50)
    )

    reference_no = db.Column(
        db.String(100)
    )

    notes = db.Column(
        db.Text
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp()
    )

class ExportRequest(db.Model):
    __tablename__ = "export_requests"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    requester_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    table_name = db.Column(
        db.String(100),
        nullable=False
    )

    start_date = db.Column(
        db.Date,
        nullable=True
    )

    end_date = db.Column(
        db.Date,
        nullable=True
    )

    export_format = db.Column(
        db.Enum("csv", "pdf"),
        nullable=False
    )

    status = db.Column(
        db.Enum(
            "pending",
            "approved",
            "rejected"
        ),
        nullable=False,
        default="pending"
    )

    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    requested_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp()
    )

    approved_at = db.Column(
        db.DateTime,
        nullable=True
    )

    rejected_at = db.Column(
        db.DateTime,
        nullable=True
    )