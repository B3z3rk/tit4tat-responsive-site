from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from . import models
from .constants import ROLE_ORDER
from .database import get_db
from .security import SESSION_COOKIE_NAME

# Routes a user with a forced password change still needs to reach: checking
# who they are, actually changing the password, and signing out. Every other
# authenticated route is blocked until they do, so the frontend redirect to
# the forced-change screen can't be bypassed by calling the API directly.
PASSWORD_CHANGE_EXEMPT_PATHS = {"/api/auth/me", "/api/auth/change-password", "/api/auth/logout"}


def get_current_user(request: Request, db: DbSession = Depends(get_db)) -> models.User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = db.get(models.Session, token)
    if not session or session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.get(models.User, session.user_id)
    if not user or user.approval_status != "approved":
        raise HTTPException(status_code=403, detail="Account not approved")

    if user.must_change_password and request.url.path not in PASSWORD_CHANGE_EXEMPT_PATHS:
        raise HTTPException(status_code=403, detail="You must change your password before continuing.")

    return user


def require_role(min_role: str):
    def _dependency(user: models.User = Depends(get_current_user)) -> models.User:
        if ROLE_ORDER.get(user.role, 0) < ROLE_ORDER[min_role]:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return _dependency
