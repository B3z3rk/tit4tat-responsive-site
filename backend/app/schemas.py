from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class MfaChallengeOut(BaseModel):
    """Returned by /login in place of UserOut when a second factor is needed —
    no session cookie is set until the matching /mfa/verify-* call succeeds."""
    mfaRequired: Optional[bool] = None
    mfaSetupRequired: Optional[bool] = None
    challengeToken: str
    secret: Optional[str] = None       # only present for mfaSetupRequired
    otpauthUrl: Optional[str] = None   # only present for mfaSetupRequired


class MfaVerifyIn(BaseModel):
    challengeToken: str
    code: str


class AuditLogEntryOut(BaseModel):
    id: int
    actorName: str
    action: str
    targetName: Optional[str] = None
    detail: Optional[str] = None
    createdAt: datetime


class ApproveIn(BaseModel):
    role: Optional[str] = None  # defaults to REGULAR_MEMBER server-side if omitted


class RejectIn(BaseModel):
    reason: Optional[str] = None


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    approvalStatus: str
    profile: Optional[str] = None
    avatarUrl: Optional[str] = None
    mustChangePassword: bool = False
    # only populated on the admin-reset-password response, so HOA can relay it to the member
    temporaryPassword: Optional[str] = None
    # only populated on the approve-user response - whether the setup-link
    # email actually went out via real SMTP (False just means it was logged
    # server-side instead, e.g. no SMTP configured in this environment)
    setupEmailSent: Optional[bool] = None

    class Config:
        from_attributes = True


class PendingUserOut(BaseModel):
    id: int
    name: str
    email: str
    createdAt: datetime
    communityArea: Optional[str] = None
    referenceName: Optional[str] = None
    referenceVerified: bool = False
    referenceUploaded: bool
    idUploaded: bool
    billUploaded: bool

    class Config:
        from_attributes = True


class ActivityOut(BaseModel):
    id: int
    title: str
    category: str
    date: str
    time: str
    location: str
    organizer: str
    description: str
    image: Optional[str] = None
    participants: int
    joined: bool


class ActivityCreateIn(BaseModel):
    title: str
    category: str
    date: date  # ISO "YYYY-MM-DD"
    time: str
    location: str
    organizer: str
    description: str
    image: Optional[str] = None


class ReportCategoryOut(BaseModel):
    name: str
    icon: str
    description: str


class TimelineEventOut(BaseModel):
    note: str
    date: str


class ReportOut(BaseModel):
    id: str
    title: str
    category: str
    priority: str
    status: str
    date: str
    location: str
    description: str
    submittedBy: str
    timeline: List[TimelineEventOut]
    mediaUrl: Optional[str] = None
    mediaType: Optional[str] = None


class ReportCreateIn(BaseModel):
    title: str
    category: str
    priority: str
    location: str
    description: str


class ReportStatusIn(BaseModel):
    status: str


class MemberNoteOut(BaseModel):
    note: str


class MemberOut(BaseModel):
    id: int
    name: str
    initials: str
    category: Optional[str] = None
    specialty: Optional[str] = None
    location: Optional[str] = None
    availability: Optional[str] = None
    status: str  # presence: Online | Offline
    verified: bool
    business: bool
    businessName: Optional[str] = None
    businessDescription: Optional[str] = None
    essentialWorker: bool
    essentialWorkerType: Optional[str] = None
    essentialWorkerRegistrationNumber: Optional[str] = None
    bio: Optional[str] = None
    notes: List[str]
    avatarUrl: Optional[str] = None
    memberCode: Optional[str] = None


class MemberLookupOut(BaseModel):
    """Minimal public info returned when a registration applicant scans a
    member's reference QR code — deliberately excludes anything the member
    isn't already showing by choosing to display their own QR code."""
    id: int
    name: str
    communityArea: Optional[str] = None


class MyBusinessUpdateIn(BaseModel):
    businessName: Optional[str] = None
    businessDescription: Optional[str] = None
    isEssentialWorker: bool = False
    essentialWorkerType: Optional[str] = None
    essentialWorkerRegistrationNumber: Optional[str] = None


class MyProfileUpdateIn(BaseModel):
    bio: Optional[str] = None
    location: Optional[str] = None
    specialty: Optional[str] = None
    availability: Optional[str] = None


class ChangePasswordIn(BaseModel):
    currentPassword: str
    newPassword: str


class SetupPasswordIn(BaseModel):
    token: str
    newPassword: str


class MyStatsOut(BaseModel):
    activitiesJoined: int
    upcomingActivities: int
    reportsSubmitted: int
    reportsByStatus: Dict[str, int]
    unreadMessages: int
    memberSince: datetime


class ContactOut(BaseModel):
    id: int
    name: str
    initials: str
    role: Optional[str] = None
    location: Optional[str] = None
    status: str
    unread: int
    lastTime: str
    lastMessage: str
    avatarUrl: Optional[str] = None


class MessageOut(BaseModel):
    id: int
    type: str  # "sent" | "received" (relative to requesting user)
    text: str
    time: str


class MessageCreateIn(BaseModel):
    text: str


class CallTargetOut(BaseModel):
    name: str
    initials: str
    role: str
    text: str


class EmergencyCallIn(BaseModel):
    targetType: str
    targetLabel: str
    targetUserId: Optional[int] = None


class EmergencyCallLogOut(BaseModel):
    id: int
    callerName: str
    targetType: str
    targetLabel: str
    createdAt: datetime
    # True only when a real Twilio bridge call was actually placed - absent/False
    # means the usual simulated call UI, not that anything failed
    callPlaced: bool = False


class RecentSignupOut(BaseModel):
    id: int
    name: str
    email: str
    approvalStatus: str
    createdAt: datetime


class AdminOverviewOut(BaseModel):
    pendingApprovals: int
    totalMembers: int
    totalActivities: int
    openReports: int
    urgentReports: int
    recentSignups: List[RecentSignupOut]
    recentReports: List[ReportOut]


class AnnouncementOut(BaseModel):
    id: int
    title: str
    body: str
    authorName: str
    createdAt: datetime


class AnnouncementCreateIn(BaseModel):
    title: str
    body: str


class AdminUserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    approvalStatus: str
    createdAt: datetime


class ResetPasswordIn(BaseModel):
    newPassword: Optional[str] = None  # if omitted, server generates a temporary password


class ResetPasswordOut(BaseModel):
    temporaryPassword: Optional[str] = None  # only present when the server generated one


class RoleChangeIn(BaseModel):
    role: str


class EmergencyAlertOut(BaseModel):
    id: int
    callerName: str
    callerLocation: Optional[str] = None
    targetType: str
    targetLabel: str
    createdAt: datetime
