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

This runs over plain HTTP — fine for poking at the app solo on localhost, but every
request (including any password) travels unencrypted. Use `start-server.ps1` below
instead of this command for anything reachable beyond your own machine; it serves
over HTTPS.

The database (`backend/tit4tat.db`) is created and seeded automatically on first run —
delete it and restart the server to reset to a clean demo state.

Demo accounts (see `backend/app/seed.py` for the full list): `member@tit4tat.com` /
`member123` (Verified Member), `regular@tit4tat.com` / `regular123` (Community Member),
`admin@tit4tat.com` / `admin123` (HOA), `superadmin@tit4tat.com` / `superadmin123`
(Super Admin). These passwords are hardcoded demo data, not a real secret — the HOA
and Super Admin accounts force a password change on first sign-in specifically because
their password is public, so logging in with it only gets you as far as setting a new
one only you know.

### Serving to other devices on the network

To reach the site from other devices (phones, laptops) on the same network instead of
just this machine, use the helper scripts from the repo root:

```powershell
.\start-server.ps1   # binds 0.0.0.0:8000 over HTTPS, prints the LAN URL to share
.\stop-server.ps1    # stops it
```

This generates a self-signed TLS certificate on first run (`backend/certs/`, not
committed) and serves over HTTPS instead of plain HTTP, so traffic is actually
encrypted on the wire. Browsers will show a one-time "connection is not private"
warning since it isn't signed by a real certificate authority — that's expected for
local/LAN dev; click through it (Advanced > Proceed). Delete `backend/certs/` to force
a fresh certificate, e.g. after your LAN IP changes.

If other devices can't connect, Windows Firewall is probably blocking the port — the
start script prints the `New-NetFirewallRule` command to allow it. Pass `-Port` to
either script to use something other than 8000.

### Emailing newly-approved members

When an HOA approves a pending registration, the applicant never gets a password from
the admin at all — the app emails them a one-time setup link (`sects.html?setupToken=...`,
valid 24 hours) where they choose their own password directly. There's no temporary
password to relay, show on screen, or intercept.

Without SMTP configured, that email is just logged to the server's console/log instead
of actually sent — so the feature is fully testable with zero setup (the HOA sees a
message pointing at the log; copy the link from there and share it manually).

To send real emails, copy `.env.example` to `.env` (same folder) and fill in real
values:

```powershell
Copy-Item .env.example .env
notepad .env
```

```ini
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your-16-character-app-password
SMTP_FROM=you@gmail.com
```

(For Gmail specifically: enable 2-Step Verification on the account, then generate an
[App Password](https://myaccount.google.com/apppasswords) — regular account passwords
won't work with SMTP. Any other provider works the same way; just point `SMTP_HOST`/
`SMTP_PORT` at it instead.) `start-server.ps1` loads `.env` automatically on every
start and prints whether SMTP ended up configured. `.env` is gitignored, so real
credentials never end up in source control — if you'd rather not use a file, setting
the same names as real environment variables (`$env:SMTP_HOST = "..."`) before running
`start-server.ps1` works too and takes the same effect.

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
