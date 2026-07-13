from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_role

router = APIRouter(tags=["directory"])

# Uploaded avatars live inside the frontend directory tree so the existing
# catch-all StaticFiles mount in main.py serves them for free at /uploads/...
# without needing a second mount.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
AVATAR_DIR = FRONTEND_DIR / "uploads" / "avatars"

ALLOWED_AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5MB


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _to_out(user: models.User) -> schemas.MemberOut:
    return schemas.MemberOut(
        id=user.id,
        name=user.name,
        initials=_initials(user.name),
        category=user.category,
        specialty=user.specialty,
        location=user.location,
        availability=user.availability,
        status=user.presence_status or "Offline",
        verified=user.approval_status == "approved",
        business=bool(user.business),
        businessName=user.business_name,
        businessDescription=user.business_description,
        essentialWorker=bool(user.is_essential_worker),
        essentialWorkerType=user.essential_worker_type,
        essentialWorkerRegistrationNumber=user.essential_worker_registration_number,
        bio=user.bio,
        notes=[n.note for n in sorted(user.notes, key=lambda n: n.created_at)],
        avatarUrl=user.avatar_path,
    )


@router.get("", response_model=list[schemas.MemberOut])
def list_members(db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    members = (
        db.query(models.User)
        .filter(models.User.approval_status == "approved")
        .order_by(models.User.name)
        .all()
    )
    return [_to_out(m) for m in members]


# Registered before "/{member_id}" so "me" is matched here rather than
# falling into the int path-converter below and failing validation.
@router.get("/me", response_model=schemas.MemberOut)
def get_my_profile(user: models.User = Depends(get_current_user)):
    return _to_out(user)


@router.patch("/me", response_model=schemas.MemberOut)
def update_my_business(
    payload: schemas.MyBusinessUpdateIn,
    db: DbSession = Depends(get_db),
    user: models.User = Depends(require_role("MEMBER")),
):
    business_name = (payload.businessName or "").strip() or None
    user.business_name = business_name
    user.business_description = (payload.businessDescription or "").strip() or None
    user.business = business_name is not None

    if payload.isEssentialWorker:
        ew_type = (payload.essentialWorkerType or "").strip()
        ew_reg = (payload.essentialWorkerRegistrationNumber or "").strip()
        if not ew_type or not ew_reg:
            raise HTTPException(
                status_code=400,
                detail="Type of essential work and registration number are required.",
            )
        user.essential_worker_type = ew_type
        user.essential_worker_registration_number = ew_reg
    else:
        user.essential_worker_type = None
        user.essential_worker_registration_number = None
    user.is_essential_worker = payload.isEssentialWorker
    if business_name and user.category != "Local Business":
        user.category = "Local Business"
    elif not business_name and user.category == "Local Business":
        user.category = "General Member"
    db.commit()
    db.refresh(user)
    return _to_out(user)


@router.patch("/me/profile", response_model=schemas.MemberOut)
def update_my_profile(
    payload: schemas.MyProfileUpdateIn,
    db: DbSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if payload.bio is not None:
        user.bio = payload.bio.strip() or None
    if payload.location is not None:
        user.location = payload.location.strip() or None
    if payload.specialty is not None:
        user.specialty = payload.specialty.strip() or None
    if payload.availability is not None:
        user.availability = payload.availability.strip() or None
    db.commit()
    db.refresh(user)
    return _to_out(user)


@router.post("/me/avatar", response_model=schemas.MemberOut)
async def upload_my_avatar(
    file: UploadFile = File(...),
    db: DbSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ext = ALLOWED_AVATAR_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use JPEG, PNG, GIF, or WEBP.")

    content = await file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Image is too large (max 5MB).")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    # clear out any previous avatar for this user under a different extension
    for old_ext in ALLOWED_AVATAR_TYPES.values():
        old_path = AVATAR_DIR / f"{user.id}{old_ext}"
        if old_path.exists():
            old_path.unlink()

    dest = AVATAR_DIR / f"{user.id}{ext}"
    dest.write_bytes(content)

    user.avatar_path = f"/uploads/avatars/{user.id}{ext}"
    db.commit()
    db.refresh(user)
    return _to_out(user)


@router.get("/{member_id}", response_model=schemas.MemberOut)
def get_member(member_id: int, db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    member = db.get(models.User, member_id)
    if not member or member.approval_status != "approved":
        raise HTTPException(status_code=404, detail="Member not found")
    return _to_out(member)
