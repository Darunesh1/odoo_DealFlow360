# Recording the backorder flow

A nine-step script for the warehouse-split and backorder feature, written to be
followed on camera. Roles change three times; the tab you are in is called out
at every step.

Everything below uses the seeded catalogue, which already stages the shortage —
**no setup is required** beyond having the stack running.

## Before you start

```
make api      # terminal 1
make worker   # terminal 2 — emails print here
make web      # terminal 3
```

Sign-in password for every account is `FIRST_ADMIN_PASSWORD` from `backend/.env`
(`admin12345` by default).

| Role | Account |
|---|---|
| Admin | `admin@dealflow360.com` |
| Sales Rep | `rep@dealflow360.com` |
| Sales Manager | `manager@dealflow360.com` |
| Finance | `finance@dealflow360.com` |

### The shortage is already staged

`core/seed.py` deliberately understocks one product so this demo has something
to split:

| Warehouse | Shipping base | Lead time | Laptop Pro 14 on hand |
|---|---|---|---|
| EAST | 18.00 | 9 days | **8** |
| MAIN | 25.00 | 5 days | **3** |

Eleven units in total. **Quote more than 11 and the remainder backorders.** The
script uses 24, which gives a clean three-way story: 8 from one warehouse, 3
from the other, 13 backordered.

### The one thing that will trip you up

The planner draws from warehouses by *deepest stock first, then cheapest
shipping*. But whatever it cannot cover is booked against the **cheapest active
warehouse** — here **EAST** — regardless of which warehouse ran short.

So at step 7, when you restock to clear the backorder, **you must add stock to
EAST**. Adding it to MAIN will look right and do nothing, and the amber
"stock has arrived" card will never appear.

---

## The script

### 1 — Admin · show the shortage

*Admin Management → Warehouses*, search `Laptop`. Point at the two rows: 3 at
MAIN, 8 at EAST.

> "Eleven units across two warehouses. We're about to sell twenty-four."

### 2 — Sales Rep · build the quotation

Sign in as `rep@`. *Quotations → New quotation*, pick any customer, set a
delivery date, add **24 × Laptop Pro 14**.

The line shows an amber note: **"Only 11 in stock — the rest backorders"**. This
is a warning, not a refusal — an order no single warehouse can cover is exactly
what the split feature exists for.

Give a discount above the customer's tier ceiling (the *Limit* column shows it)
so the deal routes for approval. **Submit**.

### 3 — Sales Manager · approve

Sign in as `manager@`. *Approvals* → the quotation is waiting. Approve it.

If the discount scored HIGH, a Finance step follows — sign in as `finance@` and
approve that too.

> "Approval plans the split automatically. Nobody had to go looking for it."

### 4 — Finance · read the suggested split

Sign in as `finance@`. *Fulfillment* → the order is under *Orders awaiting
fulfillment*. Open it.

**Warehouse split** shows:

| Warehouse | Qty fulfilled | Est. shipments | Cost |
|---|---|---|---|
| EAST | 8 units | 1 | *cost* |
| MAIN | 3 units | 1 | *cost* |
| EAST *(amber)* | 13 units | — | — |

The amber row is the backorder, with an expected restock date derived from that
warehouse's lead time. **Lines** shows the same story per line, with an amber
`backordered` pill.

Nothing is reserved yet — planning is a suggestion, reserving is Finance's
decision.

### 5 — Finance · accept the split

Click **Accept suggested split**. Allocations flip `planned → reserved`, stock
is reserved under `SELECT … FOR UPDATE`, and planned shipments appear in the
**Shipments** card.

This is also where the customer's promised delivery date is written — the later
of what they asked for and when everything can actually ship.

### 6 — Finance · ship what you have

In **Shipments**, click **Ship** on the planned shipments. Each one:

- moves its allocations to `shipped`
- decrements stock on both counters
- makes those units **billable** — nothing is invoiced before it ships

The fulfillment status becomes `partially_shipped`. The backorder is still open.

### 7 — Admin · restock **EAST**

Sign in as `admin@`. *Admin Management → Warehouses → Stock*, find
`Laptop Pro 14` at **EAST**, and set `quantity_on_hand` to cover the 13
outstanding units.

> Remember: EAST, not MAIN. The backorder is booked against the cheapest
> warehouse, not the one that ran short.

### 8 — Finance · consolidate

Back as `finance@`, reload the fulfillment. An amber card appears:

> **Stock has arrived for a backorder** — It can be reserved and folded into the
> shipment already planned for that warehouse, rather than opening a second one.

Click **Consolidate remaining backorder**. The allocation flips to `reserved`
and a shipment appears for it at EAST.

**Whether it folds or opens a new shipment depends on what you did at step 6.**
Consolidation joins the shipment already *planned* for that warehouse — so if
you shipped EAST's first load already, that one has gone and a second shipment
is opened for the backorder, which is the honest outcome. If you want to show
the fold instead, run steps 7 and 8 **before** step 6: the 13 units join EAST's
still-planned shipment and the customer gets one delivery rather than two.

*(This also runs on its own every 15 minutes when `make beat` is up — the button
is the same code path, just on demand.)*

> Verified end to end on a clean database: EAST 8 + MAIN 3 shipped, EAST 13
> backordered with a restock date nine days out (EAST's lead time), then
> consolidated and shipped — 21 units from EAST, 3 from MAIN, 24 in total.

### 9 — Finance · ship it, then invoice

**Ship** the consolidated shipment. The order reaches `fulfilled`.

Then **Invoice what has shipped** — the invoice covers only despatched units, by
construction: a one-time invoice line must point at a shipment line, and
`quantity_invoiced <= quantity_shipped` is a database CHECK.

---

## What to say while it runs

- **Step 2** — entry never refuses a short line. Backordering is a first-class
  state, not an error.
- **Step 4** — the split draws from the fewest warehouses possible, ties broken
  on the two rates an admin typed into the warehouse form. "Est. shipments" is a
  count of real planned shipment rows, so the estimate and the reality are the
  same rows in two states.
- **Step 5** — reservations are taken under a row lock, so two people confirming
  the last three laptops cannot both win; the loser backorders.
- **Step 6** — shipping is what makes units billable. Partial delivery drives
  partial invoicing by construction.
- **Step 8** — consolidation reserves the cleared backorder and joins the
  shipment already planned for that warehouse, so a customer waiting on stock
  gets one delivery rather than two — provided that shipment has not left yet.

## Resetting between takes

```
make fresh                      # destroys the volumes
# restart the API so it re-seeds, then optionally:
make load-data ARGS="--products 300 --customers 300 --quotations 150"
```

`make fresh` is enough on its own — the seeded catalogue including the staged
shortage is created at API startup. `make load-data` only adds bulk volume.

**Do not run `make test` between takes**: it truncates `users` and cascades,
which wipes the seeded accounts and the staged stock.
