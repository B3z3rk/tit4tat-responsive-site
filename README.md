# Tit4Tat Responsive Community Website

Tit4Tat is a responsive community portal: a Python/FastAPI backend (SQLite database,
real auth, a member-approval workflow) serving a multi-page frontend.

## How to run

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then visit `http://127.0.0.1:8000/` — it redirects to `sects.html`, the welcome/sign-in
entry point. The FastAPI process serves both the `/api/*` backend and the static
frontend from a single port, so there's nothing else to run.

The database (`backend/tit4tat.db`) is created and seeded automatically on first run —
delete it and restart the server to reset to a clean demo state.

Sign in with one of the demo accounts shown on the sign-in screen (Admin, Verified
Member, or Community Member) to reach the dashboard.

## Current modules

- Public splash / welcome page, sign in and register (`sects.html`)
- Community activities, details, join flow, and announcements feed (`secta.html`)
- Community reports, submission, admin status control, and report table (`sectb.html`)
- Community directory with a quick-view profile dialog (`sectc.html`)
- Full member profile — photo, address, bio, business info (`sectmemberprofile.html`)
- Messaging (polling-based) and chat (`sectmessages.html`)
- Tap call and emergency call options, incl. broadcast alerts (`sectd.html`)
- Verified-Member business listing + essential-worker status (`sectbusiness.html`)
- Admin: overview dashboard, approvals, announcements composer, emergency call log
  (`sectadmin.html`)
- Admin: account management — roles, password resets, suspend/reactivate
  (`sectsettings.html`)

## Structure

```text
tit4tat_responsive_site/
├── index.html            → redirects to sects.html
├── sects.html             # welcome / sign in / register
├── secta.html             # dashboard + activities + announcements
├── sectb.html             # reports
├── sectc.html             # directory (quick-view profile dialog)
├── sectmemberprofile.html # full member profile page
├── sectd.html             # tap call + emergency
├── sectmessages.html      # messaging
├── sectbusiness.html      # member: business listing + essential worker
├── sectadmin.html         # admin: overview + approvals + announcements + emergency log
├── sectsettings.html      # admin: account management
├── README.md
├── docs/
│   ├── file-structure.md
│   └── roles.md
├── src/
│   ├── css/
│   │   └── shared.css       # shared design tokens, shell, and components
│   └── js/
│       ├── apiClient.js     # fetch wrapper around the backend API (window.Tit4TatAPI)
│       └── localDatabase.js # auth + role/menu logic, backed by the API (window.Tit4TatDB)
└── backend/
    ├── requirements.txt
    ├── tit4tat.db            # created on first run
    └── app/
        ├── main.py           # FastAPI app, router + static frontend wiring
        ├── models.py         # SQLAlchemy models
        ├── schemas.py        # Pydantic request/response models
        ├── security.py       # password hashing, session cookies
        ├── deps.py           # auth/role dependencies
        ├── seed.py           # first-run demo data
        ├── constants.py      # static lookups (report categories, call targets)
        └── routers/          # auth, admin, activities, reports, directory, messages, emergency
```

Each `sect*.html` page also carries a small `<style>` block for styles unique to
that page; anything shared across pages (sidebar, topbar, buttons, cards, toast,
form fields) lives in `src/css/shared.css`.

Auth is a real server-side session: signing in sets an httpOnly cookie backed by a
`sessions` table (see `backend/app/security.py` / `deps.py`) — there's no more
`localStorage`-based "database" on the frontend.
