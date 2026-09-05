# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

**All 18 mockup screens are built.** The end-to-end flow runs: customer self-registration →
quotation with live ceiling checks and upsell suggestions → automatic approval routing → manager
then finance decisions → order confirmation → warehouse split with backorders → despatch →
invoicing of only what shipped → recurring billing with proration → payment → customer portal
negotiation that re-enters approval → deal health alerts → reporting with PDF/XLS export.

`DealFlow360.docx`, `DealFlow360.pdf` and the excalidraw mockup at the repo root are the
(untracked) spec. The excalidraw's 18 frames map to screens as follows: 1 login/signup, 2
dashboard, 3–4 quotations, 5–6 approvals, 7–8 fulfillment, 9–10 subscriptions/billing, 11 customer
portal, 12–13 invoices, 14 deal health, 15 reporting, 16–18 admin catalog.

**Still generic:** the landing page copy in `pages/landing.tsx` and `APP_TAGLINE` in
`frontend/src/config.ts`. Branding otherwise is done — `APP_NAME`, the `DealFlowMark` logo in
`components/brand.tsx`, and the FastAPI title in `app/main.py`.

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
make beat        # Celery scheduler — backorder consolidation, recurring billing, deal health
make prod        # whole stack in Docker (requires JWT_SECRET_KEY in the environment)
```

`make worker` and `make beat` are both needed for the full demo: the worker sends mail, the
scheduler runs the three periodic jobs. Neither is needed to click through the screens.

Single test / subset: `make test ARGS="-k auth"`, `make test ARGS="tests/api/test_admin.py::test_name -x"`.
Anything more specific: `cd backend && uv run pytest ...`.

The suite runs against the **real** Postgres and Redis containers, not mocks. `conftest.py`
truncates `users` and flushes Redis after every test, so a test run wipes your dev data.
Emails are the exception — the `mock_emails` fixture monkeypatches `.delay` so no worker is needed.

**Public signup creates customers and nothing else.** `POST /auth/register` builds a `Customer`
row on the lowest tier and a `User` attached to it with `Role.CUSTOMER`. The role is forced by
`CustomerRegister` having no field that could carry another — a schema boundary, exactly as
`UserUpdateMe`'s missing `roles` is what stops `PATCH /users/me` being a privilege-escalation
route. It answers the same `GENERIC_EMAIL_RESPONSE` whether or not the address was taken, so it is
not an account oracle.

Internal staff are still created by an Admin via `POST /admin/users`, and the invitee sets their
own password from an emailed link (`POST /auth/accept-invite`). Startup seeds `admin@dealflow360.com` / `admin12345`, plus one
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
`RequireAuth` / `RequireGuest` / `RequireRole` (and `RequireAdmin`, a thin alias). All three bounce
a signed-in user to `useAuth().landingPath` rather than a fixed `/app`, because a customer's whole
world is `/portal` and sending them to `/app` would land them on a shell every other guard refuses.

Domain code lives in `src/features/<area>/` — `auth`, `quotations`, `approvals`, `fulfillment`,
`billing`, `portal`, `analytics` — each with its `use-*.ts` hooks and the components only that area
uses. Pages compose them; a page should not hold a mutation. Server state is
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
- **Rate limiting covers only the public auth routes** (`core/rate_limit.py`: register, login,
  forgot-password). Fixed-window counters in Redis against both the caller's IP and the address
  they named. Redis being unavailable logs and lets the request through rather than locking
  everyone out. Nothing else is limited.
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

**A subscription's category is not typed, it is forced.** `catalog_service`
coerces `category` to `"Subscription"` whenever `is_subscription` is true, refuses that name
on a product whose toggle is off, and never suggests it in `list_categories`. The toggle is
the single place subscription-ness is declared - the DB already pairs it with
`recurring_interval` via a CHECK constraint, and this extends the same idea to the category.

**A plan is capped, not stocked.** `ProductVariant.available_quantity` is how many licences
may be sold in total; it is required before a subscription's matrix can be saved, and
`_check_plan_capacity` refuses a line that would take the total past it, counting `ACTIVE`
and `PAUSED` subscriptions. Per-warehouse quantities would be fiction - a plan has no depot.
Physical variants leave it NULL and use `stock_items`.

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

## Three SQLAlchemy traps this codebase has already hit

- **`populate_existing=True` on `_load_quotation`** (`services/quotation_service.py`). With
  `expire_on_commit=False`, re-querying an object already in the identity map returns it with its
  *previously loaded* collections. Without this, the recalculate straight after `add_line` totalled
  the old set of lines and reported the wrong risk band to the screen.
- **Numeric columns come back as `Decimal`.** Anything read off a persisted row must be `float()`ed
  before it meets a schema float or another Python float, or you get
  `unsupported operand type(s) for +: 'float' and 'decimal.Decimal'` at runtime.

- **`lazy="selectin"` does not help an object you just created.** It applies at *query* time. An
  object made persistent by a `flush` — or by an autoflush triggered by the next query — has
  unloaded collections, and reading one under asyncpg raises `MissingGreenlet` rather than issuing
  a query. Three ways out, all used here: build the children in the constructor
  (`Approval(steps=[...])`, `approval_service.open_round`); write them by foreign key and never
  touch the collection (`fulfillment_service.plan_split`); or re-query with `populate_existing`
  before returning (`invoice_service.get_invoice`). Appending to the relationship after a flush is
  the thing that does not work.

## Discount governance

`recalculate_quotation` measures each line against the **stricter of** its customer tier ceiling and
its category ceiling, snapshotting both onto the line. The blended score follows spec §10:

```
worst    = max(over_by_points)
weighted = Σ(over_by_points × line_net) / Σ(line_net)    # revenue-weighted, not per-unit
score    = min(100, 8 × worst + 5 × weighted)
```

Bands: 0 → `none`, <15 → `low`, <45 → `medium`, else `high`. **Routing is read from
`approval_rules` / `approval_rule_steps`** by `approval_service.resolve_rule` and *copied* onto the
approval at submit time, so an admin editing a rule cannot rewrite an in-flight chain. Bands are
half-open (`min_score <= score < max_score`, NULL max unbounded) so adjacent rules meeting at 45
cannot both match. The seeded chains:

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


## Delivery dates

`requested_delivery_date` is **required** on `QuotationCreate` and must not be
in the past. It is not decoration: the split is promised against it and
delivery slippage is measured from it, so a quotation without one leaves both
unanswerable.

`promised_delivery_date` is written **once, when the split is accepted** — not
at creation, because until stock is actually reserved there is nothing to
promise against. It is `max(requested, earliest everything can be dispatched)`,
where the earliest is the latest backorder restock date. Promising the
customer's date when a backorder clears after it would be a promise already
known to be false.

## The order lifecycle

**Approval plans the split; Finance reserves.** The moment a quotation reaches `APPROVED` -
by auto-approval, by the last approver in a chain, or by an accepted counter-offer -
`order_service.plan_fulfillment` works out which warehouses would cover it, so the order
appears under "Orders awaiting fulfillment" without anyone going looking. It deliberately
does **not** reserve: accepting the split is Finance's decision and reserving here would make
that click meaningless. `approval_service.plan_if_approved` swallows failures on purpose - a
missing warehouse must not undo an approval that has already been decided and emailed.

`confirm_quotation`'s idempotency keys on the **quotation's status**, not on whether a
fulfillment exists. The old check would have returned early and silently skipped the sales
history and the subscriptions once approval started creating fulfillments.


One row carries a deal from start to finish: **a CONFIRMED quotation *is* the sales order.** The
mockup uses one reference (Q-1042) for the quotation, its approval and its fulfillment, so a
separate `orders` table would invent an entity the spec never shows.

`order_service.confirm_quotation` is the fan-out point, and the only place several things happen:
it writes one `SalesRecord` per line (with category, tier and team snapshotted, so a product
changing category cannot rewrite last quarter), opens a `Subscription` per recurring line, creates
the `Fulfillment` and runs the split planner. All under a Redis lock, and idempotent — a
double-clicked Confirm returns the split it already made.

### The split planner

`fulfillment_service.plan_split` draws from warehouses ordered by `(quantity_available DESC,
shipping_base_cost ASC)`: **fewest warehouses touched**, ties broken on the two rates a human typed
into the warehouse form. Whatever no warehouse can cover becomes a `BACKORDERED` allocation with an
expected restock date. Subscription lines are skipped entirely — a plan has no stock to ship.

Reservations are taken under `SELECT … FOR UPDATE`, so two confirmations of the last three laptops
cannot both succeed; the loser backorders. "Est. Shipments" is `COUNT(*)` of real `PLANNED`
shipment rows rather than a stored integer, so the estimate and the reality are the same rows in
two states. `consolidate_backorders` folds a cleared backorder into the shipment already planned
for that warehouse rather than opening a second one.

## Billing

One-time invoices are raised **by hand** — Finance clicks *Invoice what has
shipped* on the fulfillment screen, which calls
`POST /quotations/{id}/invoice`. Recurring invoices are raised **automatically**
by Celery Beat at 02:00 UTC daily. There is deliberately no automatic one-time
invoicing on despatch: a partial shipment often wants batching with the next
one, and that is a commercial decision rather than a rule.

Two invariants, both enforced by the schema rather than by convention:

- **Nothing is billed before it ships.** A `ONE_TIME` invoice line must point at a `shipment_line`,
  and `quantity_invoiced <= quantity_shipped` is a CHECK. Partial delivery therefore drives partial
  invoicing by construction — `invoice_service.invoice_shipped` bills the difference and nothing
  else, returning `None` when there is nothing new.
- **A period is billed once.** A partial unique index on `(subscription_id, service_period_start)`
  where `line_type = 'recurring'` means a retried Celery task raises `IntegrityError` instead of
  double-billing. That is also why future billing periods are never materialised: they are
  arithmetic, and rows would only need deleting on cancellation.

Proration (`subscription_service`) is the unused fraction of the period times the change:

```
proration_factor = (current_period_end - effective) / (current_period_end - current_period_start)
delta            = (new_qty - old_qty) × unit_price × proration_factor
```

Every intermediate value is written to the `SubscriptionEvent`, which is what lets the billing
screen show proration *history* rather than an unexplained adjustment. A negative delta issues a
`CreditNote`. `SubscriptionEvent.resulting_invoice_id` being NULL **is** the pending-proration
queue — the biller sweeps it onto the next invoice, so there is no queue table.

`invoices.amount_paid` is always the signed sum of that invoice's payments, recomputed after every
write rather than incremented: an incremented total drifts the first time a write is retried, and
drift here is money that does not add up.

## The customer portal

§7 of the spec: *"must be a real, separate, restricted view, not just another internal screen with
a different label."* Three things enforce that, and none of them is a filter applied late:

1. `api/endpoints/portal.py` admits **only** `Role.CUSTOMER`. An admin gets 403, not a god view.
2. Every query filters on `current_user.customer_id`; an id that is not theirs answers **404**, so
   the portal is not an existence oracle either.
3. `schemas/portal.py` is a separate set of schemas, not a filtered `QuotationRead`. There is
   nowhere to put `unit_cost`, `margin_total`, the risk score or the approval chain — leaking one
   would take a code change, not a slip.

Accepting a counter-offer (`negotiation_service.accept_change_request`) applies it at the **order**
level so it is folded into every line and governed by each line's own ceiling, recalculates, and
opens a fresh approval round with `trigger=CUSTOMER_COUNTER`. If the new terms sit inside every
ceiling it auto-approves down the same path a rep's own submission takes. There is no second,
weaker confirmation path: the portal's Confirm calls `order_service.confirm_quotation`.

## Caching, locks and scheduled work

`core/cache.py` keys reads as `cache:{namespace}:v{n}:{suffix}`, where `n` comes from a counter in
Redis. **Invalidation is one `INCR` on that counter**, which orphans the old keys to expire on
their own TTL — O(1), safe when two writers race, and with no key list to keep in step. Bump
*after* the write, never before.

| Namespace | What it holds | What invalidates it |
|---|---|---|
| `catalog` | the picker's products, tiers, currencies, warehouses, categories, the KPI stats | every write in `catalog_service`, and `rebuild_variant_prices` |
| `report` | report aggregates keyed on the filter set, and each rep's trailing discount average | order confirmation — the only thing that writes `sales_records` |
| `quotation` | upsell dismissals, a Redis set with a day's TTL | its own expiry |

**The dashboard is deliberately not cached.** Its tiles cost ~10 ms, they are per-viewer so reuse
is low, and nearly every write in the system moves one — a quotation created, a line edited, a
split accepted, a payment taken, a credit applied. Correct invalidation would mean a bump at a
dozen call sites that rots the first time someone adds a thirteenth, and the whole point of those
tiles is that they agree with the list they link to.

Anything that *is* cached is cached because it is expensive and has exactly one writer. That is the
test to apply before adding another.

**Failure behaviour differs on purpose.** Reads degrade: `cached_json`, `bump`, the dismissal sets
and the rate limiter all catch a Redis failure, log it, and let the request through — with Redis
down every screen still loads, just uncached. `with_lock` **fails closed**, because reading
uncached is merely slower whereas confirming an order twice writes the sales history twice and
there is no unique index to catch it. A missing lock raises `LockUnavailable` → **503**; losing a
race raises `LockNotAcquired` → **409**, both handled once in `main.py` so a double-clicked Confirm
is a retry rather than a stack trace.

`with_lock` is `SET NX EX` held for a block — used for confirm, split planning, the invoice run,
per-subscription billing and credit-note numbering.

Three jobs run on Celery Beat (`make beat`): backorder consolidation every 15 minutes, recurring
billing daily at 02:00 UTC, the deal-health sweep hourly. `tasks/scheduled_tasks.py` dispatches by
import name and tolerates a service that does not exist, so the schedule can be declared before the
work is written.

## Deal health

`health_service.sweep` raises three kinds of alert. A **discount anomaly** is measured against
*that rep's own* trailing average over the last `REP_AVERAGE_DAYS`, not a company mean — a rep who
habitually sells at 14% is not an outlier, and flagging them trains everyone to ignore the
dashboard.

Suppression has two halves, and both are bounded. An open alert of the same kind silences a
re-raise **only while the severity has not increased**: nudging one used to quiet that pair for
ever, so a deal idle for nine days and then ninety kept showing the flag somebody had already waved
at. When it worsens the old alert is superseded and a higher one takes its place. A resolved alert
buys `ALERT_QUIET_DAYS` of silence - its own setting, because it used to reuse the stall window, so
widening that to thirty days also muted resolved alerts for thirty.

`POST /alerts/sweep` is a management action: it scans every live quotation and commits. `GET
/alerts` is scoped like every other list, so a rep sees flags on their own deals rather than their
colleagues' discount anomalies.

## Dashboards have to agree with the screens they link to

`report_service.dashboard(db, viewer)` is scoped by the same predicate the lists use, and its
cache key carries the viewer (`home:{role}:{id}`) - a shared key would serve one person's
scoped numbers to everyone. Tiles differ per role, and each is computed from the same query as
the screen it links to.

Two rules worth keeping: "waiting on me" uses `approval_service.can_act`, the inbox's own
predicate, rather than a second definition of pending; and "at-risk deals" counts **distinct
quotations**, because one deal carrying a stall and a slippage flag is one deal.

The reports screen applies its filters to quote counts and approval time too, via
`_apply_to_quotations` - they used to ignore every filter, making conversion rate a filtered
numerator over an unfiltered denominator.

## Reporting

Every figure comes from `sales_records`, never from live quotation lines. Lines stay editable after
confirmation, so a derived report would silently change, and a "top product" that shifts
retroactively is worse than none. `came_from_upsell` is what makes "Top Upsold Product" answerable
at all. Exports are built in memory (`export_service`) and streamed — no temp files.

## Scale, and what it cost

`make load-data` (`backend/scripts/generate_load_data.py`) fills the database with 300 products,
300 customers and 150 quotations through the **ORM**, so every rule the app enforces shaped the
data. Measured at that size, every list endpoint answers in under 150 ms cold.

Two things had to change to get there, and both were the same mistake:

- **`GET /lookups/products` returned the full `ProductRead`** — every derived price and every
  per-warehouse stock row for every variant. At 300 products that was 684 KB and ~500 queries,
  and the picker reads none of it. It now returns `PickerProduct`: id, name, category and the
  active variants, in two queries. 2,291 ms → 63 ms, 684 KB → 113 KB.
- **The price matrix and the stock table painted every row** — ~2,900 and ~900 at that size. Both
  now render a 250-row window with a "showing X of Y" line; the search is how you reach the rest.
  The query was never the bottleneck, the browser was.

The pattern worth remembering: a list endpoint should return what its screen renders. Reusing the
detail schema for a picker is what made both of these slow.

## Who can see what

`api/endpoints/catalog.py` holds writes behind a router-level `require_admin`. The read paths were
**moved out** rather than duplicated, so there is one implementation of each:

| Router | Guard | Routes |
|---|---|---|
| `catalog.py` | `require_admin` | currencies, tiers, category ceilings, product writes, archive/restore/delete, generate-variants, the variant matrix, the price matrix, subscription plans, customers, approval rules |
| `products.py` | admin, sales_rep, sales_manager, finance | `GET /products` (paginated, searchable, sortable), `GET /products/{id}`, `GET /categories`, `GET /catalog/stats` |
| `warehouses.py` | admin, finance | warehouse CRUD, `GET`/`POST /admin/stock` |
| `quotations.py` | admin, sales_rep, sales_manager | the quotation list, builder, suggestions, submit, and the rep's side of negotiation |
| `approvals.py` | admin, sales_rep, sales_manager, finance | reads for everyone (a rep watches their own deal); the **decision** is restricted to the role of the step actually waiting, by the service, not the router |
| `fulfillment.py` | reads: admin, finance, manager, rep | writes (accept / override / consolidate / ship) narrowed to **admin, finance** per-route |
| `billing.py` | reads: admin, finance, manager, rep | writes (payments, subscription changes) narrowed to **admin, finance** |
| `analytics.py` | admin, sales_rep, sales_manager, finance | dashboard, alerts, reports; nudge/escalate narrowed to **admin, manager, finance** |
| `portal.py` | **`Role.CUSTOMER` only** | the customer's own quotations, comments, counter-offers, confirm, invoices |

A rep may also create a customer mid-quotation (`POST /customers`, name and email only) — the
tier is not theirs to choose, and `sync_customer_portal_email` does the rest: the login, the
link, the invite. Credit notes are listed by everyone and applied by Finance.

Whose turn it is in an approval chain is a property of the loaded chain, not of the URL, so it is
checked in `approval_service.decide` rather than by a router guard. A router-level guard could only
say "some manager", not "the manager this step is waiting on".

In the UI, **Admin Management (`/app/admin/*`) is admin-only**. Non-admins get the same screens as
separate sidebar entries instead: `Products` (`/app/products`, read-only, for rep / manager /
finance) and `Warehouses` (`/app/warehouses`, full CRUD, for finance). Both mount the same
components with a `readOnly` prop rather than a second copy, and an admin sees neither entry —
they already have those screens as tabs.

`GET /products` is the one server-paginated list (`Page[ProductListRow]`, reusing `Pagination` /
`get_pagination` from `api/deps.py`). Every other table sorts client-side through
`hooks/use-table-sort.ts` + `components/sortable-header.tsx`; they are small and fetched whole.
