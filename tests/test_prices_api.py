from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.api.dependencies import get_db, get_price_service
from app.db.models import PriceRecord
from app.main import app
from app.services.price_service import InvalidTickerError, InvalidTimeRangeError, PriceNotFoundError, PriceService


@pytest_asyncio.fixture
async def api():
    service = AsyncMock(spec=PriceService)
    async def override_service():
        return service
    app.dependency_overrides[get_price_service] = override_service
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, service
    finally:
        app.dependency_overrides.pop(get_price_service, None)


def record():
    return PriceRecord(id=1, ticker="BTC_USD", price=Decimal("65000.123456789012345678"), timestamp=1728000000)


async def test_history_and_exact_decimal(api):
    client, service = api
    service.get_all_prices.return_value = [record()]
    response = await client.get("/prices", params={"ticker": "BTC_USD"})
    assert response.status_code == 200
    assert response.json() == [{"id": 1, "ticker": "BTC_USD", "price": "65000.123456789012345678", "timestamp": 1728000000}]
    service.get_all_prices.assert_awaited_once_with("BTC_USD")


async def test_latest(api):
    client, service = api
    price = record()
    price.ticker = "ETH_USD"
    service.get_latest_price.return_value = price
    response = await client.get("/prices/latest?ticker=ETH_USD")
    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["ticker"] == "ETH_USD"
    service.get_latest_price.assert_awaited_once_with("ETH_USD")


async def test_filter(api):
    client, service = api
    service.get_filtered_prices.return_value = [record()]
    response = await client.get("/prices/filter?ticker=BTC_USD&start_time=1728000000&end_time=1728000000")
    assert response.status_code == 200
    assert len(response.json()) == 1
    service.get_filtered_prices.assert_awaited_once_with("BTC_USD", 1728000000, 1728000000)


@pytest.mark.parametrize("path", ["/prices", "/prices/latest", "/prices/filter?start_time=0&end_time=10"])
@pytest.mark.parametrize("ticker", [None, "DOGE_USD", "btc_usd", ""])
async def test_missing_or_invalid_ticker(api, path, ticker):
    client, service = api
    if ticker is not None:
        path += ("&" if "?" in path else "?") + f"ticker={ticker}"
    response = await client.get(path)
    assert response.status_code == 422
    assert service.mock_calls == []


@pytest.mark.parametrize("query", [
    "", "start_time=0", "end_time=10", "start_time=text&end_time=10",
    "start_time=-1&end_time=10", "start_time=10&end_time=0",
    "start_time=0&end_time=-1", "start_time=1.5&end_time=10",
    "start_time=0&end_time=true", f"start_time=0&end_time={2**63}",
])
async def test_invalid_timestamps(api, query):
    client, service = api
    response = await client.get(f"/prices/filter?ticker=BTC_USD&{query}")
    assert response.status_code == 422
    assert service.mock_calls == []


async def test_missing_latest(api):
    client, service = api
    service.get_latest_price.side_effect = PriceNotFoundError("No price found for ETH_USD")
    response = await client.get("/prices/latest?ticker=ETH_USD")
    assert response.status_code == 404
    assert response.json() == {"detail": "No price found for ETH_USD"}


async def test_empty_history(api):
    client, service = api
    service.get_all_prices.return_value = []
    service.get_filtered_prices.return_value = []
    for path in ["/prices?ticker=ETH_USD", "/prices/filter?ticker=ETH_USD&start_time=0&end_time=10"]:
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.parametrize("error", [InvalidTickerError("invalid ticker"), InvalidTimeRangeError("invalid range")])
async def test_service_validation_maps_to_422(api, error):
    client, service = api
    service.get_all_prices.side_effect = error
    assert (await client.get("/prices?ticker=BTC_USD")).status_code == 422


async def test_swagger_and_openapi(api):
    client, _ = api
    assert (await client.get("/docs")).status_code == 200
    schema = (await client.get("/openapi.json")).json()
    for path in ["/prices", "/prices/latest", "/prices/filter"]:
        assert "get" in schema["paths"][path]
    assert schema["components"]["schemas"]["PriceResponse"]["properties"]["price"]["type"] == "string"
    parameters = schema["paths"]["/prices/filter"]["get"]["parameters"]
    assert {param["name"] for param in parameters} == {"ticker", "start_time", "end_time"}
    assert all(param["in"] == "query" and param["required"] for param in parameters)


@pytest.mark.integration
async def test_api_with_real_repository(session):
    from app.repositories.price_repository import PriceRepository

    repository = PriceRepository(session)
    await repository.create_price("BTC_USD", Decimal("65000.123456789012345678"), 10)
    await repository.create_price("BTC_USD", Decimal("66000.12"), 20)
    await repository.create_price("ETH_USD", Decimal("3000.12"), 15)
    async def override_db():
        yield session
    app.dependency_overrides[get_db] = override_db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            history = await client.get("/prices?ticker=BTC_USD")
            assert [r["timestamp"] for r in history.json()] == [10, 20]
            assert history.json()[0]["price"] == "65000.123456789012345678"
            eth = await client.get("/prices/latest?ticker=ETH_USD")
            assert eth.status_code == 200
            assert eth.json()["ticker"] == "ETH_USD"
            assert eth.json()["price"] == "3000.12"
            latest = await client.get("/prices/latest?ticker=BTC_USD")
            assert latest.json()["timestamp"] == 20
            filtered = await client.get("/prices/filter?ticker=BTC_USD&start_time=10&end_time=10")
            assert [r["timestamp"] for r in filtered.json()] == [10]
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_health(api):
    client, service = api
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert service.mock_calls == []
