from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(tags=["dashboard"])


@router.get("/me", response_model=schemas.MyStatsOut)
def get_my_stats(db: DbSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    activities_joined = (
        db.query(models.ActivityParticipant)
        .filter(models.ActivityParticipant.user_id == user.id)
        .count()
    )
    upcoming_activities = (
        db.query(models.Activity).filter(models.Activity.event_date >= date.today()).count()
    )

    reports = db.query(models.Report).filter(models.Report.submitted_by_id == user.id).all()
    reports_by_status: dict[str, int] = {}
    for report in reports:
        reports_by_status[report.status] = reports_by_status.get(report.status, 0) + 1

    unread_messages = (
        db.query(models.Message)
        .filter(models.Message.recipient_id == user.id, models.Message.read_at.is_(None))
        .count()
    )

    return schemas.MyStatsOut(
        activitiesJoined=activities_joined,
        upcomingActivities=upcoming_activities,
        reportsSubmitted=len(reports),
        reportsByStatus=reports_by_status,
        unreadMessages=unread_messages,
        memberSince=user.created_at,
    )
