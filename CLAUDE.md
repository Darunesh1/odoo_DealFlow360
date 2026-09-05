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

Promote the first superuser directly in the database (no API route grants it):

```bash
docker compose -f backend/docker-compose.yml exec db psql -U postgres -d backend_db \
  -c "UPDATE users SET is_superuser = true WHERE email = 'you@example.com';"
```

## How the two halves connect

Docker runs only Postgres and Redis. The API, the worker and Vite run natively on the host, so
there is **no dev proxy** — the browser calls the API cross-origin and CORS is load-bearing.
Two variables have to agree:

- `backend/.env` → `BACKEND_CORS_ORIGINS=http://localhost:5173,http://localhost:4173`
- `frontend/.env` → `VITE_API_URL=http://localhost:8000/api/v1`

`allow_credentials=True` means a wildcard origin is rejected by browsers; origins must be listed
explicitly. Change a port or host on either side and both files need editing.

`VITE_API_URL` already includes `/api/v1`, so every frontend call is written **relative to the
version prefix** (`api.post("/auth/login")`). The health probes are deliberately mounted at the
root (`/health`, `/health/ready`), outside the prefix, so orchestrators need not know the version.

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

Authorization comes from dependencies in `app/api/deps.py`: `get_current_user`,
`get_current_verified_user`, `get_current_active_superuser`. The admin router applies its guard
**once at the router level** (`APIRouter(dependencies=[...])`), so every route added to `admin.py`
is superuser-only automatically.

Two invariants the routes enforce deliberately, worth preserving:

- `UserUpdateMe` cannot carry `is_active` / `is_superuser` / `is_verified`. That schema boundary —
  not a runtime check — is what stops `PATCH /users/me` from being a privilege-escalation route.
  Admin-only fields live in `UserUpdateAdmin`.
- An admin cannot demote, deactivate or delete their **own** account through `/admin/users/{id}`,
  so a deployment can never end up with zero admins.

Endpoints that take an email address (`/forgot-password`, `/resend-verification`) always return the
same `GENERIC_EMAIL_RESPONSE` regardless of whether the account exists — do not add a branch that
leaks registration status.

Emails are dispatched with Celery `.delay()` and are fire-and-forget; the request never waits on
SMTP. With the `SMTP_*` values unset, `send_email` logs the message instead, which is how you get a
verification link in dev (read the `make worker` terminal).

## Frontend layout

Route tree and lazy-loading live in `src/App.tsx`; `components/route-guards.tsx` provides
`RequireAuth` / `RequireGuest` / `RequireAdmin`. Server state is TanStack Query — the current user
is the `["me"]` query owned by `features/auth/auth-context.tsx`; read it through `useAuth()`, don't
re-fetch `/users/me` elsewhere. Forms are react-hook-form + zod.

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
