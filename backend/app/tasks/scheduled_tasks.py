"""Periodic jobs.

Thin wrappers only. Each opens a session, calls one service function and
closes it - the business logic lives in the services so it can also be
triggered by a button on the relevant screen, and so it is testable without a
worker.

The service functions land in later phases; until then each task logs and
returns, so `make beat` runs clean from the start rather than crashing on a
schedule nobody has implemented yet.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine

from app.core.celery_app import celery_app
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)


def _run(coro_factory: Callable[..., Coroutine[Any, Any, Any]]) -> Any:
    """Runs one coroutine against a fresh session in the worker's own loop.

    A new session per task, never a request-scoped one: Celery runs outside the
    request lifecycle entirely, and sharing a session across the boundary is
    how you get a connection used from two event loops.
    """

    async def _inner() -> Any:
        async with async_session_maker() as db:
            return await coro_factory(db)

    return asyncio.run(_inner())


def _call(module_name: str, function_name: str, label: str) -> str:
    """Dispatches to a service function, tolerating one that does not exist yet.

    The schedule is declared up front so `make beat` runs clean from the first
    phase, but the services behind it arrive over several phases. A missing one
    logs and returns rather than filling the worker log with tracebacks every
    fifteen minutes.
    """
    import importlib

    try:
        module = importlib.import_module(f"app.services.{module_name}")
        function = getattr(module, function_name)
    except (ImportError, AttributeError):
        logger.info(f"{label}: not implemented yet, skipping")
        return f"{label}: skipped"

    count = _run(function)
    return f"{label}: {count}"


@celery_app.task(name="app.tasks.scheduled_tasks.consolidate_backorders")
def consolidate_backorders() -> str:
    return _call("fulfillment_service", "consolidate_backorders", "Backorders consolidated")


@celery_app.task(name="app.tasks.scheduled_tasks.bill_due_subscriptions")
def bill_due_subscriptions() -> str:
    return _call("invoice_service", "bill_due_subscriptions", "Recurring invoices issued")


@celery_app.task(name="app.tasks.scheduled_tasks.sweep_deal_health")
def sweep_deal_health() -> str:
    return _call("health_service", "sweep", "Deal health alerts raised")


@celery_app.task(name="app.tasks.scheduled_tasks.mine_co_purchases")
def mine_co_purchases() -> str:
    return _call("pairing_service", "mine_co_purchases", "Co-purchase pairings mined")
