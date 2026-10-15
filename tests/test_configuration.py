import json
import logging
import os
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from app.core.logging import configure_logging
from scripts.run_api import main


def test_configure_logging_applies_to_application_and_uvicorn():
    loggers = [logging.getLogger(name) for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access")]
    levels = [logger.level for logger in loggers]
    try:
        configure_logging("ERROR")
        assert all(logger.getEffectiveLevel() == logging.ERROR for logger in loggers)
        assert not logging.getLogger("app.services.collector_service").isEnabledFor(logging.INFO)
    finally:
        for logger, level in zip(loggers, levels):
            logger.setLevel(level)


def test_api_launcher_passes_log_level(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setattr(sys, "argv", ["run_api", "--reload", "--port", "8765"])
    with patch("scripts.run_api.get_settings", return_value=Settings(LOG_LEVEL="ERROR")), patch(
        "scripts.run_api.configure_logging"
    ) as configure, patch("scripts.run_api.uvicorn.run") as run:
        main()
    configure.assert_called_once_with("ERROR")
    run.assert_called_once_with("app.main:app", host="0.0.0.0", port=8765, reload=True, log_level="error")


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker Compose CLI is required")
@pytest.mark.parametrize("custom_url", [False, True])
def test_compose_connection_settings(custom_url):
    env = os.environ.copy()
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "COMPOSE_DATABASE_URL", "COMPOSE_REDIS_URL"):
        env.pop(key, None)
    env.update(POSTGRES_USER="tracker", POSTGRES_PASSWORD="test_password", POSTGRES_DB="prices")
    if custom_url:
        env.update(COMPOSE_DATABASE_URL="postgresql+asyncpg://remote:pass@remote-db:5432/prices", COMPOSE_REDIS_URL="redis://remote-redis:6379/3")
    result = subprocess.run(
        ["docker", "compose", "--env-file", "/dev/null", "config", "--format", "json"],
        env=env, check=True, capture_output=True, text=True,
    )
    services = json.loads(result.stdout)["services"]
    assert services["db"]["environment"]["POSTGRES_USER"] == "tracker"
    for name in ("web", "celery_worker", "celery_beat"):
        assert services[name]["environment"]["DATABASE_URL"] == (
            env["COMPOSE_DATABASE_URL"] if custom_url else
            "postgresql+asyncpg://tracker:test_password@db:5432/prices"
        )
        assert services[name]["environment"]["REDIS_URL"] == (
            env["COMPOSE_REDIS_URL"] if custom_url else "redis://redis:6379/0"
        )
