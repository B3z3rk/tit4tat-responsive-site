REPORT_CATEGORIES = [
    {"name": "Streetlight", "icon": "\U0001F4A1", "description": "Report damaged or non-working lights."},
    {"name": "Water Line", "icon": "\U0001F4A7", "description": "Report leaks, damaged pipes, or water issues."},
    {"name": "Garbage", "icon": "\U0001F5D1️", "description": "Report missed collection or illegal dumping."},
    {"name": "Road Damage", "icon": "\U0001F6E3️", "description": "Report potholes, broken roads, or blocked roads."},
    {"name": "Noise", "icon": "\U0001F50A", "description": "Report ongoing disturbance or nuisance."},
    {"name": "Safety Concern", "icon": "\U0001F6E1️", "description": "Report suspicious or unsafe conditions."},
]

CALL_TARGETS = {
    "admin": {
        "name": "Tit4Tat HOA",
        "initials": "HOA",
        "role": "HOA Representative",
        "text": "You are about to call a Tit4Tat HOA representative for assistance.",
    },
    "business": {
        "name": "Miller’s Mini Mart",
        "initials": "MM",
        "role": "Local Business",
        "text": "You are about to call a verified local business listed in the community directory.",
    },
    "emergency": {
        "name": "Community Alert",
        "initials": "SOS",
        "role": "Emergency Alert",
        "text": "This sends an emergency alert with your name to community admins so they can respond quickly. It does not place a call to emergency services — if you're in immediate danger, contact local emergency services directly.",
    },
}

ROLE_ORDER = {
    "REGULAR_MEMBER": 1,
    "MEMBER": 2,
    # Specialized member roles — same permission tier as MEMBER (verified
    # community access), distinguished by role identity rather than ordinal
    # rank, so they get every base member permission automatically.
    "LOCAL_BUSINESS": 2,
    "COMMUNITY_LEADER": 2,
    "EMERGENCY_CONTACT": 2,
    "HOA": 3,
    "SUPER_ADMIN": 4,
}

# Roles that only a Super Admin may assign to someone else or otherwise act on
# (suspend, reset password, change role) — a regular HOA cannot create,
# demote, or touch another HOA/Super Admin account.
ADMIN_TIER_ROLES = {"HOA", "SUPER_ADMIN"}
