from pathlib import Path

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..constants import REPORT_CATEGORIES, ROLE_ORDER
from ..database import get_db
from ..deps import get_current_user, require_role

router = APIRouter(tags=["reports"])

VALID_STATUSES = {"Submitted", "Under Review", "Urgent", "Resolved"}

# Report evidence lives inside the frontend directory tree so the existing
# catch-all StaticFiles mount in main.py serves it for free at /uploads/...
# — public within the app (like avatars/activity covers), not gated like the
# Super-Admin-only verification documents.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
REPORT_MEDIA_DIR = FRONTEND_DIR / "uploads" / "reports"

ALLOWED_REPORT_MEDIA_TYPES = {
    "image/jpeg": (".jpg", "image"),
    "image/png": (".png", "image"),
    "image/gif": (".gif", "image"),
    "image/webp": (".webp", "image"),
    "video/mp4": (".mp4", "video"),
    "video/webm": (".webm", "video"),
    "video/quicktime": (".mov", "video"),
}
MAX_REPORT_MEDIA_BYTES = 20 * 1024 * 1024  # 20MB — video needs more headroom than a photo


def _format_date(d: datetime) -> str:
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _to_out(report: models.Report) -> schemas.ReportOut:
    return schemas.ReportOut(
        id=report.id,
        title=report.title,
        category=report.category,
        priority=report.priority,
        status=report.status,
        date=_format_date(report.created_at),
        location=report.location,
        description=report.description,
        submittedBy=report.submitted_by.name if report.submitted_by else "Unknown",
        timeline=[
            schemas.TimelineEventOut(note=e.note, date=_format_date(e.created_at))
            for e in report.timeline
        ],
        mediaUrl=report.media_path,
        mediaType=report.media_type,
    )


@router.get("/reports", response_model=list[schemas.ReportOut])
def list_reports(db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    reports = db.query(models.Report).order_by(models.Report.created_at.desc()).all()
    return [_to_out(r) for r in reports]


@router.get("/reports/{report_id}", response_model=schemas.ReportOut)
def get_report(report_id: str, db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    report = db.get(models.Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return _to_out(report)


@router.post("/reports", response_model=schemas.ReportOut, status_code=201)
def create_report(
    payload: schemas.ReportCreateIn,
    db: DbSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    count = db.query(models.Report).count()
    report_id = f"T4T-RPT-{count + 1:03d}"
    status = "Urgent" if payload.priority == "Urgent" else "Submitted"
    now = datetime.utcnow()

    report = models.Report(
        id=report_id, title=payload.title, category=payload.category, priority=payload.priority,
        status=status, location=payload.location, description=payload.description,
        submitted_by_id=user.id, created_at=now, updated_at=now,
    )
    db.add(report)
    db.flush()

    first_note = (
        "Urgent report flagged for immediate attention" if status == "Urgent" else "Pending HOA review"
    )
    db.add(models.ReportTimelineEvent(report_id=report.id, note="Report submitted by member", created_by_id=user.id, created_at=now))
    db.add(models.ReportTimelineEvent(report_id=report.id, note=first_note, created_at=now))
    db.commit()
    db.refresh(report)
    return _to_out(report)


@router.post("/reports/{report_id}/media", response_model=schemas.ReportOut)
async def upload_report_media(
    report_id: str,
    file: UploadFile = File(...),
    db: DbSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    report = db.get(models.Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    is_owner = report.submitted_by_id == user.id
    is_hoa_tier = ROLE_ORDER.get(user.role, 0) >= ROLE_ORDER["HOA"]
    if not is_owner and not is_hoa_tier:
        raise HTTPException(status_code=403, detail="Only the reporter or HOA can attach evidence to this report")

    type_info = ALLOWED_REPORT_MEDIA_TYPES.get(file.content_type)
    if not type_info:
        raise HTTPException(
            status_code=400,
            detail="Unsupported media type. Use a JPEG/PNG/GIF/WEBP photo or an MP4/WEBM/MOV video.",
        )
    ext, kind = type_info

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_REPORT_MEDIA_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (max 20MB).")

    REPORT_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    # clear out any previous evidence for this report under a different extension
    for other_ext, _ in ALLOWED_REPORT_MEDIA_TYPES.values():
        old_path = REPORT_MEDIA_DIR / f"{report_id}{other_ext}"
        if old_path.exists():
            old_path.unlink()

    dest = REPORT_MEDIA_DIR / f"{report_id}{ext}"
    dest.write_bytes(content)

    report.media_path = f"/uploads/reports/{report_id}{ext}"
    report.media_type = kind
    db.commit()
    db.refresh(report)
    return _to_out(report)


@router.patch("/reports/{report_id}/status", response_model=schemas.ReportOut)
def update_status(
    report_id: str,
    payload: schemas.ReportStatusIn,
    db: DbSession = Depends(get_db),
    admin: models.User = Depends(require_role("HOA")),
):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(VALID_STATUSES)}")

    report = db.get(models.Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.status = payload.status
    report.updated_at = datetime.utcnow()
    db.add(models.ReportTimelineEvent(
        report_id=report.id, note=f"Status updated to {payload.status} by HOA",
        created_by_id=admin.id, created_at=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(report)
    return _to_out(report)


@router.get("/report-categories", response_model=list[schemas.ReportCategoryOut])
def report_categories():
    return REPORT_CATEGORIES
