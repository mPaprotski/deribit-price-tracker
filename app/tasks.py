import asyncio
import logging

from redis import Redis
from redis.exceptions import LockError, RedisError

from app.celery_app import celery_app
from app.core.config import get_settings
from app.services.collection_runner import run_collection

logger = logging.getLogger(__name__)
COLLECTION_LOCK_KEY = "deribit_tracker:collect_prices:lock"
# Longer than the prefork worker's hard task limit, allowing crash recovery.
COLLECTION_LOCK_TTL = 120


@celery_app.task(name="app.tasks.collect_prices_task")
def collect_prices_task() -> None:
    with Redis.from_url(
        get_settings().REDIS_URL, socket_connect_timeout=5, socket_timeout=5
    ) as redis:
        lock = redis.lock(COLLECTION_LOCK_KEY, timeout=COLLECTION_LOCK_TTL)
        if not lock.acquire(blocking=False):
            logger.info("Skipping price collection: another task holds the lock")
            return
        try:
            asyncio.run(run_collection())
            logger.info("Price collection task completed")
        except Exception:
            logger.exception("Price collection task failed")
            raise
        finally:
            try:
                # redis-py uses a token-checked Lua script; never delete another owner's lock.
                lock.release()
            except LockError:
                logger.exception("Price collection lock ownership was lost")
            except RedisError:
                logger.exception("Failed to release collection lock; waiting for TTL expiry")
