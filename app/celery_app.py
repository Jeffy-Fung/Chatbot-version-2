import os
from celery import Celery

# Redis URLs (supports authentication for cloud deployments)
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or "redis://redis:6379/0"
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or "redis://redis:6379/1"

celery_app = Celery(
    "worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_send_sent_event=True,  # Track when tasks are sent to queue
    task_time_limit=30 * 60,  # 30 minutes
    worker_prefetch_multiplier=1,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app"])
