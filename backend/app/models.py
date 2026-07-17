from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    phone = Column(String, nullable=True)
    # Explicit opt-in for real (Twilio-bridged) tap-to-call, kept separate
    # from just "has a phone number" - several unrelated test/registration
    # accounts already have a phone on file, and only accounts we deliberately
    # flag should ever trigger an actual outbound call. See
    # telephony_utils.place_bridge_call and routers/emergency.py.
    real_call_enabled = Column(Boolean, default=False)
    password_hash = Column(String, nullable=False)
    # set whenever HOA/Super Admin assigns a password the member didn't choose
    # themselves (approval, admin-triggered reset) — forces a change on next
    # login before the rest of the app is reachable, see get_current_user.
    must_change_password = Column(Boolean, default=False)
    role = Column(String, nullable=False, default="REGULAR_MEMBER")  # HOA | MEMBER | REGULAR_MEMBER
    approval_status = Column(String, nullable=False, default="pending")  # pending | approved | rejected
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # registration verification documents — path is relative to the repo root
    # (e.g. "uploads/verification/7/id.jpg"), None if nothing was uploaded.
    # Only ever served through the Super-Admin-only document endpoint, never
    # as a static file (see BLOCKED_STATIC_PREFIXES in main.py).
    community_area = Column(String, nullable=True)
    reference_name = Column(String, nullable=True)
    # set only when the reference was a scanned member QR code (not a manual
    # typed name) — a real, verified link to an existing approved member
    reference_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reference_uploaded = Column(Boolean, default=False)
    reference_path = Column(String, nullable=True)
    id_uploaded = Column(Boolean, default=False)
    id_path = Column(String, nullable=True)
    # OCR-based soft check against known ID keyword patterns - NULL means
    # verification wasn't available (Tesseract not installed) or the file
    # predates this check, not that it failed. See document_verification.py.
    id_format_verified = Column(Boolean, nullable=True)
    # OCR-based soft check that the typed name appears on the uploaded ID -
    # same NULL-means-unavailable convention as id_format_verified
    name_matches_id = Column(Boolean, nullable=True)
    utility_bill_uploaded = Column(Boolean, default=False)
    utility_bill_path = Column(String, nullable=True)
    utility_bill_format_verified = Column(Boolean, nullable=True)
    # which known issuer (Digicel/FLOW/JPS/National Water Commission) the
    # bill's OCR'd text matched, if any
    utility_bill_issuer_detected = Column(String, nullable=True)

    # directory profile fields
    category = Column(String, nullable=True)
    specialty = Column(String, nullable=True)
    location = Column(String, nullable=True)
    availability = Column(String, nullable=True)
    presence_status = Column(String, default="Offline")  # Online | Offline
    business = Column(Boolean, default=False)
    business_name = Column(String, nullable=True)
    business_description = Column(Text, nullable=True)
    is_essential_worker = Column(Boolean, default=False)
    essential_worker_type = Column(String, nullable=True)
    essential_worker_registration_number = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    profile = Column(Text, nullable=True)
    avatar_path = Column(String, nullable=True)

    # short unique code shown as a QR on this member's own profile — anyone
    # can scan it to be vouched for as a reference during registration
    member_code = Column(String, unique=True, nullable=True)

    # TOTP-based MFA, always required at login for Admin-tier accounts
    # (HOA/SUPER_ADMIN); mfa_required additionally opts in any other specific
    # account regardless of role (e.g. for testing) without changing their
    # permissions. mfa_enabled just tracks whether enrollment is complete.
    totp_secret = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    mfa_required = Column(Boolean, default=False)

    notes = relationship("MemberNote", foreign_keys="MemberNote.user_id", back_populates="user")


class MemberNote(Base):
    __tablename__ = "member_notes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note = Column(Text, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], back_populates="notes")


class Session(Base):
    __tablename__ = "sessions"

    token = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class MfaChallenge(Base):
    """A short-lived, single-use pending token issued between password
    verification and TOTP verification during Admin-tier login, so the real
    session cookie is only ever set after both factors succeed."""

    __tablename__ = "mfa_challenges"

    token = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    purpose = Column(String, nullable=False)  # "enroll" | "login"
    # only set for "enroll" — the not-yet-confirmed secret being set up
    pending_secret = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class AccountSetupToken(Base):
    """A single-use, emailed link that lets a newly-approved applicant set
    their own password directly - no temporary password is ever assigned,
    shown to the HOA, or transmitted anywhere, so there's nothing to relay
    or intercept in the first place."""

    __tablename__ = "account_setup_tokens"

    token = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_name = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    target_name = Column(String, nullable=True)
    detail = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)
    event_date = Column(Date, nullable=False)
    time_label = Column(String, nullable=False)
    location = Column(String, nullable=False)
    organizer = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)
    base_participants = Column(Integer, default=0)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ActivityParticipant(Base):
    __tablename__ = "activity_participants"

    id = Column(Integer, primary_key=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("activity_id", "user_id", name="uq_activity_user"),)


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    status = Column(String, nullable=False)
    location = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    submitted_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # optional photo/video evidence — path is public (like avatars/activity
    # covers), served directly from the static mount, no Super-Admin gate
    media_path = Column(String, nullable=True)
    media_type = Column(String, nullable=True)  # "image" | "video"

    timeline = relationship(
        "ReportTimelineEvent", back_populates="report", order_by="ReportTimelineEvent.created_at"
    )
    submitted_by = relationship("User", foreign_keys=[submitted_by_id])


class ReportTimelineEvent(Base):
    __tablename__ = "report_timeline_events"

    id = Column(Integer, primary_key=True)
    report_id = Column(String, ForeignKey("reports.id"), nullable=False)
    note = Column(String, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    report = relationship("Report", back_populates="timeline")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime, nullable=True)


class EmergencyCall(Base):
    __tablename__ = "emergency_calls"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_type = Column(String, nullable=False)
    target_label = Column(String, nullable=False)
    # only set for "member" calls - lets the backend look up the target's
    # phone number to place a real bridge call (see routers/emergency.py)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    created_by = relationship("User", foreign_keys=[created_by_id])
