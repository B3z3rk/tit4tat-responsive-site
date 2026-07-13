from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..security import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    create_session,
    hash_password,
    set_session_cookie,
    verify_password,
)

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=schemas.UserOut, status_code=201)
def register(payload: schemas.RegisterIn, db: DbSession = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")

    user = models.User(
        name=payload.name,
        email=payload.email.lower(),
        phone=payload.phone,
        password_hash=hash_password(payload.password or "welcome123"),
        role="REGULAR_MEMBER",
        approval_status="pending",
        community_area=payload.communityArea,
        reference_name=payload.referenceName,
        reference_uploaded=payload.referenceUploaded,
        id_uploaded=payload.idUploaded,
        utility_bill_uploaded=payload.billUploaded,
        profile="New community member",
        # seed directory fields from what registration already collects, so the
        # member shows up in the directory with something more than blanks
        # the moment an admin approves them
        category="General Member",
        location=payload.communityArea,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.post("/login", response_model=schemas.UserOut)
def login(payload: schemas.LoginIn, response: Response, db: DbSession = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user.approval_status == "suspended":
        raise HTTPException(status_code=403, detail="Your account has been suspended by an admin.")
    if user.approval_status != "approved":
        raise HTTPException(status_code=403, detail="Your account is pending admin approval.")

    session = create_session(db, user)
    set_session_cookie(response, session.token)
    return _to_user_out(user)


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
