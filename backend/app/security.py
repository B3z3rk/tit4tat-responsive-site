import secrets
from datetime import datetime, timedelta

import bcrypt
from fastapi import Response
from sqlalchemy.orm import Session as DbSession

from . import models

SESSION_COOKIE_NAME = "t4t_session"
SESSION_TTL = timedelta(days=7)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_session(db: DbSession, user: models.User) -> models.Session:
    session = models.Session(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.utcnow() + SESSION_TTL,
    )
    db.add(session)
    db.commit()
    return session


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
        max_age=int(SESSION_TTL.total_seconds()),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
