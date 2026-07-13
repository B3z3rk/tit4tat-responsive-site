from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from .directory import _initials

router = APIRouter(tags=["messages"])


def _format_time(dt: datetime) -> str:
    today = datetime.utcnow().date()
    if dt.date() == today:
        return dt.strftime("%I:%M %p").lstrip("0")
    return dt.strftime("%b %d")


def _thread_query(db: DbSession, me_id: int, other_id: int):
    return db.query(models.Message).filter(
        or_(
            and_(models.Message.sender_id == me_id, models.Message.recipient_id == other_id),
            and_(models.Message.sender_id == other_id, models.Message.recipient_id == me_id),
        )
    )


@router.get("/contacts", response_model=list[schemas.ContactOut])
def list_contacts(db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    others = (
        db.query(models.User)
        .filter(models.User.approval_status == "approved", models.User.id != user.id)
        .order_by(models.User.name)
        .all()
    )

    rows = []
    for other in others:
        last = _thread_query(db, user.id, other.id).order_by(models.Message.created_at.desc()).first()
        unread = (
            db.query(models.Message)
            .filter(
                models.Message.sender_id == other.id,
                models.Message.recipient_id == user.id,
                models.Message.read_at.is_(None),
            )
            .count()
        )
        rows.append((
            last.created_at if last else datetime.min,
            schemas.ContactOut(
                id=other.id, name=other.name, initials=_initials(other.name),
                role=other.category, location=other.location,
                status=other.presence_status or "Offline",
                unread=unread,
                lastTime=_format_time(last.created_at) if last else "",
                lastMessage=last.body if last else "Say hello to start the conversation.",
                avatarUrl=other.avatar_path,
            ),
        ))
    # contacts with the most recent message activity first
    rows.sort(key=lambda r: r[0], reverse=True)
    return [contact for _, contact in rows]


@router.get("/{other_id}", response_model=list[schemas.MessageOut])
def get_thread(
    other_id: int,
    after_id: int = 0,
    db: DbSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    other = db.get(models.User, other_id)
    if not other:
        raise HTTPException(status_code=404, detail="Contact not found")

    query = _thread_query(db, user.id, other_id).filter(models.Message.id > after_id)
    rows = query.order_by(models.Message.created_at).all()

    # mark incoming messages as read now that the thread has been fetched
    unread_ids = [m.id for m in rows if m.sender_id == other_id and m.read_at is None]
    if unread_ids:
        db.query(models.Message).filter(models.Message.id.in_(unread_ids)).update(
            {"read_at": datetime.utcnow()}, synchronize_session=False
        )
        db.commit()

    return [
        schemas.MessageOut(
            id=m.id, type="sent" if m.sender_id == user.id else "received",
            text=m.body, time=_format_time(m.created_at),
        )
        for m in rows
    ]


@router.post("/{other_id}", response_model=schemas.MessageOut, status_code=201)
def send_message(
    other_id: int,
    payload: schemas.MessageCreateIn,
    db: DbSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    other = db.get(models.User, other_id)
    if not other:
        raise HTTPException(status_code=404, detail="Contact not found")
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="Message text is required")

    message = models.Message(sender_id=user.id, recipient_id=other_id, body=payload.text.strip())
    db.add(message)
    db.commit()
    db.refresh(message)
    return schemas.MessageOut(id=message.id, type="sent", text=message.body, time=_format_time(message.created_at))
