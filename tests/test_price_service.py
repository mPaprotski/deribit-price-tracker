from unittest.mock import AsyncMock

import pytest

from app.repositories.price_repository import PriceRepository
from app.services.price_service import (
    InvalidTickerError, InvalidTimeRangeError, PriceNotFoundError, PriceService,
)


@pytest.fixture
def repository():
    return AsyncMock(spec=PriceRepository)


async def test_reads_delegate_to_repository(repository):
    service = PriceService(repository)
    record = object()
    repository.get_all_by_ticker.return_value = [record]
    repository.get_latest_by_ticker.return_value = record
    repository.get_by_time_range.return_value = [record]
    assert await service.get_all_prices("BTC_USD") == [record]
    assert await service.get_latest_price("ETH_USD") is record
    assert await service.get_filtered_prices("BTC_USD", 10, 20) == [record]
    repository.get_all_by_ticker.assert_awaited_once_with("BTC_USD")
    repository.get_latest_by_ticker.assert_awaited_once_with("ETH_USD")
    repository.get_by_time_range.assert_awaited_once_with("BTC_USD", 10, 20)


@pytest.mark.parametrize("ticker", ["DOGE_USD", "btc_usd", "", None])
async def test_invalid_ticker_never_calls_repository(repository, ticker):
    service = PriceService(repository)
    for method, args in [(service.get_all_prices, (ticker,)), (service.get_latest_price, (ticker,)), (service.get_filtered_prices, (ticker, 0, 10))]:
        with pytest.raises(InvalidTickerError):
            await method(*args)
    assert repository.mock_calls == []


async def test_missing_records(repository):
    service = PriceService(repository)
    repository.get_all_by_ticker.return_value = []
    repository.get_by_time_range.return_value = []
    repository.get_latest_by_ticker.return_value = None
    assert await service.get_all_prices("BTC_USD") == []
    assert await service.get_filtered_prices("BTC_USD", 0, 0) == []
    with pytest.raises(PriceNotFoundError):
        await service.get_latest_price("BTC_USD")


@pytest.mark.parametrize("start,end", [(20, 10), (-1, 10), (0, -1), (True, 10), (0, False), (1.5, 10), (0, "10"), (None, 10)])
async def test_invalid_time_range(repository, start, end):
    with pytest.raises(InvalidTimeRangeError):
        await PriceService(repository).get_filtered_prices("BTC_USD", start, end)
    repository.get_by_time_range.assert_not_awaited()


async def test_repository_failure_propagates(repository):
    repository.get_all_by_ticker.side_effect = RuntimeError("Database unavailable")
    with pytest.raises(RuntimeError):
        await PriceService(repository).get_all_prices("BTC_USD")
