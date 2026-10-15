from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("deribit_tracker", broker=settings.REDIS_URL, include=["app.tasks"])
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=50,
    task_time_limit=60,
    beat_schedule={
        "collect-index-prices": {
            "task": "app.tasks.collect_prices_task",
            "schedule": float(settings.COLLECTION_INTERVAL),
            "options": {"expires": settings.COLLECTION_INTERVAL},
        },
    },
)
