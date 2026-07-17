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
from ..document_verification import check_id_document, check_name_matches_id, check_utility_bill
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

# In-memory login rate limiting, keyed by email and by IP separately so a
# lockout on one axis can't be dodged by varying the other. Fine for a
# single-process deployment; would need a shared store (e.g. Redis) behind
# multiple workers/instances.
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW = timedelta(minutes=15)
_login_attempts: dict[str, list[datetime]] = {}


def _rate_limit_key_blocked(key: str) -> bool:
    now = datetime.utcnow()
    attempts = [t for t in _login_attempts.get(key, []) if now - t < LOGIN_ATTEMPT_WINDOW]
    _login_attempts[key] = attempts
    return len(attempts) >= LOGIN_ATTEMPT_LIMIT


def _record_failed_login(*keys: str) -> None:
    now = datetime.utcnow()
    for key in keys:
        _login_attempts.setdefault(key, []).append(now)


def _clear_failed_login(*keys: str) -> None:
    for key in keys:
        _login_attempts.pop(key, None)

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


def _detect_file_signature(content: bytes) -> str | None:
    """Identifies a file's real type from its own bytes (its "magic number"),
    never from the client-supplied filename or Content-Type header - both are
    just claims the client makes and are trivial to spoof (renaming a
    malicious file to "id.jpg" and setting Content-Type: image/jpeg would
    sail through a check based on either of those alone). Returns None if
    the content doesn't match any format we accept, regardless of what the
    upload claimed to be."""
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content[:5] == b"%PDF-":
        return "application/pdf"
    return None


def _issue_session(db: DbSession, response: Response, user: models.User) -> schemas.UserOut:
    session = create_session(db, user)
    set_session_cookie(response, session.token, user)
    return _to_user_out(user)


async def _read_verification_doc(
    label: str, file: UploadFile | None, *, required: bool,
) -> tuple[bool, bytes | None, str | None]:
    """Reads and validates an uploaded document's actual bytes. Doesn't write
    anything to disk yet - the destination path is keyed by the new user's
    id, which doesn't exist until after the account row is created, and a
    rejected upload shouldn't leave a half-created pending registration
    behind."""
    if not file or not file.filename:
        if required:
            raise HTTPException(status_code=400, detail=f"Please upload your {label}.")
        return False, None, None

    content = await file.read()
    if not content:
        if required:
            raise HTTPException(status_code=400, detail=f"Please upload your {label}.")
        return False, None, None
    if len(content) > MAX_DOC_BYTES:
        raise HTTPException(status_code=400, detail=f"Your {label} file is too large (max 5MB).")

    # The actual bytes have to match a known real format - not just whatever
    # content-type the upload claims to be. See _detect_file_signature.
    ext = ALLOWED_DOC_TYPES.get(_detect_file_signature(content))
    if not ext:
        raise HTTPException(
            status_code=400,
            detail=f"Your {label} doesn't look like a real JPEG, PNG, GIF, WEBP, or PDF file.",
        )
    return True, content, ext


def _write_verification_doc(user_id: int, doc_name: str, content: bytes, ext: str) -> str:
    user_dir = VERIFICATION_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    # Clear out any previous upload for this doc under a different extension -
    # relevant on a resubmission after rejection, where the corrected file
    # might not be the same format as the one it's replacing.
    for old_ext in ALLOWED_DOC_TYPES.values():
        old_path = user_dir / f"{doc_name}{old_ext}"
        if old_path.exists():
            old_path.unlink()
    dest = user_dir / f"{doc_name}{ext}"
    dest.write_bytes(content)
    return str(dest.relative_to(FRONTEND_DIR))


@router.post("/check-name-match")
async def check_name_match(name: str = Form(...), idFile: UploadFile = File(...)):
    """Deliberately unauthenticated - runs live during registration, before
    any account exists, purely to give the applicant an inline heads-up.
    Never blocks anything here; the same check also runs (and is stored,
    see register() below) at actual submission time for the HOA's review -
    this is just an early, non-authoritative preview of that same result."""
    content = await idFile.read()
    if not content:
        return {"available": False, "matches": None}
    matches = check_name_matches_id(content, name)
    return {"available": matches is not None, "matches": matches}


@router.post("/register", response_model=schemas.UserOut, status_code=201)
async def register(
    db: DbSession = Depends(get_db),
    name: str = Form(...),
    email: EmailStr = Form(...),
    phone: str = Form(None),
    communityArea: str = Form(None),
    referenceName: str = Form(None),
    referenceUserId: int = Form(None),
    referenceFile: UploadFile = File(None),
    idFile: UploadFile = File(...),
    billFile: UploadFile = File(...),
):
    email_normalized = email.lower()
    existing = db.query(models.User).filter(models.User.email == email_normalized).first()
    # A previously-rejected applicant can resubmit a corrected registration
    # under the same email (see admin.reject_user, which tells them this) -
    # updates their existing record back to "pending" rather than creating a
    # duplicate. Anyone else with that email (pending/approved/suspended)
    # still blocks a second registration as before.
    if existing and existing.approval_status != "rejected":
        raise HTTPException(status_code=409, detail="An account with that email already exists.")

    # ID and utility bill are mandatory - reference stays optional (a
    # reference can also be provided by scanning another member's QR code
    # instead of an upload, see referenceUserId below). Validated up front,
    # before any account row exists, so a rejected upload never leaves a
    # half-created pending registration behind.
    reference_uploaded, reference_content, reference_ext = await _read_verification_doc(
        "reference document", referenceFile, required=False,
    )
    id_uploaded, id_content, id_ext = await _read_verification_doc(
        "ID", idFile, required=True,
    )
    bill_uploaded, bill_content, bill_ext = await _read_verification_doc(
        "utility bill", billFile, required=True,
    )

    # A scanned QR reference must point at a real, approved member — if it
    # doesn't, fall back to whatever manual reference name was typed instead
    # of failing the whole registration outright.
    reference_user = None
    if referenceUserId is not None:
        candidate = db.get(models.User, referenceUserId)
        if candidate and candidate.approval_status == "approved":
            reference_user = candidate
            referenceName = candidate.name

    if existing:
        # Resubmission after rejection - update the existing record rather
        # than creating a duplicate, so its id/member_code/audit history
        # carry over instead of starting over from a blank slate.
        user = existing
        user.name = name
        user.phone = phone
        user.approval_status = "pending"
        user.rejection_reason = None
        user.community_area = communityArea
        user.reference_name = referenceName
        user.reference_user_id = reference_user.id if reference_user else None
        user.category = "General Member"
        user.location = communityArea
        db.commit()
        db.refresh(user)
    else:
        # No real password exists yet at this stage - the account can't log in
        # until an HOA approves it, and approval always assigns a fresh random
        # temporary password (see admin.approve_user), so this hash is never
        # actually used to authenticate anyone.
        user = models.User(
            name=name,
            email=email_normalized,
            phone=phone,
            password_hash=hash_password(secrets.token_urlsafe(24)),
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

    if reference_uploaded:
        user.reference_uploaded = True
        user.reference_path = _write_verification_doc(user.id, "reference", reference_content, reference_ext)
    user.id_uploaded = True
    user.id_path = _write_verification_doc(user.id, "id", id_content, id_ext)
    user.id_format_verified = check_id_document(id_content)
    user.name_matches_id = check_name_matches_id(id_content, name)

    user.utility_bill_uploaded = True
    user.utility_bill_path = _write_verification_doc(user.id, "bill", bill_content, bill_ext)
    bill_check = check_utility_bill(bill_content)
    if bill_check is not None:
        user.utility_bill_format_verified, user.utility_bill_issuer_detected = bill_check

    db.commit()
    db.refresh(user)

    return _to_user_out(user)


@router.post("/setup-password", status_code=204)
def setup_password(payload: schemas.SetupPasswordIn, db: DbSession = Depends(get_db)):
    """Deliberately unauthenticated - this is what an applicant's one-time
    emailed setup link (see admin.approve_user) hits to pick their own
    password. The token itself, not a session, is the proof of identity."""
    setup_token = db.get(models.AccountSetupToken, payload.token)
    if not setup_token or setup_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This setup link is invalid or has expired.")
    if len(payload.newPassword) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    user = db.get(models.User, setup_token.user_id)
    user.password_hash = hash_password(payload.newPassword)
    user.must_change_password = False
    db.delete(setup_token)
    db.commit()
    return Response(status_code=204)


@router.post("/login")
def login(payload: schemas.LoginIn, request: Request, response: Response, db: DbSession = Depends(get_db)):
    # Wrong password, unknown email, unapproved, and suspended accounts all
    # produce the exact same response (status, message, and rate-limit
    # accounting) - telling them apart would let an attacker enumerate which
    # emails have accounts, and separately which of those are pending/active.
    email_key = f"email:{payload.email.lower()}"
    ip_key = f"ip:{request.client.host if request.client else 'unknown'}"

    if _rate_limit_key_blocked(email_key) or _rate_limit_key_blocked(ip_key):
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")

    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    valid_login = (
        user is not None
        and verify_password(payload.password, user.password_hash)
        and user.approval_status == "approved"
    )
    if not valid_login:
        _record_failed_login(email_key, ip_key)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    _clear_failed_login(email_key, ip_key)

    # Admin-tier accounts always require a second factor; mfa_required
    # additionally opts in any other specific account (e.g. for testing)
    # without changing its role/permissions. Password-correct isn't enough
    # on its own to get a session — a pending challenge is issued instead,
    # and the real session/cookie only appears after the matching
    # /mfa/verify-* call succeeds.
    if user.role in ADMIN_TIER_ROLES or user.mfa_required:
        if user.mfa_enabled:
            challenge = models.MfaChallenge(
                token=secrets.token_urlsafe(24), user_id=user.id, purpose="login",
                expires_at=datetime.utcnow() + MFA_CHALLENGE_TTL,
            )
            db.add(challenge)
            db.commit()
            return schemas.MfaChallengeOut(mfaRequired=True, challengeToken=challenge.token)

        # Not yet enrolled. Reuse an existing unexpired enroll challenge for
        # this user if one's already pending, rather than minting a fresh
        # secret on every login attempt - otherwise any retry (mistyped
        # password, page reload, taking too long to grab a code) hands back
        # a different QR code than the one they already scanned into their
        # authenticator app, making it look like enrollment never sticks.
        challenge = (
            db.query(models.MfaChallenge)
            .filter(
                models.MfaChallenge.user_id == user.id,
                models.MfaChallenge.purpose == "enroll",
                models.MfaChallenge.expires_at > datetime.utcnow(),
            )
            .order_by(models.MfaChallenge.expires_at.desc())
            .first()
        )
        if not challenge:
            challenge = models.MfaChallenge(
                token=secrets.token_urlsafe(24), user_id=user.id, purpose="enroll",
                pending_secret=pyotp.random_base32(), expires_at=datetime.utcnow() + MFA_CHALLENGE_TTL,
            )
            db.add(challenge)
            db.commit()
        secret = challenge.pending_secret
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
    user.must_change_password = False
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
        mustChangePassword=user.must_change_password,
    )
