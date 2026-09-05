# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This repo was generated from a full-stack web template and is being built out as
**DealFlow360**. Auth and roles are done, the full 37-table domain schema exists, the Admin
Management area (products, variants, pricing, discount ceilings, warehouses, recurring plans) is
built, and a rep can build and submit a quotation that routes for approval.

**Still unbuilt:** approval decisions (mockup screens 5–6), fulfillment splitting (7–8),
subscriptions and invoicing (9–10, 12–13), the customer portal (11), deal health (14), reporting
(15), the upsell panel and the pipeline Kanban. The dashboard is still template copy.
`DealFlow360.docx` and the excalidraw mockup at the repo root are the (untracked) spec.

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
password) — see `backend/app/core/seed.py`, which also seeds the whole demo catalog.

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


## The catalog, and why it is shaped this way

**Every product owns at least one variant.** A product with `has_variants = false` gets a single
hidden `Default` row. SKU, per-warehouse stock and tier prices therefore hang off exactly one
place — `product_variants` — and pricing, stock and quotation-line code has one path, not two.
`stock_items` and `quotation_lines.variant_id` both key on the variant, never the product.

**Generate Variants is idempotent.** `product_variants.options` stores the combination as JSONB
(`{"Color": "Black", "RAM": "8GB"}`), and `variant_service.generate_variants` matches existing rows
on that payload. Regenerating after the admin adds a value inserts only the new combinations, so
SKUs, quantities and prices already typed into the matrix survive.

**Two numbers are typed; every price is calculated.** A variant carries `unit_cost` and
`base_price`, both in the base currency. `variant_prices` then holds one derived row per
`(variant, tier, currency)`:

```
unit_price = convert(base_price, base -> currency) x (1 - tier.max_discount_percent / 100)
```

`pricing_service.rebuild_variant_prices()` is the **only** place a `variant_prices` row is written.
Call it after anything that feeds the formula: a variant's cost or price saved (that product's
variants), a tier ceiling changed or a tier added or deleted (all), a currency rate changed or a
currency added or deleted (all). Prices are stored rather than converted on read so resolution stays
one indexed lookup and repricing is always an explicit, visible rebuild.

A consequence worth knowing: **a tier's percentage does two jobs** — it is the standing discount
baked into that tier's prices *and* the ceiling a rep may discount further before a line flags. The
two stay coherent because `recalculate_quotation` measures the rep's discount against the
already-tier-adjusted `unit_price`, so a Gold quote starts at zero points over, not fifteen.

**Nothing half-configured can be saved.** `variant_service.save_variant_matrix` rejects the whole
batch, naming the SKU, unless every row has `unit_cost > 0`, `base_price > 0`, and — for a
non-subscription product — a quantity for every active warehouse.

**Category is free text on the product; its ceiling is a separate table.** There is no categories
table. `category_discount_limits` is keyed by category name, and **a category absent from it has no
ceiling** — which is not the same as a ceiling of zero, or every uncapped line would flag the
instant anyone discounted it. `customer_tiers` has no `code` and no `sort_order`: the name is the
natural key and listings order by `max_discount_percent`.

**Archived is not deleted.** `products.status` is `active` / `archived`. Archived products are
absent from `/lookups/products`, and `add_line` re-checks the status server-side rather than
trusting the picker. Hard delete is refused (409) once a product appears on any quotation line.

Deletes that are refused rather than cascaded, all returning **409** with a detail naming the
blocker: a tier with customers or quotations on it, a currency with prices or quotations in it, a
warehouse holding stock or backing a quoted line, a product on a quotation line.

## Two SQLAlchemy traps this codebase has already hit

- **`populate_existing=True` on `_load_quotation`** (`services/quotation_service.py`). With
  `expire_on_commit=False`, re-querying an object already in the identity map returns it with its
  *previously loaded* collections. Without this, the recalculate straight after `add_line` totalled
  the old set of lines and reported the wrong risk band to the screen.
- **Numeric columns come back as `Decimal`.** Anything read off a persisted row must be `float()`ed
  before it meets a schema float or another Python float, or you get
  `unsupported operand type(s) for +: 'float' and 'decimal.Decimal'` at runtime.

## Discount governance

`recalculate_quotation` measures each line against the **stricter of** its customer tier ceiling and
its category ceiling, snapshotting both onto the line. The blended score follows spec §10:

```
worst    = max(over_by_points)
weighted = Σ(over_by_points × line_net) / Σ(line_net)    # revenue-weighted, not per-unit
score    = min(100, 8 × worst + 5 × weighted)
```

Bands: 0 → `none`, <15 → `low`, <45 → `medium`, else `high`. Routing, which
`_approval_roles_for_band` is the last hardcoded copy of (the next phase reads `approval_rules`):

| Situation | Chain |
|---|---|
| Every line within its ceiling | No approval — a rule with **zero steps**, still written as a real `approvals` row so an auto-approved quote appears in the list |
| Over a ceiling, low or medium | **Sales Manager** |
| Over a ceiling, high | **Sales Manager**, then **Finance** |

**A Sales Rep is never an approver, and Admin is never an approval step.**

## Line entry does not gate on stock

`_allocate_stock_line` records the likeliest source warehouse and the *total* available, and
**never refuses a short line**. An order no single warehouse can cover is exactly what the
warehouse-split feature exists for, and backordering is a first-class state; refusing at entry would
make both unreachable, and would also block services and subscriptions, which carry no stock rows at
all.

## Admin Management

Five tabs under `/app/admin`, admin-only at the parent route
(`frontend/src/pages/admin/management/`): Products (mockup screen 16) → product detail (17),
Price Lists (currencies + a read-only price matrix), Discount Tiers (18), Warehouses, Subscription
Plans. Users stays its own sidebar entry at `/app/admin/users`.

All price editing happens on the product form. The Price Lists tab is deliberately read-only so
there is only ever one place a price comes from.


## Who can see what

`api/endpoints/catalog.py` holds writes behind a router-level `require_admin`. The read paths were
**moved out** rather than duplicated, so there is one implementation of each:

| Router | Guard | Routes |
|---|---|---|
| `catalog.py` | `require_admin` | currencies, tiers, category ceilings, product writes, archive/restore/delete, generate-variants, the variant matrix, the price matrix, subscription plans, customers, approval rules |
| `products.py` | admin, sales_rep, sales_manager, finance | `GET /products` (paginated, searchable, sortable), `GET /products/{id}`, `GET /categories`, `GET /catalog/stats` |
| `warehouses.py` | admin, finance | warehouse CRUD, `GET`/`POST /admin/stock` |

In the UI, **Admin Management (`/app/admin/*`) is admin-only**. Non-admins get the same screens as
separate sidebar entries instead: `Products` (`/app/products`, read-only, for rep / manager /
finance) and `Warehouses` (`/app/warehouses`, full CRUD, for finance). Both mount the same
components with a `readOnly` prop rather than a second copy, and an admin sees neither entry —
they already have those screens as tabs.

`GET /products` is the one server-paginated list (`Page[ProductListRow]`, reusing `Pagination` /
`get_pagination` from `api/deps.py`). Every other table sorts client-side through
`hooks/use-table-sort.ts` + `components/sortable-header.tsx`; they are small and fetched whole.
