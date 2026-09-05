# DealFlow360

A production-shaped starting point for a web application. Authentication, email flows,
background jobs and an admin area are already wired together, so the first thing you build
is the part that is actually yours.

**Backend** — FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Redis · Celery, managed with `uv`
**Frontend** — React 19 · TypeScript · Vite · Tailwind v4 · shadcn/ui

---

## How it runs

Docker provides the two stateful services you would rather not install by hand. Everything
containing project code runs natively, so an edit is live the moment you save it.

| In Docker | On your machine |
|---|---|
| PostgreSQL 16 → `:5432` | FastAPI → `:8000` |
| Redis 7 → `:6379` | Celery worker |
| | Vite dev server → `:5173` |

A fully containerised composition is available too, for deployment — see
[Deployment](#deployment).

---

## Quick start

Requires [Docker](https://docs.docker.com/get-docker/),
[uv](https://docs.astral.sh/uv/getting-started/installation/) and Node 20+.

```bash
make install     # creates both .env files, then installs backend + frontend deps
```

Then, in three terminals:

```bash
make api         # starts Postgres and Redis for you, then serves the API
make worker      # the Celery worker
make web         # the Vite dev server
```

| | |
|---|---|
| Application | <http://localhost:5173> |
| API | <http://localhost:8000> |
| Interactive API reference | <http://localhost:8000/docs> |

Register an account at <http://localhost:5173/register>. With no SMTP configured, the
verification email is printed to the **`make worker` terminal** — copy the link from there
and open it in your browser.

### All commands

```
make help        show this list
make env         create backend/.env and frontend/.env from their examples
make install     create the .env files and install all dependencies
make up          start the Postgres and Redis containers
make down        stop the containers, keeping the data volumes
make logs        tail the container logs
make fresh       destroy the data volumes and start again from empty
make api         run the FastAPI server on :8000
make worker      run the Celery worker
make web         run the Vite dev server on :5173
make test        run the backend test suite
make lint        lint and typecheck the frontend
make prod        run the whole stack in Docker
make prod-down   stop the full Docker stack
```

---

## Configuration

The two applications keep **separate** environment files. Neither is committed; both are
created from their `.env.example` by `make env`, which never overwrites an existing file.

| File | Owns |
|---|---|
| `backend/.env` | database and Redis connection, JWT secret and token lifetimes, CORS origins, SMTP |
| `frontend/.env` | the API base URL |

Both applications run with **no `.env` at all** — every setting has a working local default.
The files exist so you can change things without editing code.

### The two variables that connect the halves

```ini
# backend/.env — which browser origins may call the API
BACKEND_CORS_ORIGINS=http://localhost:5173,http://localhost:4173
```

```ini
# frontend/.env — where the API lives
VITE_API_URL=http://localhost:8000/api/v1
```

If you move either side to a different port or host, change both. A wildcard origin is not
usable here: the API sends credentials, and browsers reject `*` in that case.

### Other settings worth knowing

| Variable | Purpose |
|---|---|
| `FRONTEND_URL` | Where verification and password-reset emails point. Must be the address a person can actually open. |
| `JWT_SECRET_KEY` | Generate with `openssl rand -hex 32`. The sample value is **refused** when `ENVIRONMENT=production`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime, 15 by default. The frontend refreshes transparently. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime, 7 by default. |
| `SMTP_*` | While unset, mail is logged instead of sent. Fill in all four to send for real. |

---

## API

Everything lives under `/api/v1`. Health probes sit at the root so orchestrators can reach
them without knowing the version.

### Authentication — `/api/v1/auth`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/register` | Create an account and send a verification email |
| `POST` | `/login` | OAuth2 password flow; returns an access + refresh pair |
| `POST` | `/refresh` | Exchange a refresh token for a new pair, revoking the old one |
| `POST` | `/logout` | Revoke a refresh token |
| `POST` | `/verify-email` | Confirm an address using the emailed token |
| `POST` | `/resend-verification` | Send a fresh verification link |
| `POST` | `/forgot-password` | Start a password reset |
| `POST` | `/reset-password` | Complete a reset using the emailed token |
| `POST` | `/change-password` | Change your password, re-checking the current one |

### Your own account — `/api/v1/users`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/me` | Read your profile |
| `PATCH` | `/me` | Update your name or email. Changing the email resets verification. |
| `DELETE` | `/me` | Delete your own account |

`PATCH /me` accepts **only** `email` and `full_name`. Role and status fields are not part of
its schema, so this route cannot be used to grant yourself privileges.

### Administration — `/api/v1/admin`

Superusers only; everyone else gets a `403`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/users` | Paginated list with `search`, `is_active`, `page` and `size` |
| `GET` | `/users/{id}` | Read one account |
| `PATCH` | `/users/{id}` | Update any field, including role and status |
| `DELETE` | `/users/{id}` | Delete an account |

An administrator cannot demote, deactivate or delete their own account here, so a deployment
can never be left without one.

### Operations

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness. Answers whenever the process is up. |
| `GET` | `/health/ready` | Readiness. Reports on Postgres and Redis; `503` if either is down. |

### Making the first administrator

Accounts are created as ordinary members. Promote one directly in the database:

```bash
docker compose -f backend/docker-compose.yml exec db \
  psql -U postgres -d backend_db \
  -c "UPDATE users SET is_superuser = true WHERE email = 'you@example.com';"
```

Sign out and back in, and **Administration → Users** appears in the sidebar.

---

## Frontend

| Route | Access | Screen |
|---|---|---|
| `/` | public | Landing page |
| `/login` `/register` | signed out | Sign in, sign up |
| `/forgot-password` `/reset-password` `/verify-email` | public | Account recovery and confirmation |
| `/app` | signed in | Dashboard |
| `/app/profile` `/app/settings` | signed in | Profile, appearance, password, account deletion |
| `/app/admin/users` | superuser | User management |

```text
frontend/src/
├── config.ts            app name and API URL — start here when rebranding
├── index.css            design tokens: palette, typography, motion
├── lib/api.ts           axios client with a single-flight token refresh
├── types/api.ts         response shapes shared with the backend
├── providers/           theme and react-query providers
├── features/auth/       auth context, hook, and the zod schemas every form uses
├── components/
│   ├── ui/              shadcn/ui primitives
│   └── ...              sidebar, nav, theme toggle, form helpers
├── layouts/             marketing, auth, and application shells
└── pages/               one file per route
```

### Making it yours

1. **Name** — change `APP_NAME` in `src/config.ts`. It flows to the header, sidebar, footer,
   emails-facing copy and the browser tab.
2. **Colour** — change `--primary` and `--brass` in `src/index.css`. Both themes and every
   component follow from those two variables.
3. **Copy** — the landing page sections in `src/pages/landing.tsx` are scaffolding. The
   pricing tiers in particular are placeholders, there so you have a working section to point
   at your own plans.

Validation rules live in `src/features/auth/schemas.ts` and mirror the backend's own rules in
`backend/app/schemas/user.py`. If you change a password policy, change both.

---

## Testing

```bash
make test                      # the whole suite
make test ARGS="-k auth"       # a subset
```

The suite runs against the real Postgres and Redis containers rather than mocks, so
`make test` starts them if they are not already up.

Lint and typecheck the frontend with `make lint`, which runs `oxlint` and then `tsc -b`.

---

## Deployment

`backend/docker-compose.prod.yml` runs the whole stack — database, cache, API and worker —
in containers:

```bash
export ENVIRONMENT=production
export JWT_SECRET_KEY=$(openssl rand -hex 32)
make prod
```

Two things guard the secret, at different layers:

- The compose file declares `JWT_SECRET_KEY` as **required**, with no fallback. It has to
  come from the shell or from `backend/.env`, or compose stops before starting anything.
- The application refuses to boot when `ENVIRONMENT=production` and the key is still the
  sample value, wherever that value came from.

`backend/.env` is a **development** file — it carries the sample secret and
`ENVIRONMENT=development`, and if it is present compose will read from it. On a real
deployment, supply the environment properly and do not ship that file.

---

## Known gaps

- **No migrations.** Tables are created from the models at startup via
  `Base.metadata.create_all`. That is fine until you have data you care about; add Alembic
  before your first schema change in production.
- **Tokens live in `localStorage`,** which is readable by any script running on the page.
  Refresh tokens rotate on use and can be revoked, which limits the damage, but httpOnly
  cookies are stronger if your threat model calls for it.
- **No rate limiting** on sign-in or password reset. Redis is already available if you want
  to add it.

---

## Licence

MIT — see [LICENSE](LICENSE).
