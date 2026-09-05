from celery import Celery

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

# Autodiscover tasks under app package
celery_app.autodiscover_tasks(["app"])
