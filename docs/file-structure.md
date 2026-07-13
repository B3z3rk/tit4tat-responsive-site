# Tit4Tat File Directory

This is a small full-stack web system: a Python/FastAPI backend (`backend/`) with a
SQLite database, and a multi-page frontend where each screen is its own HTML page
(`sect*.html`) rather than a single-page app.

## Root

- `index.html` — redirects to `sects.html`, the real entry point.
- `sects.html` — public splash, requirements, sign in, and register.
- `secta.html` — dashboard, community activities, and the announcements feed.
- `sectb.html` — community reports (includes the admin-only status control).
- `sectc.html` — community directory; selecting a member opens a quick-view dialog.
- `sectmemberprofile.html` — a member's full profile page (photo/avatar, address, bio,
  business info, community notes), reached via "View Profile".
- `sectd.html` — tap call and emergency call options only (see `sectmessages.html` for
  messaging).
- `sectmessages.html` — member-to-member messaging (conversation list + chat).
- `sectbusiness.html` — verified-Member-only: manage a local business listing and
  essential-worker status, shown in the directory.
- `sectadmin.html` — admin-only: overview dashboard, member approval queue,
  announcements composer, and emergency call log.
- `sectsettings.html` — admin-only: account management (roles, password resets,
  suspend/reactivate).
- `README.md` — setup notes and module list.

## src

- `src/js/apiClient.js` — thin `fetch()` wrapper around the backend API, exposed as
  `window.Tit4TatAPI`. Every page that needs live data (activities, reports, members,
  messages, emergency targets) calls this instead of reading local mock data.
- `src/js/localDatabase.js` — auth (sign in/register/sign out) and role/menu rendering
  shared by every `sect*.html` page, exposed as `window.Tit4TatDB`. Internally it's a
  thin wrapper over `Tit4TatAPI`'s auth endpoints — no `localStorage` "database"
  anymore, the server owns the real session.
- `src/css/shared.css` — shared design tokens, app shell (sidebar/topbar), buttons,
  form fields, cards, and toast used by all pages. Each page's own `<style>` block
  only holds rules specific to that page.

## backend

- `backend/app/main.py` — FastAPI app; registers all `/api/*` routers, then mounts the
  frontend root as static files. Router registration must stay before the static
  mount, or the mount's catch-all would 404 every API request first.
- `backend/app/models.py` — SQLAlchemy models. Notably, `User` unifies login accounts
  and community-directory members (one real account = one directory entry).
- `backend/app/schemas.py` — Pydantic request/response shapes, deliberately named to
  match what the frontend already expects (e.g. `submittedBy`, `lastMessage`) to keep
  page-side rendering code unchanged.
- `backend/app/security.py` / `deps.py` — password hashing (`bcrypt`, used directly —
  not `passlib`, which doesn't detect current `bcrypt` versions), and the session-cookie
  auth + `require_role()` dependency used across routers.
- `backend/app/seed.py` — populates demo accounts, directory members, activities,
  reports, and starter messages the first time the database is empty.
- `backend/app/routers/` — one file per feature area: `auth`, `admin` (approvals,
  account management), `activities`, `reports`, `directory` (includes the `/members/me`
  business-listing endpoints), `messages`, `emergency` (calls + broadcast alerts),
  `announcements`.

## docs

- `docs/file-structure.md` — explanation of this folder structure.
- `docs/roles.md` — role/permission notes for Admin, Member, and Regular Member; the
  source the role model (and `require_role()` ordering) was built from.
