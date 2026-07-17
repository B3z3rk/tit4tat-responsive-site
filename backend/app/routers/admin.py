import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..constants import ADMIN_TIER_ROLES, ROLE_ORDER
from ..database import get_db
from ..deps import require_role
from ..email_utils import send_email
from ..security import hash_password
from .reports import _to_out as _report_to_out

router = APIRouter(tags=["admin"], dependencies=[Depends(require_role("HOA"))])

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent.parent

DOCUMENT_PATH_COLUMNS = {
    "reference": lambda u: u.reference_path,
    "id": lambda u: u.id_path,
    "bill": lambda u: u.utility_bill_path,
}


def _assert_can_manage_admin_tier(actor: models.User, *roles: str) -> None:
    """Only a Super Admin may assign an Admin-tier role, or act on an account
    that already holds one — a regular HOA cannot create, demote, suspend,
    or reset the password of another HOA/Super Admin."""
    if actor.role == "SUPER_ADMIN":
        return
    if any(role in ADMIN_TIER_ROLES for role in roles):
        raise HTTPException(status_code=403, detail="Only a Super Admin can manage Admin-tier accounts")


def _log(
    db: DbSession, actor: models.User, action: str,
    target: models.User | None = None, detail: str | None = None,
) -> None:
    db.add(models.AuditLogEntry(
        actor_id=actor.id, actor_name=actor.name, action=action,
        target_user_id=target.id if target else None,
        target_name=target.name if target else None,
        detail=detail,
    ))
    db.commit()


@router.get("/overview", response_model=schemas.AdminOverviewOut)
def overview(db: DbSession = Depends(get_db)):
    pending_approvals = db.query(models.User).filter(models.User.approval_status == "pending").count()
    total_members = db.query(models.User).filter(models.User.approval_status == "approved").count()
    total_activities = db.query(models.Activity).count()
    open_reports = db.query(models.Report).filter(models.Report.status != "Resolved").count()
    urgent_reports = (
        db.query(models.Report)
        .filter(or_(models.Report.status == "Urgent", models.Report.priority == "Urgent"))
        .count()
    )

    recent_signups = (
        db.query(models.User)
        .order_by(models.User.created_at.desc())
        .limit(5)
        .all()
    )
    recent_reports = (
        db.query(models.Report)
        .order_by(models.Report.created_at.desc())
        .limit(5)
        .all()
    )

    return schemas.AdminOverviewOut(
        pendingApprovals=pending_approvals,
        totalMembers=total_members,
        totalActivities=total_activities,
        openReports=open_reports,
        urgentReports=urgent_reports,
        recentSignups=[
            schemas.RecentSignupOut(
                id=u.id, name=u.name, email=u.email,
                approvalStatus=u.approval_status, createdAt=u.created_at,
            )
            for u in recent_signups
        ],
        recentReports=[_report_to_out(r) for r in recent_reports],
    )


@router.get("/users/pending", response_model=list[schemas.PendingUserOut])
def list_pending(db: DbSession = Depends(get_db)):
    users = (
        db.query(models.User)
        .filter(models.User.approval_status == "pending")
        .order_by(models.User.created_at)
        .all()
    )
    return [
        schemas.PendingUserOut(
            id=u.id, name=u.name, email=u.email, createdAt=u.created_at,
            communityArea=u.community_area, referenceName=u.reference_name,
            referenceVerified=u.reference_user_id is not None,
            referenceUploaded=u.reference_uploaded, idUploaded=u.id_uploaded,
            billUploaded=u.utility_bill_uploaded,
            idFormatVerified=u.id_format_verified,
            billFormatVerified=u.utility_bill_format_verified,
            billIssuerDetected=u.utility_bill_issuer_detected,
            nameMatchesId=u.name_matches_id,
        )
        for u in users
    ]


@router.get("/users/{user_id}/documents/{doc_type}")
def view_document(
    user_id: int,
    doc_type: str,
    db: DbSession = Depends(get_db),
    actor: models.User = Depends(require_role("SUPER_ADMIN")),
):
    """Streams a submitted verification document. Super Admin only — this is
    the ONLY way to reach these files; they're excluded from the static
    mount (see BLOCKED_STATIC_PREFIXES in main.py)."""
    getter = DOCUMENT_PATH_COLUMNS.get(doc_type)
    if not getter:
        raise HTTPException(status_code=404, detail="Unknown document type")

    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    relative_path = getter(user)
    if not relative_path:
        raise HTTPException(status_code=404, detail="No document on file for this user")

    file_path = FRONTEND_DIR / relative_path
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Document file is missing on disk")

    _log(db, actor, "view_document", user, detail=doc_type)
    return FileResponse(file_path)


@router.post("/users/{user_id}/approve", response_model=schemas.UserOut)
def approve_user(
    user_id: int,
    payload: schemas.ApproveIn,
    request: Request,
    db: DbSession = Depends(get_db),
    admin: models.User = Depends(require_role("HOA")),
):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _assert_can_manage_admin_tier(admin, payload.role or "REGULAR_MEMBER")

    user.approval_status = "approved"
    user.role = payload.role or "REGULAR_MEMBER"
    user.approved_by_id = admin.id
    user.approved_at = datetime.utcnow()
    # No password is assigned here at all - the account is unreachable by
    # password until the applicant uses their one-time emailed setup link to
    # pick their own, so there's never a shared/known credential for the HOA
    # to relay (or for anyone else to intercept) in the first place.
    user.password_hash = hash_password(secrets.token_urlsafe(24))
    # Every newly-approved account goes through MFA setup on its first real
    # sign-in, regardless of role - not just Admin-tier accounts (which
    # already require it unconditionally, see auth.login()).
    user.mfa_required = True
    db.commit()
    db.refresh(user)

    setup_token = secrets.token_urlsafe(32)
    db.add(models.AccountSetupToken(
        token=setup_token, user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    ))
    db.commit()

    # Prefer PUBLIC_BASE_URL (the LAN address start-server.ps1 detects and
    # exports) over request.base_url - the request came from the HOA's own
    # browser, which might be on localhost/127.0.0.1 even when the actual
    # applicant is on a different device that can only reach the LAN IP.
    base_url = os.getenv("PUBLIC_BASE_URL") or str(request.base_url).rstrip("/")
    setup_url = f"{base_url.rstrip('/')}/sects.html?setupToken={setup_token}"
    email_sent = send_email(
        to=user.email,
        subject="Your Tit4Tat account has been approved",
        body=(
            f"Hi {user.name},\n\n"
            "Your Tit4Tat account has been approved. Set your password to get started:\n\n"
            f"{setup_url}\n\n"
            "This link works once and expires in 24 hours.\n"
        ),
    )

    _log(db, admin, "approve_user", user, detail=f"role={user.role}")
    return schemas.UserOut(
        id=user.id, name=user.name, email=user.email, role=user.role,
        approvalStatus=user.approval_status, profile=user.profile,
        setupEmailSent=email_sent,
    )


@router.post("/users/{user_id}/reject", status_code=204)
def reject_user(
    user_id: int,
    payload: schemas.RejectIn,
    db: DbSession = Depends(get_db),
    actor: models.User = Depends(require_role("HOA")),
):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.approval_status = "rejected"
    user.rejection_reason = payload.reason
    db.commit()
    _log(db, actor, "reject_user", user, detail=payload.reason)

    # Without this, a rejected applicant has no way to find out - login
    # deliberately gives the same generic "invalid credentials" message
    # regardless of approval status, so email is the only channel. Their
    # email stays free to register() again afterward (see the "rejected
    # accounts can resubmit" handling there), so this also tells them how.
    send_email(
        to=user.email,
        subject="Your Tit4Tat registration",
        body=(
            f"Hi {user.name},\n\n"
            "Your Tit4Tat registration could not be approved at this time.\n\n"
            f"Reason: {payload.reason or 'No specific reason was provided.'}\n\n"
            "You're welcome to submit a corrected registration at any time using the "
            f"same email address ({user.email}) with the corrected information or documents.\n\n"
            "If you have questions, please contact your community's HOA directly.\n"
        ),
    )


@router.get("/users", response_model=list[schemas.AdminUserOut])
def list_all_users(db: DbSession = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.name).all()
    return [
        schemas.AdminUserOut(
            id=u.id, name=u.name, email=u.email, role=u.role,
            approvalStatus=u.approval_status, createdAt=u.created_at,
        )
        for u in users
    ]


@router.post("/users/{user_id}/reset-password", response_model=schemas.ResetPasswordOut)
def reset_password(
    user_id: int,
    payload: schemas.ResetPasswordIn,
    db: DbSession = Depends(get_db),
    actor: models.User = Depends(require_role("HOA")),
):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _assert_can_manage_admin_tier(actor, user.role)

    generated = None
    new_password = payload.newPassword
    if not new_password:
        generated = secrets.token_urlsafe(9)
        new_password = generated

    user.password_hash = hash_password(new_password)
    # An HOA-known password (generated or hand-picked) is a temporary one by
    # definition - force it to be replaced with something only the account
    # holder knows before they can do anything else, same as approval.
    user.must_change_password = True
    db.commit()

    # existing sessions for this user are invalidated so a reset password takes effect immediately
    db.query(models.Session).filter(models.Session.user_id == user_id).delete()
    db.commit()
    _log(db, actor, "reset_password", user)  # never log the actual password

    return schemas.ResetPasswordOut(temporaryPassword=generated)


@router.post("/users/{user_id}/role", response_model=schemas.UserOut)
def change_role(
    user_id: int,
    payload: schemas.RoleChangeIn,
    db: DbSession = Depends(get_db),
    # Super Admin only — a regular HOA can no longer change anyone's role.
    actor: models.User = Depends(require_role("SUPER_ADMIN")),
):
    if payload.role not in ROLE_ORDER:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ROLE_ORDER)}")

    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    previous_role = user.role
    user.role = payload.role
    db.commit()
    db.refresh(user)
    _log(db, actor, "change_role", user, detail=f"{previous_role} -> {user.role}")
    return schemas.UserOut(
        id=user.id, name=user.name, email=user.email, role=user.role,
        approvalStatus=user.approval_status, profile=user.profile,
    )


@router.post("/users/{user_id}/suspend", response_model=schemas.UserOut)
def suspend_user(
    user_id: int,
    db: DbSession = Depends(get_db),
    # Super Admin only — a regular HOA can no longer suspend accounts.
    actor: models.User = Depends(require_role("SUPER_ADMIN")),
):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.approval_status = "suspended"
    db.commit()

    # a suspended account's active sessions are revoked immediately
    db.query(models.Session).filter(models.Session.user_id == user_id).delete()
    db.commit()
    db.refresh(user)
    _log(db, actor, "suspend_user", user)
    return schemas.UserOut(
        id=user.id, name=user.name, email=user.email, role=user.role,
        approvalStatus=user.approval_status, profile=user.profile,
    )


@router.post("/users/{user_id}/reactivate", response_model=schemas.UserOut)
def reactivate_user(
    user_id: int,
    db: DbSession = Depends(get_db),
    actor: models.User = Depends(require_role("HOA")),
):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _assert_can_manage_admin_tier(actor, user.role)

    user.approval_status = "approved"
    db.commit()
    db.refresh(user)
    _log(db, actor, "reactivate_user", user)
    return schemas.UserOut(
        id=user.id, name=user.name, email=user.email, role=user.role,
        approvalStatus=user.approval_status, profile=user.profile,
    )


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: DbSession = Depends(get_db),
    actor: models.User = Depends(require_role("SUPER_ADMIN")),
):
    """Permanently removes an account - unlike suspend, this cannot be undone.
    Content that can't exist without an owner (reports, messages, activity
    participation, emergency calls, announcements) is removed along with it;
    references from other rows that are merely informational (audit log,
    who approved/reset someone, who left a community note) are kept but
    detached (set to NULL) so that history survives the account itself."""
    if user_id == actor.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    name, email = user.name, user.email

    # Detach references from surviving rows rather than deleting them.
    db.query(models.User).filter(models.User.approved_by_id == user_id).update({"approved_by_id": None})
    db.query(models.User).filter(models.User.reference_user_id == user_id).update({"reference_user_id": None})
    db.query(models.AuditLogEntry).filter(models.AuditLogEntry.actor_id == user_id).update({"actor_id": None})
    db.query(models.AuditLogEntry).filter(models.AuditLogEntry.target_user_id == user_id).update({"target_user_id": None})
    db.query(models.MemberNote).filter(models.MemberNote.created_by_id == user_id).update({"created_by_id": None})
    db.query(models.ReportTimelineEvent).filter(models.ReportTimelineEvent.created_by_id == user_id).update({"created_by_id": None})
    db.query(models.Activity).filter(models.Activity.created_by_id == user_id).update({"created_by_id": None})

    # This account's own ephemeral/personal state.
    db.query(models.Session).filter(models.Session.user_id == user_id).delete()
    db.query(models.MfaChallenge).filter(models.MfaChallenge.user_id == user_id).delete()
    db.query(models.AccountSetupToken).filter(models.AccountSetupToken.user_id == user_id).delete()
    db.query(models.MemberNote).filter(models.MemberNote.user_id == user_id).delete()

    # Content with a NOT NULL owner column - can't be detached, so it goes
    # with the account.
    db.query(models.ActivityParticipant).filter(models.ActivityParticipant.user_id == user_id).delete()
    db.query(models.EmergencyCall).filter(models.EmergencyCall.user_id == user_id).delete()
    db.query(models.Announcement).filter(models.Announcement.created_by_id == user_id).delete()
    db.query(models.Message).filter(
        or_(models.Message.sender_id == user_id, models.Message.recipient_id == user_id)
    ).delete()

    report_ids = [r.id for r in db.query(models.Report.id).filter(models.Report.submitted_by_id == user_id)]
    if report_ids:
        db.query(models.ReportTimelineEvent).filter(models.ReportTimelineEvent.report_id.in_(report_ids)).delete(synchronize_session=False)
        db.query(models.Report).filter(models.Report.id.in_(report_ids)).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
    _log(db, actor, "delete_user", detail=f"{name} <{email}>")


@router.get("/audit-log", response_model=list[schemas.AuditLogEntryOut])
def list_audit_log(db: DbSession = Depends(get_db), actor: models.User = Depends(require_role("SUPER_ADMIN"))):
    entries = (
        db.query(models.AuditLogEntry)
        .order_by(models.AuditLogEntry.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        schemas.AuditLogEntryOut(
            id=e.id, actorName=e.actor_name, action=e.action,
            targetName=e.target_name, detail=e.detail, createdAt=e.created_at,
        )
        for e in entries
    ]
