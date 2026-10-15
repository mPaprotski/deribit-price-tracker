from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError, LockNotOwnedError

from app.celery_app import celery_app
from app.core.config import get_settings
from app.tasks import COLLECTION_LOCK_TTL, collect_prices_task


@pytest.fixture
def dependencies():
    with patch("app.tasks.Redis") as redis_class, patch(
        "app.tasks.run_collection", new_callable=AsyncMock
    ) as run:
        redis = redis_class.from_url.return_value.__enter__.return_value
        lock = redis.lock.return_value
        lock.acquire.return_value = True
        yield redis, lock, run


def test_schedule_and_limits():
    schedule = celery_app.conf.beat_schedule["collect-index-prices"]
    assert schedule["task"] == collect_prices_task.name
    assert schedule["schedule"] == get_settings().COLLECTION_INTERVAL
    assert celery_app.conf.task_time_limit < COLLECTION_LOCK_TTL
    assert celery_app.conf.task_soft_time_limit < celery_app.conf.task_time_limit


def test_task_runs_and_releases_lock(dependencies):
    redis, lock, run = dependencies
    collect_prices_task.run()
    run.assert_awaited_once()
    lock.acquire.assert_called_once_with(blocking=False)
    lock.release.assert_called_once()
    redis.lock.assert_called_once_with("deribit_tracker:collect_prices:lock", timeout=120)


def test_concurrent_task_skipped(dependencies):
    _, lock, run = dependencies
    lock.acquire.return_value = False
    collect_prices_task.run()
    run.assert_not_called()
    lock.release.assert_not_called()


def test_failure_releases_lock_and_propagates(dependencies, caplog):
    _, lock, run = dependencies
    run.side_effect = RuntimeError("collection failed")
    with pytest.raises(RuntimeError, match="collection failed"):
        collect_prices_task.run()
    lock.release.assert_called_once()
    assert "Price collection task failed" in caplog.text


def test_repeated_tasks_use_new_event_loops(dependencies):
    import asyncio

    _, _, run = dependencies
    loops = []
    async def capture_loop():
        loops.append(asyncio.get_running_loop())
    run.side_effect = capture_loop
    collect_prices_task.run()
    collect_prices_task.run()
    assert loops[0] is not loops[1]
    assert all(loop.is_closed() for loop in loops)


def test_redis_failure_does_not_start_collection(dependencies):
    _, lock, run = dependencies
    lock.acquire.side_effect = ConnectionError("offline")
    with pytest.raises(ConnectionError):
        collect_prices_task.run()
    run.assert_not_called()


def test_lock_loss_does_not_hide_original_failure(dependencies, caplog):
    _, lock, run = dependencies
    run.side_effect = RuntimeError("original failure")
    lock.release.side_effect = LockNotOwnedError("expired")
    with pytest.raises(RuntimeError, match="original failure"):
        collect_prices_task.run()
    assert "lock ownership was lost" in caplog.text


@pytest.mark.integration
def test_real_redis_excludes_parallel_task(monkeypatch):
    import os
    from types import SimpleNamespace
    from redis import Redis
    from app.tasks import COLLECTION_LOCK_KEY

    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL for Redis integration tests")
    monkeypatch.setattr("app.tasks.get_settings", lambda: SimpleNamespace(REDIS_URL=url))
    with Redis.from_url(url) as redis:
        lock = redis.lock(COLLECTION_LOCK_KEY, timeout=120)
        assert lock.acquire(blocking=False)
        try:
            with patch("app.tasks.run_collection", new_callable=AsyncMock) as run:
                collect_prices_task.run()
                run.assert_not_called()
            assert lock.owned()
        finally:
            lock.release()
        with patch("app.tasks.run_collection", new_callable=AsyncMock) as run:
            collect_prices_task.run()
            run.assert_awaited_once()
        assert not redis.exists(COLLECTION_LOCK_KEY)


@pytest.mark.parametrize("failed_collection", [False, True])
def test_redis_release_failure_preserves_collection_result(dependencies, caplog, failed_collection):
    _, lock, run = dependencies
    lock.release.side_effect = ConnectionError("Redis is offline")
    if failed_collection:
        run.side_effect = RuntimeError("Original collection failure")
        with pytest.raises(RuntimeError, match="Original collection failure"):
            collect_prices_task.run()
    else:
        assert collect_prices_task.run() is None
    run.assert_awaited_once()
    assert "Failed to release collection lock" in caplog.text
