import secrets
from datetime import datetime, timedelta
from pathlib import Path

import pyotp
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import EmailStr
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..constants import ADMIN_TIER_ROLES
from ..database import get_db
from ..deps import get_current_user
from ..security import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    create_session,
    generate_member_code,
    hash_password,
    set_session_cookie,
    verify_password,
)

router = APIRouter(tags=["auth"])

MFA_CHALLENGE_TTL = timedelta(minutes=10)

# Verification documents live under uploads/verification/{user_id}/ — same
# repo-root convention as uploads/avatars and uploads/activities, but this
# specific subpath is blocked from the static mount (see main.py) since these
# are Super-Admin-only, unlike public avatars/activity covers.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
VERIFICATION_DIR = FRONTEND_DIR / "uploads" / "verification"

ALLOWED_DOC_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
MAX_DOC_BYTES = 5 * 1024 * 1024  # 5MB


def _issue_session(db: DbSession, response: Response, user: models.User) -> schemas.UserOut:
    session = create_session(db, user)
    set_session_cookie(response, session.token, user)
    return _to_user_out(user)


async def _save_verification_doc(user_id: int, doc_name: str, file: UploadFile | None) -> tuple[bool, str | None]:
    if not file or not file.filename:
        return False, None

    ext = ALLOWED_DOC_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type for {doc_name}. Use JPEG, PNG, GIF, WEBP, or PDF.",
        )

    content = await file.read()
    if not content:
        return False, None
    if len(content) > MAX_DOC_BYTES:
        raise HTTPException(status_code=400, detail=f"{doc_name} file is too large (max 5MB).")

    user_dir = VERIFICATION_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    dest = user_dir / f"{doc_name}{ext}"
    dest.write_bytes(content)
    return True, str(dest.relative_to(FRONTEND_DIR))


@router.post("/register", response_model=schemas.UserOut, status_code=201)
async def register(
    db: DbSession = Depends(get_db),
    name: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(None),
    phone: str = Form(None),
    communityArea: str = Form(None),
    referenceName: str = Form(None),
    referenceUserId: int = Form(None),
    referenceFile: UploadFile = File(None),
    idFile: UploadFile = File(None),
    billFile: UploadFile = File(None),
):
    email_normalized = email.lower()
    existing = db.query(models.User).filter(models.User.email == email_normalized).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")

    # A scanned QR reference must point at a real, approved member — if it
    # doesn't, fall back to whatever manual reference name was typed instead
    # of failing the whole registration outright.
    reference_user = None
    if referenceUserId is not None:
        candidate = db.get(models.User, referenceUserId)
        if candidate and candidate.approval_status == "approved":
            reference_user = candidate
            referenceName = candidate.name

    user = models.User(
        name=name,
        email=email_normalized,
        phone=phone,
        password_hash=hash_password(password or "welcome123"),
        role="REGULAR_MEMBER",
        approval_status="pending",
        community_area=communityArea,
        reference_name=referenceName,
        reference_user_id=reference_user.id if reference_user else None,
        profile="New community member",
        # seed directory fields from what registration already collects, so the
        # member shows up in the directory with something more than blanks
        # the moment an admin approves them
        category="General Member",
        location=communityArea,
        member_code=generate_member_code(db),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Documents are optional at this layer (a missing/invalid one just leaves
    # that requirement unmet, shown to HOA/Super Admin in the approval queue)
    # rather than blocking account creation outright.
    user.reference_uploaded, user.reference_path = await _save_verification_doc(user.id, "reference", referenceFile)
    user.id_uploaded, user.id_path = await _save_verification_doc(user.id, "id", idFile)
    user.utility_bill_uploaded, user.utility_bill_path = await _save_verification_doc(user.id, "bill", billFile)
    db.commit()
    db.refresh(user)

    return _to_user_out(user)


@router.post("/login")
def login(payload: schemas.LoginIn, response: Response, db: DbSession = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user.approval_status == "suspended":
        raise HTTPException(status_code=403, detail="Your account has been suspended by an admin.")
    if user.approval_status != "approved":
        raise HTTPException(status_code=403, detail="Your account is pending admin approval.")

    # Admin-tier accounts require a second factor. Password-correct isn't
    # enough on its own to get a session — a pending challenge is issued
    # instead, and the real session/cookie only appears after the matching
    # /mfa/verify-* call succeeds.
    if user.role in ADMIN_TIER_ROLES:
        if user.mfa_enabled:
            challenge = models.MfaChallenge(
                token=secrets.token_urlsafe(24), user_id=user.id, purpose="login",
                expires_at=datetime.utcnow() + MFA_CHALLENGE_TTL,
            )
            db.add(challenge)
            db.commit()
            return schemas.MfaChallengeOut(mfaRequired=True, challengeToken=challenge.token)

        # Not yet enrolled — issue a fresh secret and require it to be
        # confirmed with one valid code before it's ever active.
        secret = pyotp.random_base32()
        challenge = models.MfaChallenge(
            token=secrets.token_urlsafe(24), user_id=user.id, purpose="enroll",
            pending_secret=secret, expires_at=datetime.utcnow() + MFA_CHALLENGE_TTL,
        )
        db.add(challenge)
        db.commit()
        otpauth_url = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Tit4Tat")
        return schemas.MfaChallengeOut(
            mfaSetupRequired=True, challengeToken=challenge.token, secret=secret, otpauthUrl=otpauth_url,
        )

    return _issue_session(db, response, user)


@router.post("/mfa/verify-enroll", response_model=schemas.UserOut)
def verify_mfa_enroll(payload: schemas.MfaVerifyIn, response: Response, db: DbSession = Depends(get_db)):
    challenge = db.get(models.MfaChallenge, payload.challengeToken)
    if not challenge or challenge.purpose != "enroll" or challenge.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This setup session has expired. Please sign in again.")

    if not pyotp.TOTP(challenge.pending_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=401, detail="Incorrect authentication code.")

    user = db.get(models.User, challenge.user_id)
    user.totp_secret = challenge.pending_secret
    user.mfa_enabled = True
    db.delete(challenge)
    db.commit()
    db.refresh(user)
    return _issue_session(db, response, user)


@router.post("/mfa/verify-login", response_model=schemas.UserOut)
def verify_mfa_login(payload: schemas.MfaVerifyIn, response: Response, db: DbSession = Depends(get_db)):
    challenge = db.get(models.MfaChallenge, payload.challengeToken)
    if not challenge or challenge.purpose != "login" or challenge.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This sign-in attempt has expired. Please sign in again.")

    user = db.get(models.User, challenge.user_id)
    if not pyotp.TOTP(user.totp_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=401, detail="Incorrect authentication code.")

    db.delete(challenge)
    db.commit()
    return _issue_session(db, response, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DbSession = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        session = db.get(models.Session, token)
        if session:
            db.delete(session)
            db.commit()
    clear_session_cookie(response)
    return Response(status_code=204)


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return _to_user_out(user)


@router.post("/change-password", status_code=204)
def change_password(
    payload: schemas.ChangePasswordIn,
    db: DbSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not verify_password(payload.currentPassword, user.password_hash):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")
    if len(payload.newPassword) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    user.password_hash = hash_password(payload.newPassword)
    # invalidate every session (including this one) so the new password takes
    # effect immediately everywhere, matching the admin-triggered reset flow
    db.query(models.Session).filter(models.Session.user_id == user.id).delete()
    db.commit()
    return Response(status_code=204)


def _to_user_out(user: models.User) -> schemas.UserOut:
    return schemas.UserOut(
        id=user.id, name=user.name, email=user.email, role=user.role,
        approvalStatus=user.approval_status, profile=user.profile,
        avatarUrl=user.avatar_path,
    )
