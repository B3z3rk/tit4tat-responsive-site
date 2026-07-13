from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from . import models
from .constants import ROLE_ORDER
from .database import get_db
from .security import SESSION_COOKIE_NAME


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

    return user


def require_role(min_role: str):
    def _dependency(user: models.User = Depends(get_current_user)) -> models.User:
        if ROLE_ORDER.get(user.role, 0) < ROLE_ORDER[min_role]:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return _dependency
