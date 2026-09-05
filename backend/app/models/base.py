"""Shared building blocks for every domain model.

The numeric aliases below are the money convention for this codebase. Nothing
in the repo used a decimal column before DealFlow360's domain model, so these
are the precedent: import them rather than writing Numeric(...) inline, so a
price and a percentage can never quietly end up sharing a scale.
"""

from datetime import datetime, timezone
from sqlalchemy import DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

# Any settled amount: line totals, invoice totals, payments, shipping cost.
# Never Float - binary floats cannot represent 0.10, and these get summed and
# compared against payments for equality. asyncpg maps NUMERIC to Decimal.
MONEY = Numeric(14, 2)

# Per-unit rates only, never displayed raw. Four decimals because proration
# produces genuinely fractional rates: $46/month over 26 of 30 days is
# 39.8666.../unit. At scale 2 you would round at the unit AND at the total,
# and the two roundings drift apart by cents over a 24-cycle plan.
UNIT_PRICE = Numeric(12, 4)

# Percentages hold 12.50 for 12.5%, never 0.125. The spec, the mockup and the
# seed data all speak whole percents; storing the fraction invites a x100 bug
# at every boundary.
PERCENT = Numeric(5, 2)

# "8 pt over limit" is a difference of two percentages, which is a different
# unit from a percentage. Naming it separately stops anyone summing points
# into a percent column.
POINTS = Numeric(6, 2)

# Dimensionless factors: proration (26/30), warehouse shipping weight. Six
# decimals so an audit trail can reproduce the arithmetic exactly.
RATIO = Numeric(9, 6)


def utcnow() -> datetime:
    """Timezone-aware now, matching the convention in models/user.py."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """created_at / updated_at, identical to the pair written out in user.py.

    A deliberate departure from the house style of repeating them per model:
    that is fine once and is ~200 lines of copy-paste across thirty tables.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
