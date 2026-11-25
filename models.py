from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import JSON, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Supabase/PostgreSQL, plain JSON elsewhere (local tests use SQLite)
JSONType = JSON().with_variant(JSONB(), "postgresql")

db = SQLAlchemy()


# ==================================================
# MEMBERS
# ==================================================

class Member(db.Model):

    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("membership_id", name="uq_members_membership_id"),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    membership_id = db.Column(
        db.String(64),
        nullable=False
    )

    last_name = db.Column(
        db.String(150),
        nullable=False
    )

    first_name = db.Column(
        db.String(150),
        nullable=False
    )

    middle_name = db.Column(
        db.String(150)
    )

    org_role = db.Column(
        db.String(100),
        nullable=False,
        default="Member"
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="active"
    )

    # Where notifications (dues reminders, meetings, events, warnings) go.
    email = db.Column(
        db.String(254)
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp()
    )

    users = db.relationship(
        "Profile",
        back_populates="member"
    )

    membership_fees = db.relationship(
        "MembershipFee",
        back_populates="member"
    )

    @property
    def notify_email(self):
        """The member's own email, or else the email of their active login."""
        if self.email:
            return self.email
        for account in self.users or []:
            if account.status == "active" and account.email:
                return account.email
        return None

    @property
    def full_name(self):
        return " ".join(
            part for part in (
                self.first_name,
                self.middle_name,
                self.last_name
            )
            if part
        )


# ==================================================
# PROFILE  (replaces the old "users" table)
#
# One row per login. `id` is the Supabase Auth user id, so there is
# NO password here: Supabase Auth stores and checks passwords.
# This table only holds what the app needs: which member the login
# belongs to, the system role (admin/encoder/viewer), and the status.
# ==================================================
class Profile(db.Model, UserMixin):
    __tablename__ = "profiles"

    # Deliberately no default: the id must come from Supabase Auth so a
    # profile can never exist without a matching login.
    id = db.Column(
        Uuid,
        primary_key=True
    )

    membership_id = db.Column(
        db.String(64),
        db.ForeignKey(
            "members.membership_id",
            ondelete="RESTRICT",
            onupdate="CASCADE"
        ),
        nullable=False,
        index=True
    )

    email = db.Column(
        db.String(150),
        unique=True,
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

    member = db.relationship(
        "Member",
        back_populates="users"
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp()
    )

    @property
    def full_name(self):
        return self.member.full_name if self.member else ""


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

    # Event / project the money was raised for (public)
    activity = db.Column(
        db.String(255)
    )

    # Donation, Registration Fee, Sponsorship, Event Proceeds, ... (public)
    income_type = db.Column(
        db.String(50)
    )

    # Donor / payer name or account (PRIVATE: never published)
    payer = db.Column(
        db.String(255)
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
        db.DateTime(timezone=True),
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

    # Individual / Business / Organization
    sponsor_type = db.Column(
        db.String(50)
    )

    # Event / project the sponsorship was for ("Purpose" in the spreadsheet)
    activity = db.Column(
        db.String(255)
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
        db.DateTime(timezone=True),
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

    membership_id = db.Column(
        db.String(64),
        db.ForeignKey(
            "members.membership_id",
            ondelete="RESTRICT",
            onupdate="CASCADE"
        ),
        nullable=False
    )

    # Dues period: the year the quarter belongs to (may differ from the
    # payment date, e.g. a 2025-Q4 fee paid in 2026)
    year = db.Column(
        db.Integer
    )

    quarter = db.Column(
        db.String(2),
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
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp()
    )

    member = db.relationship(
        "Member",
        back_populates="membership_fees"
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

    # Event / project the expense belongs to (public)
    activity = db.Column(
        db.String(255)
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
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp()
    )

# ==================================================
# DUES  (what each member owes per year + quarter)
#
# Filled from the treasurer's membership-fee sheets (Status / Balance).
# Payments themselves stay in membership_fees; this table records the
# obligation and its status, which is what unpaid-dues analytics need.
# ==================================================

class Due(db.Model):

    __tablename__ = "dues"
    __table_args__ = (
        UniqueConstraint(
            "membership_id", "year", "quarter",
            name="uq_dues_member_period"
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    membership_id = db.Column(
        db.String(64),
        db.ForeignKey(
            "members.membership_id",
            ondelete="RESTRICT",
            onupdate="CASCADE"
        ),
        nullable=False,
        index=True
    )

    year = db.Column(
        db.Integer,
        nullable=False
    )

    quarter = db.Column(
        db.String(2),
        nullable=False
    )

    amount_due = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    amount_paid = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    balance = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    # paid / partial / unpaid / deferred
    status = db.Column(
        db.String(20),
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp()
    )

    member = db.relationship("Member")


# ==================================================
# AUDIT LOG  (append-only history of financial changes)
#
# One row per change: who, when, what, and the record before / after.
# A deleted record's full contents stay here, so it can be restored.
# The database refuses UPDATE and DELETE on this table (see
# migrations/2026-11-25_audit_log.sql), so history cannot be rewritten.
# ==================================================

class AuditLog(db.Model):

    __tablename__ = "audit_log"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    occurred_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp(),
        nullable=False,
        index=True
    )

    # Who did it. user_id is kept even if the account is later removed;
    # the email is a snapshot taken at the time of the change.
    user_id = db.Column(
        Uuid
    )

    user_email = db.Column(
        db.String(150)
    )

    # create / update / delete / import / restore / resync / member_create
    action = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )

    # fundraising / sponsorships / membership_fees / expenses / members / sheet
    entity = db.Column(
        db.String(40),
        nullable=False,
        index=True
    )

    record_id = db.Column(
        db.String(64)
    )

    summary = db.Column(
        db.Text
    )

    before = db.Column(
        JSONType
    )

    after = db.Column(
        JSONType
    )

    # e.g. a restore points at the delete entry it undid
    related_id = db.Column(
        db.Integer
    )


class ExportRequest(db.Model):
    __tablename__ = "export_requests"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        Uuid,
        db.ForeignKey("profiles.id"),
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
        db.String(10),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    admin_id = db.Column(
        Uuid,
        db.ForeignKey("profiles.id"),
        nullable=True
    )

    requested_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp()
    )

    approved_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    rejected_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    requester = db.relationship(
        "Profile",
        foreign_keys=[user_id]
    )

    processed_by = db.relationship(
        "Profile",
        foreign_keys=[admin_id]
    )


# ==================================================
# EVENTS  (meetings and events members are reminded about)
# ==================================================

class Event(db.Model):

    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="meeting")
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    location = db.Column(db.String(255))
    description = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="scheduled")
    created_by = db.Column(db.String(150))
    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp()
    )


# ==================================================
# NOTIFICATION LOG  (one row per email the website tried to send)
# ==================================================

class NotificationLog(db.Model):

    __tablename__ = "notification_log"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp(),
        index=True
    )
    kind = db.Column(db.String(30), nullable=False)
    batch_id = db.Column(db.String(40))
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text)
    recipient_email = db.Column(db.String(254))
    membership_id = db.Column(db.String(64))
    recipient_name = db.Column(db.String(255))
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("events.id", ondelete="SET NULL")
    )
    status = db.Column(db.String(20), nullable=False)
    error = db.Column(db.Text)
    sent_by = db.Column(db.String(150))
    dedupe_key = db.Column(db.String(120), unique=True)


# ==================================================
# PASSWORD RESET TOKENS  ("Forgot password" links; only a hash is stored)
# ==================================================

class PasswordResetToken(db.Model):

    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(
        Uuid,
        db.ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp()
    )
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))
    requested_ip = db.Column(db.String(64))
