"""Real task, client, collector, transaction, repository and API; only HTTP is mocked."""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.services.collector_service import PriceCollectionError
from app.tasks import collect_prices_task

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("failure", [None, "btc_usd", "all"])
def test_collection_task_to_api(monkeypatch, failure, caplog):
    database_url = os.environ.get("TEST_DATABASE_URL")
    redis_url = os.environ.get("TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("Set TEST_DATABASE_URL and TEST_REDIS_URL for pipeline tests")
    schema = "pipeline_" + uuid4().hex
    settings = SimpleNamespace(DATABASE_URL=database_url, REDIS_URL=redis_url)
    monkeypatch.setattr("app.tasks.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.collection_runner.get_settings", lambda: settings)

    def scoped_engine(*args, **kwargs):
        return create_async_engine(*args, **kwargs, connect_args={"server_settings": {"search_path": schema}})

    async def prepare():
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    async def verify_api():
        engine = scoped_engine(database_url)
        factory = async_sessionmaker(engine)
        async def override_db():
            async with factory() as session:
                yield session
        app.dependency_overrides[get_db] = override_db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                for ticker, expected in [("BTC_USD", "65000.12"), ("ETH_USD", "3000.34")]:
                    missing = failure == "all" or (failure == "btc_usd" and ticker == "BTC_USD")
                    latest = await client.get("/prices/latest", params={"ticker": ticker})
                    assert latest.status_code == (404 if missing else 200)
                    if not missing:
                        assert latest.json()["price"] == expected
                    history = await client.get("/prices", params={"ticker": ticker})
                    assert history.status_code == 200
                    assert len(history.json()) == (0 if missing else 2)
                    if not missing:
                        timestamp = latest.json()["timestamp"]
                        filtered = await client.get("/prices/filter", params={"ticker": ticker, "start_time": timestamp, "end_time": timestamp})
                        assert filtered.status_code == 200
                        assert any(row["id"] == latest.json()["id"] for row in filtered.json())
        finally:
            app.dependency_overrides.pop(get_db, None)
            await engine.dispose()

    async def cleanup():
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await engine.dispose()

    def mock_request(session, url, *, params, timeout):
        response = MagicMock()
        index = params["index_name"]
        response.status = 500 if failure in (index, "all") else 200
        response.json = AsyncMock(return_value={"result": {"index_price": 65000.12 if index == "btc_usd" else 3000.34}})
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        return context

    asyncio.run(prepare())
    try:
        with patch("aiohttp.ClientSession.get", new=mock_request), patch(
            "app.services.collection_runner.create_async_engine", side_effect=scoped_engine
        ):
            for _ in range(2):
                if failure == "all":
                    with pytest.raises(PriceCollectionError):
                        collect_prices_task.run()
                else:
                    collect_prices_task.run()
        asyncio.run(verify_api())
        if failure:
            assert "Failed to retrieve price" in caplog.text
    finally:
        asyncio.run(cleanup())
