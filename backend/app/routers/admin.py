import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..constants import ADMIN_TIER_ROLES, ROLE_ORDER
from ..database import get_db
from ..deps import require_role
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
    db.commit()
    db.refresh(user)
    _log(db, admin, "approve_user", user, detail=f"role={user.role}")
    return schemas.UserOut(
        id=user.id, name=user.name, email=user.email, role=user.role,
        approvalStatus=user.approval_status, profile=user.profile,
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
    actor: models.User = Depends(require_role("HOA")),
):
    if payload.role not in ROLE_ORDER:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ROLE_ORDER)}")

    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _assert_can_manage_admin_tier(actor, user.role, payload.role)

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
    actor: models.User = Depends(require_role("HOA")),
):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _assert_can_manage_admin_tier(actor, user.role)

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
