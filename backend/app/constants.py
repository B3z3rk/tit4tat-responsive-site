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
        "name": "Tit4Tat Admin",
        "initials": "TA",
        "role": "Community Admin",
        "text": "You are about to call a Tit4Tat community admin for assistance.",
    },
    "business": {
        "name": "Miller’s Mini Mart",
        "initials": "MM",
        "role": "Local Business",
        "text": "You are about to call a verified local business listed in the community directory.",
    },
    "emergency": {
        "name": "Emergency Services",
        "initials": "911",
        "role": "Emergency Contact",
        "text": "This should be used for urgent safety, medical, fire, or police matters only.",
    },
}

ROLE_ORDER = {"REGULAR_MEMBER": 1, "MEMBER": 2, "ADMIN": 3}
