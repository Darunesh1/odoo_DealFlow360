from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

# Initialize Celery app
celery_app = Celery(
    "tasks_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Configuration overrides
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

# Periodic work. Three business rules that have to happen on a clock rather
# than in response to a request:
#
#   - a backorder clears when stock arrives, which no user action announces
#   - a subscription bills on its own date, whether or not anyone is logged in
#   - a deal goes stale by the passage of time, which is the whole point of the
#     Deal Health screen
#
# Run with `make beat` alongside `make worker`.
celery_app.conf.beat_schedule = {
    "consolidate-backorders": {
        "task": "app.tasks.scheduled_tasks.consolidate_backorders",
        "schedule": 15 * 60.0,
    },
    "bill-due-subscriptions": {
        "task": "app.tasks.scheduled_tasks.bill_due_subscriptions",
        # 02:00 UTC daily: after any timezone's midnight rollover, well before
        # anyone looks at the invoices screen.
        "schedule": crontab(hour=2, minute=0),
    },
    "sweep-deal-health": {
        "task": "app.tasks.scheduled_tasks.sweep_deal_health",
        "schedule": crontab(minute=0),
    },
    "mine-co-purchases": {
        "task": "app.tasks.scheduled_tasks.mine_co_purchases",
        # 03:00 UTC daily, after the billing run. Only order confirmation moves
        # this data, and a suggestion that lags the truth by a day costs
        # nothing - whereas rebuilding it per request would put a self-join on
        # the critical path of a panel that refetches on every line change.
        "schedule": crontab(hour=3, minute=0),
    },
}

# Autodiscover tasks under app package
celery_app.autodiscover_tasks(["app"])
