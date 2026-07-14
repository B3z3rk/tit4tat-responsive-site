from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from .. import models, schemas
from ..constants import CALL_TARGETS
from ..database import get_db
from ..deps import get_current_user, require_role

router = APIRouter(tags=["emergency"])


@router.get("/targets", response_model=dict[str, schemas.CallTargetOut])
def get_targets():
    return CALL_TARGETS


@router.post("/calls", response_model=schemas.EmergencyCallLogOut, status_code=201)
def log_call(
    payload: schemas.EmergencyCallIn,
    db: DbSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    call = models.EmergencyCall(
        user_id=user.id, target_type=payload.targetType, target_label=payload.targetLabel,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    return schemas.EmergencyCallLogOut(
        id=call.id, callerName=user.name, targetType=call.target_type,
        targetLabel=call.target_label, createdAt=call.created_at,
    )


@router.get("/admin/calls", response_model=list[schemas.EmergencyCallLogOut], dependencies=[Depends(require_role("ADMIN"))])
def list_calls(db: DbSession = Depends(get_db)):
    calls = db.query(models.EmergencyCall).order_by(models.EmergencyCall.created_at.desc()).all()
    return [
        schemas.EmergencyCallLogOut(
            id=c.id, callerName=c.user.name if c.user else "Unknown",
            targetType=c.target_type, targetLabel=c.target_label, createdAt=c.created_at,
        )
        for c in calls
    ]


@router.get("/alerts", response_model=list[schemas.EmergencyAlertOut])
def list_alerts(
    after_id: int = 0,
    db: DbSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    # Broadcasts emergency alerts only (not member/business/admin tap calls, which
    # are person-to-person calls) to the rest of the community — not back to the
    # caller themselves, who already sees their own confirmation — so everyone is
    # aware when someone nearby needs urgent help.
    calls = (
        db.query(models.EmergencyCall)
        .filter(
            models.EmergencyCall.id > after_id,
            models.EmergencyCall.user_id != user.id,
            models.EmergencyCall.target_type == "emergency",
        )
        .order_by(models.EmergencyCall.id)
        .all()
    )
    return [
        schemas.EmergencyAlertOut(
            id=c.id, callerName=c.user.name if c.user else "Unknown",
            callerLocation=c.user.location if c.user else None,
            targetType=c.target_type, targetLabel=c.target_label, createdAt=c.created_at,
        )
        for c in calls
    ]
