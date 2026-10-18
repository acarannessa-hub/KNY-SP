from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, Uuid

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

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp()
    )

    users = db.relationship(
        "Profile",
        back_populates="member"
    )

    

    attendance_records = db.relationship(
        "Attendance",
        back_populates="member"
    )

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
# NOTE: fundraising, sponsorships, membership fees and expenses are NOT
# database tables any more. They live in the private Google Sheet and are
# handled by financial_store.py / google_sheets.py.
# ==================================================


# ==================================================
# ATTENDANCE
# ==================================================

class Attendance(db.Model):

    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint(
            "membership_id",
            "attendance_date",
            name="uq_attendance_member_date"
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

    attendance_date = db.Column(
        db.Date,
        nullable=False,
        index=True
    )

    attendance_status = db.Column(
        db.String(20),
        nullable=False
    )

    time_in = db.Column(
        db.Time
    )

    time_out = db.Column(
        db.Time
    )

    remarks = db.Column(
        db.Text
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp()
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp()
    )

    member = db.relationship(
        "Member",
        back_populates="attendance_records"
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