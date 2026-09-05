# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This repo was generated from a full-stack web template and is being built out as
**DealFlow360**. The template's auth, email, admin and background-job machinery is complete and
working; **the domain layer is not written yet** — there are no deal/pipeline models, routes or
screens. `DealFlow360.pdf` at the repo root is the (untracked) spec.

Branding is done: the app name lives in `frontend/src/config.ts` (`APP_NAME`), the logo is
`DealFlowMark` in `components/brand.tsx`, and the FastAPI title is set in `app/main.py`. The
landing-page copy in `pages/landing.tsx` and `APP_TAGLINE` are still generic placeholders.

## Commands

All commands run from the repo root via the Makefile; it `cd`s into `backend/` or `frontend/` for you.

```
make install     # create both .env files, then uv sync + npm install
make api         # FastAPI on :8000 (starts Postgres + Redis first)
make worker      # Celery worker  — verification/reset emails print here when SMTP is unset
make web         # Vite dev server on :5173
make test        # backend pytest suite (also starts the containers)
make lint        # frontend: oxlint, then tsc -b
make fresh       # destroy the data volumes and restart empty
make prod        # whole stack in Docker (requires JWT_SECRET_KEY in the environment)
```

Single test / subset: `make test ARGS="-k auth"`, `make test ARGS="tests/api/test_admin.py::test_name -x"`.
Anything more specific: `cd backend && uv run pytest ...`.

The suite runs against the **real** Postgres and Redis containers, not mocks. `conftest.py`
truncates `users` and flushes Redis after every test, so a test run wipes your dev data.
Emails are the exception — the `mock_emails` fixture monkeypatches `.delay` so no worker is needed.

There is **no public signup**. `POST /auth/register` does not exist: an Admin creates accounts
via `POST /admin/users` and the invitee sets their own password from an emailed link
(`POST /auth/accept-invite`). Startup seeds `admin@dealflow360.com` / `admin12345`, plus one
demo account per role in development (`rep@`, `manager@`, `finance@`, `customer@`, same
password) — see `backend/app/core/seed.py`.

**`make test` shares `backend_db` with the dev server and truncates `users` after every test**,
so a test run wipes the seeded accounts. Restart the API (or touch a file, with `--reload`) to
re-seed before using the app again.

## How the two halves connect

Docker runs only Postgres and Redis. The API, the worker and Vite run natively on the host, so
there is **no dev proxy** — the browser calls the API cross-origin and CORS is load-bearing.
Two variables have to agree:

- `backend/.env` → `BACKEND_CORS_ORIGINS=http://localhost:5173,http://localhost:4173`
- `frontend/.env` → `VITE_API_URL=http://localhost:8000/api`

`allow_credentials=True` means a wildcard origin is rejected by browsers; origins must be listed
explicitly. Change a port or host on either side and both files need editing.

`VITE_API_URL` already includes `/api`, so every frontend call is written **relative to that
prefix** (`api.post("/auth/login")`). The API is deliberately unversioned: one frontend ships
with this backend, so there is no external client to keep a `/v1` alive for. The health probes
sit at the root (`/health`, `/health/ready`), outside the prefix, for orchestrators.

### Auth token flow

`POST /auth/login` is an OAuth2 password flow, so it takes **form encoding**, not JSON — see
`auth-context.tsx`, which builds a `URLSearchParams` and overrides the Content-Type. Every other
endpoint is JSON.

Refresh tokens **rotate**: presenting one revokes it (jti recorded in Redis with a TTL matching the
token's own expiry). This is why `lib/api.ts` implements single-flight refresh — if four parallel
requests each fired their own `/auth/refresh`, three would present tokens rotation had already
revoked. Preserve that property when touching the interceptor. The interceptor also skips retrying
any URL starting with `/auth/`, so a failing refresh cannot recurse.

Tokens live in `localStorage` behind `lib/tokens.ts`; that module is the only place that knows the
storage mechanism.

## Backend layout

`app/api/endpoints/*` → `app/services/user_service.py` → `app/models/*`. Endpoints hold HTTP
concerns (status codes, 404s, authorization guards); services hold the SQLAlchemy queries and are
re-exported flat from `app.services`. Add new service functions to both
`user_service.py` and the `__init__.py` `__all__`.

Authorization is role-based. A user holds **many** roles (`Role` enum in `app/models/user.py`:
`admin`, `sales_rep`, `sales_manager`, `finance`, `customer`), stored in the `user_roles`
association table. `require_roles(*roles)` in `app/api/deps.py` builds a dependency admitting
anyone holding at least one of them; `require_admin` is the only shortcut built so far — add
others alongside their first route. The admin router applies its guard **once at the router
level** (`APIRouter(dependencies=[...])`), so every route added to `admin.py` is admin-only
automatically.

`User.role_links` uses `lazy="selectin"`, which is load-bearing: roles are read in the auth
dependency, during response serialization after the endpoint returns, and by the delete-orphan
cascade — all places where an asyncpg lazy load would raise `MissingGreenlet`. Because it is set
at the mapper, no query needs an explicit `selectinload`.

`User.roles` is a read-only property, so `update_user`'s blind `setattr` loop must keep popping
`roles` before it runs. Role writes go through `apply_roles()`, which reconciles rather than
replacing the collection — assigning a fresh list orphans and re-inserts rows with identical
composite keys and intermittently violates the primary key.

Invariants the routes enforce deliberately, worth preserving:

- `UserUpdateMe` cannot carry `roles` / `is_active` / `is_verified`. That schema boundary —
  not a runtime check — is what stops `PATCH /users/me` from being a privilege-escalation route.
  Admin-only fields live in `UserUpdateAdmin`, where `roles` is a full replacement, not a merge.
- An admin cannot remove their own `admin` role, deactivate or delete their **own** account,
  so a deployment can never end up with zero admins. Seeding also re-grants `admin` to
  `FIRST_ADMIN_EMAIL` on boot if it is somehow missing.

- An invitation is single-use, and what enforces that is the **password**, not `is_verified`:
  a pending account stores an unusable sentinel (`"!" + random`, see `core/security.py`) that
  bcrypt can never match. Keying on `is_verified` would be unsafe, because changing your email
  resets that flag and would re-arm an old invite token against a live account.

Endpoints that take an email address (`/forgot-password`, `/resend-verification`) always return the
same `GENERIC_EMAIL_RESPONSE` regardless of whether the account exists — do not add a branch that
leaks registration status.

Emails are dispatched with Celery `.delay()` and are fire-and-forget; the request never waits on
SMTP. With the `SMTP_*` values unset, `send_email` logs the message instead, which is how you get a
verification link in dev (read the `make worker` terminal).

## Frontend layout

Route tree and lazy-loading live in `src/App.tsx`; `components/route-guards.tsx` provides
`RequireAuth` / `RequireGuest` / `RequireRole` (and `RequireAdmin`, a thin alias). Server state is
TanStack Query — the current user is the `["me"]` query owned by `features/auth/auth-context.tsx`;
read it through `useAuth()`, which also exposes `hasRole(...roles)` and `isAdmin`. Don't re-fetch
`/users/me` elsewhere, and don't read `user.roles` directly when `hasRole` will do. Forms are
react-hook-form + zod.

Role names and their display labels live once in `types/api.ts` (`ROLES`, `ROLE_LABELS`) and must
stay in step with the backend `Role` enum. `components/role-picker.tsx` holds the shared checkbox
group and badge rendering.

`src/config.ts` is the rebranding entry point (`APP_NAME`, `APP_TAGLINE`, `STORAGE_KEYS`);
`src/index.css` holds the design tokens — `--primary` and `--brass` drive both themes.
`src/components/ui/` is generated shadcn/ui; prefer regenerating over hand-editing.

Use `errorMessage()` from `lib/api.ts` to surface failures — it unpacks FastAPI's `detail`, which is
a string for `HTTPException` but a list of `{msg, loc}` objects for 422 validation errors.

## Things that are duplicated on purpose

- **Password rules** exist in `backend/app/schemas/user.py` (the `Password` annotated type) and in
  `frontend/src/features/auth/schemas.ts`. Change one, change the other.
- **Response shapes** in `frontend/src/types/api.ts` are hand-maintained against the Pydantic
  schemas. There is no codegen; adding a field to `UserRead` means adding it to `User` there too.

## Known gaps to work around

- **No migrations.** Tables come from `Base.metadata.create_all` in `init_db()` at startup, and new
  models must be imported there to register with the metadata. Adding a column to an existing table
  will *not* alter it — during development use `make fresh`; add Alembic before there is data worth
  keeping.
- **No rate limiting** on login or password reset. Redis is already wired if you add it.
- Access tokens are 15 minutes, refresh 7 days (`ACCESS_TOKEN_EXPIRE_MINUTES`,
  `REFRESH_TOKEN_EXPIRE_DAYS`).
