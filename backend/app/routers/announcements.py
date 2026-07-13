from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_role

router = APIRouter(tags=["announcements"])


def _to_out(a: models.Announcement) -> schemas.AnnouncementOut:
    return schemas.AnnouncementOut(
        id=a.id, title=a.title, body=a.body,
        authorName=a.created_by.name if a.created_by else "Admin",
        createdAt=a.created_at,
    )


@router.get("", response_model=list[schemas.AnnouncementOut])
def list_announcements(db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.Announcement).order_by(models.Announcement.created_at.desc()).limit(20).all()
    return [_to_out(a) for a in rows]


@router.post("", response_model=schemas.AnnouncementOut, status_code=201)
def create_announcement(
    payload: schemas.AnnouncementCreateIn,
    db: DbSession = Depends(get_db),
    admin: models.User = Depends(require_role("ADMIN")),
):
    announcement = models.Announcement(title=payload.title, body=payload.body, created_by_id=admin.id)
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return _to_out(announcement)


@router.delete("/{announcement_id}", status_code=204)
def delete_announcement(
    announcement_id: int,
    db: DbSession = Depends(get_db),
    admin: models.User = Depends(require_role("ADMIN")),
):
    announcement = db.get(models.Announcement, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    db.delete(announcement)
    db.commit()
