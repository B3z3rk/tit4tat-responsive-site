from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_role

router = APIRouter(tags=["activities"])

# Uploaded cover images live inside the frontend directory tree so the
# existing catch-all StaticFiles mount in main.py serves them for free at
# /uploads/... without needing a second mount (same pattern as avatars).
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
COVER_DIR = FRONTEND_DIR / "uploads" / "activities"

ALLOWED_COVER_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
MAX_COVER_BYTES = 5 * 1024 * 1024  # 5MB


def _format_date(d) -> str:
    # cross-platform "Sat, May 24, 2025" without relying on the non-portable %-d/%#d strftime flags
    return f"{d.strftime('%a, %b')} {d.day}, {d.year}"


def _to_out(activity: models.Activity, db: DbSession, user: models.User) -> schemas.ActivityOut:
    join_count = (
        db.query(models.ActivityParticipant)
        .filter(models.ActivityParticipant.activity_id == activity.id)
        .count()
    )
    joined = (
        db.query(models.ActivityParticipant)
        .filter(
            models.ActivityParticipant.activity_id == activity.id,
            models.ActivityParticipant.user_id == user.id,
        )
        .first()
        is not None
    )
    return schemas.ActivityOut(
        id=activity.id,
        title=activity.title,
        category=activity.category,
        date=_format_date(activity.event_date),
        time=activity.time_label,
        location=activity.location,
        organizer=activity.organizer,
        description=activity.description,
        image=activity.image_url,
        participants=activity.base_participants + join_count,
        joined=joined,
    )


@router.get("", response_model=list[schemas.ActivityOut])
def list_activities(db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    activities = db.query(models.Activity).order_by(models.Activity.event_date).all()
    return [_to_out(a, db, user) for a in activities]


@router.get("/{activity_id}", response_model=schemas.ActivityOut)
def get_activity(activity_id: int, db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    activity = db.get(models.Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return _to_out(activity, db, user)


@router.post("/{activity_id}/join", response_model=schemas.ActivityOut)
def join_activity(activity_id: int, db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    activity = db.get(models.Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    existing = (
        db.query(models.ActivityParticipant)
        .filter(
            models.ActivityParticipant.activity_id == activity_id,
            models.ActivityParticipant.user_id == user.id,
        )
        .first()
    )
    if not existing:
        db.add(models.ActivityParticipant(activity_id=activity_id, user_id=user.id))
        db.commit()

    return _to_out(activity, db, user)


@router.post("", response_model=schemas.ActivityOut, status_code=201)
def create_activity(
    payload: schemas.ActivityCreateIn,
    db: DbSession = Depends(get_db),
    admin: models.User = Depends(require_role("ADMIN")),
):
    activity = models.Activity(
        title=payload.title, category=payload.category, event_date=payload.date,
        time_label=payload.time, location=payload.location, organizer=payload.organizer,
        description=payload.description, image_url=payload.image, base_participants=0,
        created_by_id=admin.id,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return _to_out(activity, db, admin)


@router.post("/{activity_id}/cover", response_model=schemas.ActivityOut)
async def upload_activity_cover(
    activity_id: int,
    file: UploadFile = File(...),
    db: DbSession = Depends(get_db),
    admin: models.User = Depends(require_role("ADMIN")),
):
    activity = db.get(models.Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    ext = ALLOWED_COVER_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use JPEG, PNG, GIF, or WEBP.")

    content = await file.read()
    if len(content) > MAX_COVER_BYTES:
        raise HTTPException(status_code=400, detail="Image is too large (max 5MB).")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    COVER_DIR.mkdir(parents=True, exist_ok=True)

    # clear out any previous cover for this activity under a different extension
    for old_ext in ALLOWED_COVER_TYPES.values():
        old_path = COVER_DIR / f"{activity_id}{old_ext}"
        if old_path.exists():
            old_path.unlink()

    dest = COVER_DIR / f"{activity_id}{ext}"
    dest.write_bytes(content)

    activity.image_url = f"/uploads/activities/{activity_id}{ext}"
    db.commit()
    db.refresh(activity)
    return _to_out(activity, db, admin)


@router.delete("/{activity_id}", status_code=204)
def delete_activity(
    activity_id: int,
    db: DbSession = Depends(get_db),
    admin: models.User = Depends(require_role("ADMIN")),
):
    activity = db.get(models.Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    db.query(models.ActivityParticipant).filter(
        models.ActivityParticipant.activity_id == activity_id
    ).delete()
    db.delete(activity)
    db.commit()
